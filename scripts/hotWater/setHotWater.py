import os, sys, time, json, csv
import RPi.GPIO as GPIO
from datetime import datetime
import iso8601
from pathlib import Path

GPIO.setmode(GPIO.BCM)

pinNo = 17

GPIO.setup(pinNo, GPIO.OUT)
GPIO.output(17, GPIO.HIGH)

boostJSON = os.path.join(Path.home(), 'data', 'boostStates.json')
scheduleCSV = os.path.join(Path.home(), 'data', 'hotWaterSchedule.csv')
secondsInterval = 20


def condenseTimes(timeStates:list):
    prevState = 0
    condensedTimes = []
    for timeState in timeStates:
        if len(timeState) <= 1:
            continue
        if timeState[-1] == 'True':
            state = True
            startTime = iso8601.parse_date(timeState[0])
            prevStates = timeState[1:]
        elif timeState[-1] == 'False':
            state = False
            if prevState:
                endTime = iso8601.parse_date(timeState[0])
                prevStates = [False if a == 'False' else True for a in prevStates]
                condensedTimes.append((startTime, endTime, prevStates
                            ))
        prevState = state

    return condensedTimes

def checkAgainstSchedule():
	#open the schedule csv file
	with open(scheduleCSV, 'r') as f:
		schedule = list(csv.reader(f))[1:]
	#sort the schedule into list of start-end times
	condensedTimes = condenseTimes(schedule)
	#assume off initially
	state = False
	#iterate over the timeframes to check whethere timenow is within any timeframe
	for timeframe in condensedTimes:
		if timeframe[0] < timeNow < timeframe[1]:
			state = True
			break

	return state

#getting the boost states from the json file
def checkBoostState():
	with open(boostJSON, 'r') as f:
		boostStates = json.load(f)
	return boostStates

#update the boost json file by setting boost to off
def turnOffBoost():
	boostStates = checkBoostState()
	boostStates['hotWater']['state'] = False
	with open(boostJSON, 'w') as f:
		json.dump(boostStates, f)

try:
	prevState = False
	while True:
		#get the current time
		timeNow = datetime.now().astimezone()

		#get the boostState
		boostStates = checkBoostState()['hotWater']
		bState = boostStates['state']
		#if boost is on
		if bState:
			#get the end time
			endTime = datetime.fromisoformat(boostStates['endTime'])
			#if end time hasn't passed, then set state as on
			if timeNow < endTime:
				state = True
			#if end time has passed, turn boost off by updating json, 
			#then set state according to schedule
			elif endTime < timeNow:
				turnOffBoost()
				state = checkAgainstSchedule()
		#if boost is off, set state according to schedule
		else:
			state = checkAgainstSchedule()

		#check if previous state is the same as current state
		#if not, then set the state
		if prevState != state:
			GPIO.output(pinNo, not state)

		#pause for x seconds
		time.sleep(secondsInterval)
		prevState = state


except KeyboardInterrupt:
	sys.exit()
