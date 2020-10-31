import os, sys, pytz, json
from operator import itemgetter
from datetime import date, time, datetime, timedelta
from dateutil.tz import tzlocal
from pathlib import Path
import pandas as pd

#read in the csv file that contains the updated agile rates into dataframe
ratesDF = pd.read_csv(os.path.join(Path.home(), 'data', 'agileRates.csv'))
ratesDF['valid_to'] = pd.to_datetime(ratesDF['valid_to'], utc=True)
ratesDF['valid_from'] = pd.to_datetime(ratesDF['valid_from'], utc=True)


time_variables_json = os.path.join(Path.home(), 'data', 'time_variables.json')
try:
    with open(time_variables_json, 'r') as f:
        time_variables = json.load(f)
except FileNotFoundError:
    time_variables = {}

#read in any existing schedule for hot water into a dataframe
scheduleFile = os.path.join(Path.home(), 'data', 'hotWaterSchedule.csv')
# try:
#     scheduleDF = pd.read_csv(scheduleFile, header = 0)
# except:
scheduleDF = pd.DataFrame(columns=['time', 'state'])

#timezone is system timezone
scheduleDF['time'] = pd.to_datetime(scheduleDF['time'], utc=True)

#remove any rows which are older than today and tomorrow's rows
# if scheduleDF.shape[0]:
#     scheduleDF = scheduleDF.drop(scheduleDF[scheduleDF['time'].dt.date < date.today()].index)
#     scheduleDF = scheduleDF.drop(scheduleDF[scheduleDF['time'].dt.date == date.today()+timedelta(days=1)].index)

#get the past month avg from states.json
with open(os.path.join(Path.home(), 'data', 'states.json'), 'r') as f:
    states = json.load(f)
heatWaterMin = states['hotWater']['pastMonthAvg'] + time_variables.get('addToAverage', 10)    #how long is the typical heat up
# heatWaterMin = 50    #how long is the typical heat up
fullHeating = time_variables.get("fullHeatingMin", 100)         #how long is the full heat up
kWUse = time_variables.get("boilerPowerkW", 9)                  #what is the power rating of the boiler
heatBeforeHour = time_variables.get("heatBeforeHour", 16)       #set the hour of the day which to find the heat up time


#set starting time to the current hour and convert everything to UTC for comparison
currentTime = datetime.now().astimezone(pytz.utc).replace(minute=0, second = 0, microsecond=0)
endLoopTime = datetime.now().astimezone(tzlocal()).replace(minute=0, second = 0, microsecond=0, hour=0) \
                + timedelta(days = 1)

endLoopTime = endLoopTime.replace(hour=heatBeforeHour).astimezone(pytz.utc)
costs, times = [], []

#start from tomorrow and ends when reaches the next day heat before hour
while currentTime < endLoopTime:
    #get the ratesDF row with the current time in it
    currentRow = ratesDF[(ratesDF['valid_from'] <= currentTime) & (currentTime < ratesDF['valid_to'])]
    if not currentRow.size:
        currentTime += timedelta(minutes = 15)
        continue
    #initialising the cost of heating
    cost = 0
    #how long the heating time is remaining in seconds
    heatTimeLeft = heatWaterMin * 60
    #setting the start and end time and rate from the filtered dataframe
    startTime, endTime, currentRate = currentRow.iloc[0]['valid_from'], currentRow.iloc[0]['valid_to'], currentRow.iloc[0]['rate']
    
    cTime = currentTime.astimezone(pytz.utc)
    endTime = endTime.astimezone(pytz.utc)

    while heatTimeLeft > (endTime - cTime).seconds:
        secs = (endTime - cTime).total_seconds()
        cost += secs * kWUse /3600 * currentRate

        heatTimeLeft = heatTimeLeft - (endTime - cTime).seconds

        #get the next timeframe cost
        nextRow = ratesDF[(ratesDF['valid_from'] == endTime)]
        nextRow = nextRow[nextRow['valid_to'] == nextRow['valid_to'].min()]

        if not nextRow.size:
            cost = 9999
            break
        
        nextRow = nextRow.iloc[0]
        startTime, endTime, currentRate = nextRow['valid_from'], nextRow['valid_to'], nextRow['rate']
        cTime = startTime

    cost += heatTimeLeft * kWUse / 3600 * currentRate
    costs.append(cost)
    times.append(currentTime)
    currentTime = currentTime + timedelta(minutes=time_variables.get("searchBlockMins"))


