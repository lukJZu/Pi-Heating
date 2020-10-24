import sys, os, json
from datetime import date, datetime, timedelta
from pathlib import Path
import requests
from urllib.parse import urljoin
import pandas as pd

baseURL = "https://api.octopus.energy"

#getting the octopus details
with open(os.path.join(Path.home(), 'data', 'octopus_keys.json'), 'r') as f:
    octopus_keys = json.load(f)

product_code = octopus_keys['Product Code']
tariff_code = octopus_keys['Tariff Code']
API_KEY = octopus_keys['API_KEY']
MPAN = octopus_keys['MPAN']
meter_serial = octopus_keys['Meter Serial']

def get_consumption():
    #list to store the usage history
    history_list = []

    #setting the period of dates to retrieve
    #including timezone details
    period_from = datetime.combine(date.today(), datetime.min.time()).astimezone() - timedelta(days=40)
    period_to   = datetime.now().astimezone()

    url = urljoin(baseURL, f'v1/electricity-meter-points/{MPAN}/meters/{meter_serial}/consumption/')
    params = {'period_from':period_from.isoformat(), 'period_to':period_to.isoformat(), 'order_by':'period'}
    while url:
        resp = requests.get(url, auth=(API_KEY,''), params=params)
        if resp.status_code != 200:
            break
        
        url = resp.json()['next']
        history_list.extend(resp.json()['results'])

    # print(history_list)
    return history_list


def main():
    #retrieving the agile rates
    resp = requests.get(urljoin(baseURL, f'v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/'))
    rates = resp.json()['results']

    #storing the rates into a dataframe and convert string to datetime
    df = pd.DataFrame(rates)
    df = df.drop(columns = 'value_exc_vat')
    df = df.rename(columns = {'value_inc_vat':'rate'})
    df['valid_from'] = pd.to_datetime(df['valid_from'], utc = True, format = "%Y-%m-%dT%H:%M:%SZ")
    df['valid_to']   = pd.to_datetime(df['valid_to'],   utc = True, format = "%Y-%m-%dT%H:%M:%SZ")
    df = df.sort_values(by='valid_from')

    #storing the rates to csv for hot water scheduling 
    df.to_csv(os.path.join(Path.home(), 'data', 'agileRates.csv'), index=False,
                columns=['valid_from', 'valid_to', "rate"])

    #loading the consumption DF and storing the rates
    df = df.rename(columns={'valid_from': 'interval_start'})
    old_df_pckl = os.path.join(Path.home(), 'data', 'consumptionHistory.df')
    try:
        oldDF = pd.read_pickle(old_df_pckl)
    except FileNotFoundError:
        oldDF = pd.DataFrame(columns=['rate', 'interval_start', 'consumption'])

    #merging the new rates into existing consumption DF
    combined_df = oldDF.merge(df, how='outer', on=['interval_start'])
    combined_df['rate'] = combined_df['rate_x'].fillna(combined_df['rate_y'])
    combined_df = combined_df.drop(columns=['rate_x', 'rate_y', 'valid_to'])

    consumption_history = get_consumption()

    #storing the retrieved data into a df
    conDF = pd.DataFrame(consumption_history)
    #converting string to datetime
    conDF['interval_start'] = pd.to_datetime(conDF['interval_start'], utc = True)

    #merging with the existing consumption DF
    combined_df = combined_df.merge(conDF, how='outer', on=['interval_start'])
    combined_df['consumption'] = combined_df['consumption_x'].fillna(combined_df['consumption_y'])
    combined_df = combined_df.drop(columns=['consumption_x', 'consumption_y', 'interval_end'])

    #overwriting the existing DF
    combined_df.to_pickle(old_df_pckl)


if __name__ == "__main__":
    main()