# Pi-Heating

This project started off in June 2020 during the Covid-19 lockdown (great times I know). I had to get my gas boiler removed and had to go full electric for the flat.
With electricity retail prices about 4-5 times higher than gas prices per kWh, I had to find ways to reduce my energy bills to heat up the flat and the hot water cylinder.

I managed to find the way:
1) Get a smart meter installed so the supplier can read your meter reading every 30 minutes automatically
2) Move onto any smart tariff, in this case I moved to <a href="https://octopus.energy/agile/">Octopus Agile</a>, to get electricity unit prices cheaper than the standard flat rate 14-15p/kWh depending on the time of the day.
3) With Octopus Agile, the rate overnight (in 2020 anyway) was around 8-9p, occasionally ~5p and rarely goes below 0p (ie. you get paid to use electricity)
4) Hardwire a relay switch to my S-Plan heating circuit, set the built-in wall timer (Honeywell or other brands) to be always on for the hot water and let the Raspberry Pi to control the relay on when to switch on and off the heating of the hot water tank.

This repo contains a few scripts, which are setup using crontab on the RPi to run automatically everyday to calculate when is the best time in the day to heat up the hot water tank due to the constantly changing of half-hourly electricity prices on the tariff. On some days it's 1am, some days it's 4am, some days it's 11pm. It varies everyday.

<br>
<b>getAgileRates.py</b>
<p>
This is a script that is set to run at around 1630hrs daily to retrieve the next day's unit rates (when octopus publishes it at around 1600) using Octopus' REST API. It also retrieves the half-hourly smart meter readings from the previous day. These are then stored into a Pandas Dataframe and pickled into a file.
 </p>
<br>

<b>setMeasureBoiler.py</b>
<p>
This is a script that is set to run automatically at boot (@reboot in crontab) and runs at all times, checking every 30 seconds (adjustable) whether to turn the relays for both hot water and heating on or off depending on the calculated "best time to heat" and the boost timing
  </p>
<br>

<b>scheduleHotWater.py</b>
<p>
This is a script that is set to run daily twice in the evening. This is THE script that does the calculation of "when it is the best time to heat up the hot water tank". It takes the average time taken to heat up the tank in the past 30 days, calculate every 5 minutes block to find the cheapest block of time it would be to do so, and pick the latest cheapest time (latest because you'll want to take the shower before the tank loses heat so that it uses less hot water than when it's colder).
 </p>
