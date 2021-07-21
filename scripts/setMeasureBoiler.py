import os, sys
import time, json
# import RPi.GPIO as GPIO
from gpiozero.pins.pigpio import PiGPIOFactory
from gpiozero import Button, LED
from pathlib import Path
from datetime import datetime, timedelta
import requests
import pandas as pd
import traceback

data_dir = "/mnt/data"

csvFile = os.path.join(data_dir, 'boilerState.csv')
boostJSON = os.path.join(data_dir, 'states.json')
scheduleCSV = os.path.join(data_dir, 'hotWaterSchedule.csv')
secondsInterval = 10
boostHeatingThermostatTemp = 27


def get_access_token():
    with open(os.path.join(data_dir, 'tokens.json'), 'r') as f:
        token_dict = json.load(f)

    expiry_time = datetime.fromisoformat(token_dict['expiry'])
    if expiry_time > datetime.now():
        return token_dict['access_token']
    
    with open(os.path.join(data_dir, 'oauth_secret_web.json'), 'r') as f:
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

    with open(os.path.join(data_dir, 'tokens.json'), 'w') as f:
        json.dump(token_dict, f)
    
    return access_token


def setHotWaterHeating(recordStates, hot_water_pin, heating_pin, boiler_state_pin):

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

    #check if previous state is the same as current state
    try:
        if setHotWaterState:
            hot_water_pin.off()
        else:
            hot_water_pin.on()
        if setHeatingState:
            heating_pin.on()
        else:
            heating_pin.off()
    except Exception:
        # del hot_water_pin, heating_pin, boiler_state_pin
        print("ERROR", traceback.print_exc())
        return (0, recordStates)

    #check and record boiler state
    boilerState = bool(boiler_state_pin.value)

    recordStates = [setHotWaterState, prevHeatingNestState, boilerState]
    if recordStates != prevMeasuredStates:
        #set heating state to on if boiler state is on and hot water is off
        if boilerState and not setHotWaterState:
            recordStates[1] = True

        with open(csvFile, 'a') as f:
            timeNow = datetime.now().replace(microsecond = 0).astimezone()
            f.write(f'{timeNow.isoformat()},{",".join(str(s) for s in recordStates)}\n')

    print("SET STATE", (1, [setHotWaterState, prevHeatingNestState, boilerState]))
    return (1, [setHotWaterState, prevHeatingNestState, boilerState])


def each_loop(pin_status, remote_pin_factory, recordStates):
    if not pin_status:
        try:
            remote_pin_factory = PiGPIOFactory("192.168.1.51")
            hot_water_pin       = LED(17, pin_factory=remote_pin_factory)
            heating_pin         = LED(18, pin_factory=remote_pin_factory)
            boiler_state_pin    = Button(23, pin_factory=remote_pin_factory)
        except Exception:
            print("PIN Setup error: ", traceback.print_exc())
            pass
        else:
            pin_status, recordStates = setHotWaterHeating(recordStates, 
                                        hot_water_pin, heating_pin, boiler_state_pin)
    else:
        pin_status, recordStates = setHotWaterHeating(recordStates, 
                                    hot_water_pin, heating_pin, boiler_state_pin)

    # if not pin_status:
    #     if "remote_pin_factory" in locals():
    #         # remote_pin_factory.close()
    #         del remote_pin_factory
    #     if "hot_water_pin" in locals():
    #         # hot_water_pin.close()
    #         del hot_water_pin
    #     if "heating_pin" in locals():
    #         # remote_pin_factory.close()
    #         del heating_pin
    #     if "boiler_state_pin" in locals():
    #         # remote_pin_factory.close()
    #         del boiler_state_pin




if __name__ == "__main__":
    # prevMeasuredStates = [-1, -1, -1]
    # prevHotWaterState = False
    # prevHeatingState = False
    recordStates = [False, False, -1]
    pin_status = 0
    try:
        while True:
            if not pin_status:
                try:
                    remote_pin_factory = PiGPIOFactory("192.168.1.51")
                    hot_water_pin       = LED(17, pin_factory=remote_pin_factory)
                    heating_pin         = LED(18, pin_factory=remote_pin_factory)
                    boiler_state_pin    = Button(23, pin_factory=remote_pin_factory)
                except Exception:
                    print("PIN Setup error: ", traceback.print_exc())
                    pass
                else:
                    pin_status, recordStates = setHotWaterHeating(recordStates, 
                                                hot_water_pin, heating_pin, boiler_state_pin)
            else:
                pin_status, recordStates = setHotWaterHeating(recordStates, 
                                            hot_water_pin, heating_pin, boiler_state_pin)

            if not pin_status:
                if "remote_pin_factory" in locals():
                    # remote_pin_factory.close()
                    del remote_pin_factory
                if "hot_water_pin" in locals():
                    # hot_water_pin.close()
                    del hot_water_pin
                if "heating_pin" in locals():
                    # remote_pin_factory.close()
                    del heating_pin
                if "boiler_state_pin" in locals():
                    # remote_pin_factory.close()
                    del boiler_state_pin

            time.sleep(secondsInterval)
    except KeyboardInterrupt:
        sys.exit()
