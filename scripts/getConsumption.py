import sys, os, json
from datetime import date, datetime, timedelta
from dateutil import tz
from pathlib import Path
import requests
from urllib.parse import urljoin
import pandas as pd

baseURL = "https://api.octopus.energy"

with open(os.path.join(Path.home(), 'data', 'octopus_keys.json'), 'r') as f:
    octopus_keys = json.load(f)

product_code = octopus_keys['Product Code']
tariff_code = octopus_keys['Tariff Code']
API_KEY = octopus_keys['API_KEY']
MPAN = octopus_keys['MPAN']
meter_serial = octopus_keys['Meter Serial']

#list to store the usage history
history_list = []

#setting the period of dates to retrieve
#including timezone details
period_from = datetime.combine(date.today(), datetime.min.time()).astimezone() - timedelta(days=1)
period_to   = datetime.now().astimezone()

url = urljoin(baseURL, f'v1/electricity-meter-points/{MPAN}/meters/{meter_serial}/consumption/')
params = {'period_from':period_from.isoformat(), 'period_to':period_to.isoformat(), 'order_by':'period'}
while url:
    resp = requests.get(url, auth=(API_KEY,''), params=params)
    if resp.status_code != 200:
        break
    
    url = resp.json()['next']
    history_list.extend(resp.json()['results'])


old_df_pckl = os.path.join(Path.home(), 'data', 'consumptionHistory.df')
try:
    oldDF = pd.read_pickle(old_df_pckl)
except FileNotFoundError:
    oldDF = pd.DataFrame(columns=['rate', 'interval_start', 'consumption'])

#storing the retrieved data into a df
conDF = pd.DataFrame(history_list)
#converting string to datetime
conDF['interval_start'] = pd.to_datetime(conDF['interval_start'], utc = True)

#merging with the existing consumption DF
df = oldDF.merge(conDF, how='outer', on=['interval_start'])
df['consumption'] = df['consumption_x'].fillna(df['consumption_y'])
df = df.drop(columns=['consumption_x', 'consumption_y', 'interval_end'])

#overwriting the existing DF
df.to_pickle(old_df_pckl)

# for tupl in df.itertuples():
#     print(tupl)
