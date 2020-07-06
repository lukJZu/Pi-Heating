import RPi.GPIO as GPIO
from datetime import datetime
import pandas as pd
#from dateutil.tz import tzlocal
import iso8601

GPIO.setmode(GPIO.BCM)

pinNo = 17

GPIO.setup(pinNo, GPIO.OUT)

#get the current time
timeNow = datetime.now().astimezone()

#read in the csv as pandas dataframe
scheduleDF = pd.read_csv('scripts/hotWater/schedule.csv')
scheduleDF['time'] = scheduleDF['time'].apply(iso8601.parse_date)

#scheduleDF['time'] = pd.to_datetime(scheduleDF['time'])
#scheduleDF.time = scheduleDF.time.dt.tz_localize(tzlocal())

subDF = scheduleDF[(scheduleDF.time<timeNow)]
row = subDF[subDF.time == subDF.time.max()]

if not row.size:
	state = 0
elif row.iloc[0, 1]:
	state = 1
elif not row.iloc[0, 1]:
	state = 0


if state:
	GPIO.output(pinNo, GPIO.LOW)
elif not state:
	GPIO.output(pinNo, GPIO.HIGH)