#getting the lowest cost starting time
val, idx = min((val, idx) for (idx, val) in enumerate(costs))
timeOn = times[idx]

#getting the smart meter time delay and add the offset
if time_variables.get('smartMeterDelay'):
    delayMinutes = time_variables.get('smartMeterDelay').get('minutes', 0)
    delaySeconds = time_variables.get('smartMeterDelay').get('seconds', 0)
else:
    delayMinutes, delaySeconds = -1, -30
#getting the boiler startup delay
if time_variables.get('boilerStartupDelay'):
    delayMinutes -= time_variables.get('boilerStartupDelay').get('minutes', 0)
    delaySeconds -= time_variables.get('boilerStartupDelay').get('seconds', 0)
else:
    delayMinutes -= 1
    delaySeconds -= 30
timeOn = timeOn + timedelta(minutes = delayMinutes, seconds = delaySeconds)
timeOff = timeOn + timedelta(minutes = fullHeating)

#adding timeOn to the schedule
scheduleDF.loc[len(scheduleDF)] = [timeOn, 1]

#loop over to find negative rates
prevRate = 0
negDF = pd.DataFrame(columns = ['time', 'state'])
for tup in ratesDF.itertuples():
    #skipping any rows which are older than the start time of the min cost
    if tup.valid_from < timeOn:#tup.valid_from < datetime.now().astimezone() or tup.valid_from:
        prevRate = tup.rate
        continue
    #iterating over the timeframes
    #if rate is negative, set state to on
    if tup.rate < 0:
        startTime = tup.valid_from
        negDF.loc[len(negDF)] = [startTime+timedelta(minutes=delayMinutes, seconds=delaySeconds), 1]
    #if rate becomes positive, set state to off
    elif tup.rate > 0 and prevRate < 0:
        negDF.loc[len(negDF)] = [tup.valid_from+timedelta(minutes=delayMinutes, seconds=delaySeconds), 0]
    
    if tup.valid_from < timeOff < tup.valid_to and tup.rate > 0:
        scheduleDF.loc[len(scheduleDF)] = [timeOff, 0]
        scheduleDF = scheduleDF.drop(scheduleDF[(scheduleDF['time'] > timeOn
                    ) & (scheduleDF['time'] < timeOff)].index)

    prevRate = tup.rate
    
#combining the negrates DF back to main scheduleDF
scheduleDF = pd.concat([scheduleDF, negDF], ignore_index = True)

#checking for duplicates and remove the off state
modes = scheduleDF['time'].value_counts()
for idx, value in modes.items():
    if value > 1:
        #checking if the duplicated times have same or different states
        subDF = scheduleDF[scheduleDF['time'] == idx]
        stateCount = subDF['state'].nunique()
        #if different states, then drop the off state
        if stateCount > 1:
            scheduleDF = scheduleDF.drop(scheduleDF[(
                scheduleDF['time'] == idx) & (
                scheduleDF['state'] == 0)].index)

#set to turn off at 2359
lastTime = datetime.combine(date.today()+timedelta(days = 2),time()) - timedelta(minutes = 1)
lastTime = lastTime.astimezone(pytz.utc)
scheduleDF.loc[len(scheduleDF)] = [lastTime, 0]

#drop duplicated rows
scheduleDF = scheduleDF.drop(scheduleDF[scheduleDF.duplicated()].index)

scheduleDF.time = scheduleDF['time'].dt.tz_convert(tzlocal())
scheduleDF['state'] = scheduleDF['state'].astype(bool)
scheduleDF = scheduleDF.sort_values(by = 'time')

scheduleDF.to_csv(scheduleFile, index=False)
