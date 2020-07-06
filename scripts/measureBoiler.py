import sys
import time, datetime, csv
import RPi.GPIO as GPIO


GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.OUT)
GPIO.setup(23, GPIO.IN)

prevState = -1
prevTime = datetime.datetime.now()
try:
	while True:
		if not GPIO.input(17):
			state = GPIO.input(23)
	
		if state != prevState or datetime.datetime.now() - prevTime > datetime.timedelta(hours = 12):
			with open('scripts/boilerState.csv', 'a') as f:
				timeNow = datetime.datetime.now().replace(microsecond = 0)
				f.write(f'{timeNow.isoformat()},{not state}\n')
			prevTime = datetime.datetime.now()

		prevState = state

		time.sleep(15)
except KeyboardInterrupt:
	sys.exit()
