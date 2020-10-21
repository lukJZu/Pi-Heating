import sys, os, json, datetime
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

resp = requests.get(urljoin(baseURL, f'v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/'))
rates = resp.json()['results']
resp = requests.get(urljoin(baseURL, f'v1/electricity-meter-points/{MPAN}'))
print(resp.json())
resp = requests.get(urljoin(baseURL, f'v1/electricity-meter-points/{MPAN}/meters/{meter_serial}/consumption/'), auth=(API_KEY,''))
print(resp.json())


old_df_pckl = os.path.join(Path.home(), 'data', 'agileRates.df')
try:
    # oldDF = pd.read_json(old_df_json, orient='split')
    oldDF = pd.read_pickle(old_df_pckl)
except FileNotFoundError:
    oldDF = pd.DataFrame()

df = pd.DataFrame(rates)
df = df.drop(columns = 'value_exc_vat')
df = df.rename(columns = {'value_inc_vat':'rate'})
df['valid_from'] = pd.to_datetime(df['valid_from'], utc = True, format = "%Y-%m-%dT%H:%M:%SZ")
df['valid_to']   = pd.to_datetime(df['valid_to'],   utc = True, format = "%Y-%m-%dT%H:%M:%SZ")
df = df.sort_values(by='valid_from')

df.to_csv(os.path.join(Path.home(), 'data', 'agileRates.csv'), index=False,
            columns=['valid_from', 'valid_to', "rate"])
combined_df = pd.concat([oldDF, df], ignore_index=True)
combined_df = combined_df.sort_values(by='valid_from')
combined_df = combined_df.drop_duplicates(subset='valid_from', ignore_index=True)
combined_df.to_pickle(os.path.join(Path.home(), 'data', 'agileRatesHistory.df'))

