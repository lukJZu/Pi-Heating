import os, sys, pathlib
import time, datetime, csv
import RPi.GPIO as GPIO


GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)
GPIO.setup(18, GPIO.OUT)
GPIO.setup(23, GPIO.IN)

prevState = -1
prevTime = datetime.datetime.now()
homeDir = str(pathlib.Path.home())
csvFile = os.path.join(homeDir, 'data', 'boilerState.csv')

try:
	while True:
#		if not GPIO.input(17):
#			state = GPIO.input(23)
#		else:
#			state = GPIO.HIGH
		
		#storing state of the hotWater, heating and boiler
		hotWaterState = not GPIO.input(17)
		heatingState  = bool(GPIO.input(18))
		boilerState   = not GPIO.input(23)
	
		if boilerState != prevState or datetime.datetime.now() - prevTime > datetime.timedelta(hours = 12):
			with open(csvFile, 'a') as f:
				timeNow = datetime.datetime.now().replace(microsecond = 0).astimezone()
				f.write(f'{timeNow.isoformat()},{hotWaterState},{heatingState},{boilerState}\n')
			prevTime = datetime.datetime.now()

		prevState = boilerState

		time.sleep(30)
except KeyboardInterrupt:
	sys.exit()
