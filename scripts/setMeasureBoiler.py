import os, sys, pathlib
import time, csv, json
import RPi.GPIO as GPIO
from pathlib import Path
from datetime import datetime
import iso8601

GPIO.setmode(GPIO.BCM)

hotWaterPin 	= 17
heatingPin 		= 18
boilerStatePin 	= 23

GPIO.setup(hotWaterPin, GPIO.OUT)
GPIO.setup(heatingPin, GPIO.OUT)
GPIO.setup(boilerStatePin, GPIO.IN)

csvFile = os.path.join(Path.home(), 'data', 'boilerState.csv')
boostJSON = os.path.join(Path.home(), 'data', 'states.json')
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


def measureBoiler(prevState):
	while True:
		#storing state of the hotWater, heating and boiler
		hotWaterState = not GPIO.input(hotWaterPin)
		heatingState  = bool(GPIO.input(heatingPin))
		boilerState   = not GPIO.input(boilerStatePin)
	
		if boilerState != prevState:# or datetime.datetime.now() - prevTime > datetime.timedelta(hours = 12):
			with open(csvFile, 'a') as f:
				timeNow = datetime.now().replace(microsecond = 0).astimezone()
				f.write(f'{timeNow.isoformat()},{hotWaterState},{heatingState},{boilerState}\n')
			# prevTime = datetime.datetime.now()

		return boilerState


def setHotWater(prevState):

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
	def checkHotWaterStates():
		with open(boostJSON, 'r') as f:
			hotWaterStates = json.load(f)
		return hotWaterStates

	#update the boost json file by setting boost to off
	def turnOffBoost():
		hotWaterStates = checkHotWaterStates()
		hotWaterStates['hotWater']['boost'] = False
		with open(boostJSON, 'w') as f:
			json.dump(hotWaterStates, f)

	# prevState = False
	#get the current time
	timeNow = datetime.now().astimezone()

	#get the boostState
	hotWaterStates = checkHotWaterStates()['hotWater']
	cState = hotWaterStates['state']
	bState = hotWaterStates['boost']
	#if boost is on
	if bState:
		#get the end time
		endTime = datetime.fromisoformat(hotWaterStates['endTime'])
		#if end time hasn't passed, then set state as on
		if timeNow < endTime:
			state = True
		#if end time has passed, turn boost off by updating json, 
		#then set state according to schedule
		elif endTime < timeNow:
			turnOffBoost()
			state = checkAgainstSchedule()
	#if boost is off, set state according to schedule
	elif not cState:
		state = False
	else:
		state = checkAgainstSchedule()

	#check if previous state is the same as current state
	#if not, then set the state
	if prevState != state:
		GPIO.output(hotWaterPin, not state)

	return state



if __name__ == "__main__":
	prevBoilerState = -1
	prevHotWaterState = False
	try:
		while True:
			prevHotWaterState = setHotWater(prevHotWaterState)
			prevBoilerState = measureBoiler(prevBoilerState)
			time.sleep(secondsInterval)
	except KeyboardInterrupt:
		sys.exit()
