import os, sys, pathlib
import time, csv, json
import RPi.GPIO as GPIO
from pathlib import Path
from datetime import datetime, timedelta
import requests
import pandas as pd

GPIO.setmode(GPIO.BCM)

hotWaterPin        = 17
heatingPin         = 18
boilerStatePin     = 23

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
boostHeatingThermostatTemp = 25


def get_access_token():
    with open(os.path.join(Path.home(), 'data', 'tokens.json'), 'r') as f:
        token_dict = json.load(f)

    expiry_time = datetime.fromisoformat(token_dict['expiry'])
    if expiry_time > datetime.now():
        return token_dict['access_token']
    
    with open(os.path.join(Path.home(), 'data', 'oauth_secret_web.json'), 'r') as f:
        credentials = json.load(f)['web']
        
    url = "https://www.googleapis.com/oauth2/v4/token?"+\
            f"client_id={credentials['client_id']}"+\
            f"&client_secret={credentials['client_secret']}"+\
            f"&refresh_token={token_dict['refresh_token']}"+\
            "&grant_type=refresh_token"

    resp = requests.post(url).json()
    access_token = resp['access_token']
    # refresh_token = resp['refresh_token']

    token_dict['access_token'] = access_token
    # token_dict['refresh_token'] = refresh_token
    new_expiry = datetime.now() + timedelta(seconds=3599)
    token_dict['expiry'] = new_expiry.isoformat()

    with open(os.path.join(Path.home(), 'data', 'tokens.json'), 'w') as f:
        json.dump(token_dict, f)
    
    return access_token


# def measureBoiler(prevMeasuredStates):
#     #storing state of the hotWater, heating and boiler
#     # hotWaterState = 1
#     # heatingState  = 0
#     # boilerState   = 1
#     hotWaterState = not GPIO.input(hotWaterPin)
#     heatingState  = bool(GPIO.input(heatingPin))
#     boilerState   = not GPIO.input(boilerStatePin)

#     states = [hotWaterState, heatingState, boilerState]
#     if states != prevMeasuredStates:
#         with open(csvFile, 'a') as f:
#             timeNow = datetime.now().replace(microsecond = 0).astimezone()
#             f.write(f'{timeNow.isoformat()},{",".join(str(s) for s in states)}\n')

#     return states


def setHotWaterHeating(recordStates):

    prevHeatingNestState = recordStates[1]

    def checkAgainstSchedule():
        scheduleDF = pd.read_csv(scheduleCSV)
        scheduleDF['start_time'] = pd.to_datetime(scheduleDF['start_time'], utc=True)
        scheduleDF['end_time'] = pd.to_datetime(scheduleDF['end_time'], utc=True)
         
        #assume off initially
        hotWaterState, heatingState = False, False
        timestampNow = pd.Timestamp.now('utc')
        time_block_now = scheduleDF[(scheduleDF['start_time'] < timestampNow) & (scheduleDF['end_time'] > timestampNow)]
        if len(time_block_now.index):
            hotWaterState = time_block_now.iloc[0].hot_water_state
            heatingState = time_block_now.iloc[0].heating_state
        
        return {"hotWater": hotWaterState, "heating":heatingState}

    #getting the boost states from the json file
    def checkJSONStates():
        with open(boostJSON, 'r') as f:
            hotWaterStates = json.load(f)
        return hotWaterStates

    def setState(stateType, jsonState, scheduleState):
        cState = jsonState[stateType]['state']
        bState = jsonState[stateType]['boost']

        #if boost is on
        if bState:
            #get the end time
            endTime = datetime.fromisoformat(jsonState[stateType]['endTime'])
            #if end time hasn't passed, then set state as on
            if timeNow < endTime:
                returnState = True
            #if end time has passed, turn boost off by updating json, 
            #then set state according to schedule
            elif endTime < timeNow:
                turnOffBoost(stateType)
                returnState = scheduleState
                bState = False
        #if boost is off, set state according to schedule
        elif not cState:
            returnState = False
        else:
            returnState = scheduleState
        
        return returnState
        

    #update the boost json file by setting boost to off
    def turnOffBoost(stateType):
        states = checkJSONStates()
        states[stateType]['boost'] = False
        with open(boostJSON, 'w') as f:
            json.dump(states, f)

    #get the current time
    timeNow = datetime.now().astimezone()

    #get the boostState
    jsonState = checkJSONStates()
    scheduleStates = checkAgainstSchedule()

    setHotWaterState = setState('hotWater', jsonState, scheduleStates['hotWater'])

    if jsonState['heating']['state']:
        setHeatingState = True
        heatingState = setState('heating', jsonState, scheduleStates['heating'])

        if prevHeatingNestState != heatingState:
            with open(f'{Path.home()}/data/oauth_secret_web.json', 'r') as f:
                json_dict = json.load(f)['web']
            device_id = json_dict['device_id']
            project_id = json_dict['device_access_project_ID']

            access_token = get_access_token()
            url = f"https://smartdevicemanagement.googleapis.com/v1/enterprises/{project_id}/devices/{device_id}"
            heatTemp = boostHeatingThermostatTemp if heatingState else 17
            setData = {
                "command" : "sdm.devices.commands.ThermostatTemperatureSetpoint.SetHeat",
                "params" : {
                    "heatCelsius" : heatTemp
                }
            }
            requests.post(url+':executeCommand', headers={"Content-Type": "application/json", 
                            "Authorization": f"Bearer {access_token}"},
                            data=json.dumps(setData))
            prevHeatingNestState = heatingState
    else:
        setHeatingState = False

    #read heating state
    #setHeatingState = jsonState['heating']['state']

    #check if previous state is the same as current state
    #if not, then set the state
#    if prevWaterState != setHotWaterStat:
    GPIO.output(hotWaterPin, not setHotWaterState)
#    if prevHeatingState != setHeatingState:
    GPIO.output(heatingPin, setHeatingState)

    #check and record boiler state
    boilerState   = not GPIO.input(boilerStatePin)

    recordStates = [setHotWaterState, prevHeatingNestState, boilerState]
    if recordStates != prevMeasuredStates:
        #set heating state to on if boiler state is on and hot water is off
        if boilerState and not setHotWaterState:
            recordStates[1] = True

        with open(csvFile, 'a') as f:
            timeNow = datetime.now().replace(microsecond = 0).astimezone()
            f.write(f'{timeNow.isoformat()},{",".join(str(s) for s in recordStates)}\n')

    return recordStates



if __name__ == "__main__":
    prevMeasuredStates = [-1, -1, -1]
    prevHotWaterState = False
    prevHeatingState = False
    recordStates = [False, False, -1]
    try:
        while True:
            recordStates = setHotWaterHeating(recordStates)
            # prevMeasuredStates = measureBoiler(prevMeasuredStates)
            time.sleep(secondsInterval)
    except KeyboardInterrupt:
        sys.exit()
