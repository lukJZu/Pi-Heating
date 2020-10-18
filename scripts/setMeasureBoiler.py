import os, sys, pathlib
import time, csv, json
import RPi.GPIO as GPIO
from pathlib import Path
from datetime import datetime
import iso8601

GPIO.setmode(GPIO.BCM)

hotWaterPin 	= 17
heatingPin 	    = 18
boilerStatePin 	= 23

GPIO.setup(hotWaterPin, GPIO.OUT)
GPIO.setup(heatingPin, GPIO.OUT)
GPIO.setup(boilerStatePin, GPIO.IN)
#turn off pins after reboot
GPIO.output(hotWaterPin, GPIO.HIGH)
GPIO.output(heatingPin, GPIO.LOW)

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
			if not prevState:
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


def measureBoiler(prevMeasuredStates):
	while True:
		#storing state of the hotWater, heating and boiler
		hotWaterState = not GPIO.input(hotWaterPin)
		heatingState  = bool(GPIO.input(heatingPin))
		boilerState   = not GPIO.input(boilerStatePin)

		states = [hotWaterState, heatingState, boilerState]
		if states != prevMeasuredStates:
			with open(csvFile, 'a') as f:
				timeNow = datetime.now().replace(microsecond = 0).astimezone()
				f.write(f'{timeNow.isoformat()},{",".join(str(s) for s in states)}\n')

		return states


def setHotWaterHeating(prevWaterState, prevHeatingState):

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
	def checkJSONStates():
		with open(boostJSON, 'r') as f:
			hotWaterStates = json.load(f)
		return hotWaterStates

	#update the boost json file by setting boost to off
	def turnOffBoost():
		hotWaterStates = checkJSONStates()
		hotWaterStates['hotWater']['boost'] = False
		with open(boostJSON, 'w') as f:
			json.dump(hotWaterStates, f)

	# prevState = False
	#get the current time
	timeNow = datetime.now().astimezone()

	#get the boostState
	jsonState = checkJSONStates()
	cState = jsonState['hotWater']['state']
	bState = jsonState['hotWater']['boost']

	#if boost is on
	if bState:
		#get the end time
		endTime = datetime.fromisoformat(jsonState['hotWater']['endTime'])
		#if end time hasn't passed, then set state as on
		if timeNow < endTime:
			setHotWaterStat = True
		#if end time has passed, turn boost off by updating json, 
		#then set state according to schedule
		elif endTime < timeNow:
			turnOffBoost()
			setHotWaterStat = checkAgainstSchedule()
	#if boost is off, set state according to schedule
	elif not cState:
		setHotWaterStat = False
	else:
		setHotWaterStat = checkAgainstSchedule()

	#read heating state
	setHeatingState = jsonState['heating']['state']

	#check if previous state is the same as current state
	#if not, then set the state
#	if prevWaterState != setHotWaterStat:
	GPIO.output(hotWaterPin, not setHotWaterStat)
#	if prevHeatingState != setHeatingState:
	GPIO.output(heatingPin, setHeatingState)


	return setHotWaterStat, setHeatingState



if __name__ == "__main__":
	prevMeasuredStates = [-1, -1, -1]
	prevHotWaterState = False
	prevHeatingState = False
	try:
		while True:
			prevHotWaterState, prevHeatingState = setHotWaterHeating(prevHotWaterState, prevHeatingState)
			prevMeasuredStates = measureBoiler(prevMeasuredStates)
			time.sleep(secondsInterval)
	except KeyboardInterrupt:
		sys.exit()
