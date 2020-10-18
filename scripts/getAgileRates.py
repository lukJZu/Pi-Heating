import sys, os, json, datetime
import requests
from urllib.parse import urljoin
import pandas as pd
from pathlib import Path

baseURL = "https://api.octopus.energy"
API_KEY = "sk_live_8FpzB32H5PszTPusBxgU5Ppq"

productCode = "AGILE-18-02-21"
tariffCode = "E-1R-AGILE-18-02-21-E"

resp = requests.get(urljoin(baseURL, f'v1/products/{productCode}/electricity-tariffs/{tariffCode}/standard-unit-rates/'))
rates = resp.json()['results']
# resp = requests.get(urljoin(baseURL, f'v1/electricity-meter-points/1460000502417'))
# print(resp.json())
# resp = requests.get(urljoin(baseURL, f'v1/electricity-meter-points/1460000502417/meters/20L3258803/consumption/'), auth=(API_KEY,''))
# print(resp.json())

df = pd.DataFrame(rates)
df = df.drop(columns = 'value_exc_vat')
df = df.rename(columns = {'value_inc_vat':'rate'})
df['valid_from'] = pd.to_datetime(df['valid_from'], utc = True, format = "%Y-%m-%dT%H:%M:%SZ")
df['valid_to']   = pd.to_datetime(df['valid_to'],   utc = True, format = "%Y-%m-%dT%H:%M:%SZ")
df = df.sort_values(by='valid_from')

df.to_csv(os.path.join(Path.home(), 'data', 'agileRates.csv'), index=False)


