import os, sys, pytz, json
from operator import itemgetter
from datetime import date, time, datetime, timedelta
from dateutil.tz import tzlocal
from pathlib import Path
import pandas as pd
import iso8601

#read in the csv file that contains the updated agile rates into dataframe
ratesDF = pd.read_csv(os.path.join(Path.home(), 'data', 'agileRates.csv'))
ratesDF['valid_to'] = ratesDF['valid_to'].apply(iso8601.parse_date)
ratesDF['valid_from'] = ratesDF['valid_from'].apply(iso8601.parse_date)

#read in any existing schedule for hot water into a dataframe
scheduleFile = os.path.join(Path.home(), 'data', 'hotWaterSchedule.csv')
try:
    scheduleDF = pd.read_csv(scheduleFile, header = 0)
except:
    scheduleDF = pd.DataFrame(columns=['time', 'state'])

#timezone is system timezone
scheduleDF['time'] = scheduleDF['time'].apply(iso8601.parse_date)

#remove any rows which are older than today
if scheduleDF.shape[0]:
    scheduleDF = scheduleDF.drop(scheduleDF[scheduleDF['time'].dt.date < date.today()].index)

#get the past month avg from states.json
with open(os.path.join(Path.home(), 'data', 'states.json'), 'r') as f:
    states = json.load(f)
heatWaterMin = states['hotWater']['pastMonthAvg'] + 10    #how long is the typical heat up
# heatWaterMin = 50    #how long is the typical heat up
fullHeating = 100                                    #how long is the full heat up
kWUse = 9                                            #what is the power rating of the boiler
heatBeforeHour = 16

#loop over to find negative rates
prevRate = 0
negDF = pd.DataFrame(columns = ['time', 'state'])
for tup in ratesDF.itertuples():
    #skipping any rows which are older than now
    if tup.valid_from < datetime.now().astimezone():
        prevRate = tup.rate
        continue
    #iterating over the timeframes
    if tup.rate < 0:
        startTime = tup.valid_from
        negDF.loc[len(negDF)] = [startTime - timedelta(minutes = 1, seconds = 10), 1]
    elif tup.rate > 0 and prevRate < 0:
        negDF.loc[len(negDF)] = [tup.valid_from-timedelta(minutes = 1, seconds=10), 0]
    prevRate = tup.rate

#check if the negative rates already exceeded the full heating time
onTime = timedelta()
onState = 0
for no in range(len(negDF.index)):
    if negDF.iloc[no,1]:
        onState = 1
    elif not negDF.iloc[no,1] and onState and no > 0:
        onTime += negDF.iloc[no, 0] - negDF.iloc[no-1, 0]
        onState = 0
#variable to skip the while loop if heating time has exceeded
if onTime.seconds >= fullHeating * 60:
    skipWhile = True
else:
    skipWhile = False

scheduleDF = pd.concat([scheduleDF, negDF], ignore_index = True)
try:
    scheduleDF.time = scheduleDF.time.dt.tz_convert(tzlocal())
except AttributeError:
    pass

#calculate the remaining minutes to heat
heatWaterMinAfterNeg = heatWaterMin - onTime.seconds / 60

#calculating heat time today
# todayDF = scheduleDF[scheduleDF['time'] < datetime.now().astimezone()]
# state, secondsOn = 0, 0
# for i in range(todayDF.shape[0]-1):
#     if todayDF.iloc[i, 1]:
#         state = 1
#     if not todayDF.iloc[i, 1] and state:
#         secondsOn += (todayDF.iloc[i, 0] - todayDF.iloc[i-1, 0]).seconds
#         state = 0

#set starting time to the current hour 
# tomorrow = date.today() + timedelta(days = 1)
currentTime = datetime.now().astimezone(tzlocal()).replace(minute=0, second = 0, microsecond=0)
midnightToday = datetime.now().astimezone(tzlocal()).replace(minute=0, second = 0, microsecond=0, hour=0)
costs, times = [], []

#start from tomorrow and ends when reaches the next day
while currentTime < midnightToday + timedelta(days = 1, hours=heatBeforeHour) and not skipWhile:
    #get the ratesDF row with the current time in it
    currentRow = ratesDF[(ratesDF['valid_from'] <= currentTime) & (currentTime < ratesDF['valid_to'])]
    if not currentRow.size:
        currentTime += timedelta(minutes = 15)
        continue
    #initialising the cost of heating
    cost = 0
    #how long the heating time is remaining in seconds
    heatTimeLeft = heatWaterMinAfterNeg * 60
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
    currentTime = currentTime + timedelta(minutes=10)


if not skipWhile and costs:
    # idx = len(costs) - costs.index(min(costs)) - 1
    val, idx = min((val, idx) for (idx, val) in enumerate(costs))
    timeOn = times[idx]

    #checking for duplicates
    timeOn = timeOn.astimezone() - timedelta(minutes = 1, seconds = 30)
    scheduleDF.loc[len(scheduleDF)] = [timeOn, 1]
    timeOff = timeOn + timedelta(minutes = (fullHeating - heatWaterMin + heatWaterMinAfterNeg))
    scheduleDF.loc[len(scheduleDF)] = [timeOff, 0]

    #check and drop anything between timeOn and timeOff
    scheduleDF = scheduleDF.drop(scheduleDF[(scheduleDF['time'] > timeOn
                ) & (scheduleDF['time'] < timeOff)].index)

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
lastTime = lastTime.astimezone()
scheduleDF.loc[len(scheduleDF)] = [lastTime, 0]

#drop duplicated rows
scheduleDF = scheduleDF.drop(scheduleDF[scheduleDF.duplicated()].index)

scheduleDF['state'] = scheduleDF['state'].astype(bool)
scheduleDF = scheduleDF.sort_values(by = 'time')
scheduleDF.to_csv(scheduleFile, index=False)
