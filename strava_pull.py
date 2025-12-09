### important - run this as `python3 -u script 100` to be able to use tee or pipe to file

from oauth2client import file, client, tools
import argparse
from datetime import datetime
import dateutil.parser
import logging
import json
import os
import requests
import sys
from typing import Optional

'''
Call Strava API, connect oauth. Download your workout history to tab separated output.
Last saved workout is stored in `last_saved.txt` so future runs only output new activities.
Delete last saved file to download all history.

usage: strava_pull.py [-h] [-p PAGE] [max_results]

positional arguments:
  max_results           How many results to pull (default: 100)

options:
  -h, --help            show this help message and exit
  -p PAGE, --page PAGE  (Optional) starting page number (default: 1)
  
examples:
    python3 strava_pull.py 35  -- pull the first 35 results
    python3 strava_pull.py -p 2 80 -- pull 80 results, starting from page 2
'''

DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = None
is_celsius = False  # set to True for C, False for F
is_metric = False  # set to True for metric, False for standard

LOCAL_CREDS_FILE = 'credentials.json'
LOCAL_SECRET_FILE = 'client_secret.json'
LOCAL_LAST_SAVED_ID_FILE = 'last_saved.txt'
SCOPES = "activity:read_all"  # https://developers.strava.com/docs/authentication/
NOW = datetime.now().strftime("%Y%m%d_%H%M")
OUTPUT_FILE = 'data/strava_%s.tsv'  % NOW
START_PAGE = 1
# todo optimize detail/calorie fetch. Too slow, would be nice to batch or async join :-(
# todo lookup lat/long -> city (i'm not paying for a service to do this)
# todo test single and double quote in description
# todo change tsv to csv
# todo remove incomplete files (with only header row)

# desired order (and inclusion) of columns from Strava's API
COLUMNS_ORDERED = [
    'start_date_local',
    'name',
    'description',
    'type',
    "device_name",
    'distance',
    'total_elevation_gain',
    'average_watts',
    'weighted_average_watts',
    'average_cadence',
    'moving_time',
    'average_speed',
    'max_speed',
    'gear_id',
    "calories",
    'suffer_score',
    'average_heartrate',
    'max_heartrate',
    'average_temp',
    'trainer', # MOVE
    'manual', # MOVE
    'elapsed_time',
    'elev_high',
    'elev_low',
    'athlete_count',
    'location_city',  # MOVE
    'location_state', # MOVE
    'start_latlng',
    'end_latlng',
    'kilojoules',
    'total_photo_count',
    'id'
]

# fields that require a per-activity lookup
DETAIL_LOOKUP_COLUMNS = {
    'device_name',
    'calories',
    'description'
}

#API name to output name mapping
COLUMNS_TO_LABELS = {
    # 'external_id': 'device_src_id',
    'moving_time': 'moving time min',
    'elapsed_time': 'elapsed time min',
    'average_temp': 'average temp %s' % ('C' if is_celsius else 'F'),
    'elev_high': 'elev high %s' % ('m' if is_metric else 'ft'),
    'elev_low': 'elev low %s' % ('m' if is_metric else 'ft'),
    'total_elevation_gain': 'total elevation gain %s' % ('m' if is_metric else 'ft'),
    'average_speed': 'average speed %s' % ('km/h' if is_metric else 'mi/h'),
    'max_speed': 'max speed %s' % ('km/h' if is_metric else 'mi/h'),
    'distance': 'distance %s' % ('km' if is_metric else 'mi'),
    'id': 'url',
    'gear_id': 'gear'
}

DELIMIT_FIELDS = ['name', 'description', 'gear_id', 'device_name', 'type']

def cred_init(force_reset=False):
    # Setup the API oauth token locally, and return access token
    # NOTE: TO CHANGE SCOPES OR REFRESH AUTH, DELETE credentials.json file locally & RERUN
    #store = file.Storage(LOCAL_CREDS_FILE)
    creds = cred_read_local(force_reset)
    if creds:
        if creds.access_token_expired:
            logging.warning("Token expired, attempting refresh")
            creds = cred_refresh(creds) #will repopulate or throw exception
        if creds.access_token:
            return creds.access_token

# read our locally cached creds/token store
def cred_read_local(force_reset=False):
    store = file.Storage(LOCAL_CREDS_FILE)
    creds = store.get()
    if not creds or creds.invalid or force_reset:
        # this will fail if ANY arguments are passed to this python script
        flow = client.flow_from_clientsecrets(LOCAL_SECRET_FILE, SCOPES)
        creds = tools.run_flow(flow, store)
        pass
    return creds


def cred_refresh(credentials):
    import httplib2
    http = credentials.authorize(httplib2.Http())
    credentials.refresh(http)  # refresh our tokens
    return credentials


# manually run this to reauthorize my own key/app if we accidentally delete the
#    authorization on Strava but still have the registered oauth app/API set up
def cred_reauthorize_manual():
    # be sure you remove all parameters to this script before you run it, or it will incorrectly try to read them
    cred_init(True) #todo backup prev credentials.json -> credentials.json.date
    sys.exit()
    # UNDER THE COVERS IT OPENS auth url for human interaction - so this part is NOT needed but shows what is happening
    #url_auth = f"http://www.strava.com/oauth/authorize?client_id={client_id}&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=read_all"
    #url_apps = f"https://www.strava.com/settings/apps"
    # sys.exit(f"1. Open in browser, Authorize, ignore redirect 404:\n{url_auth}\n\n2. then verify in My Apps that 'valer' app is re-enabled\n{url_apps}")

def call_strava(tok: str, route: str=None):
    ''' call strava api and return data as python form'''
    headers = {'Authorization': f'Bearer {tok}'}
    r = requests.get(f'https://www.strava.com/api/v3/{route}', headers=headers)
    if r.status_code == 200:
        return json.loads(r.content)
    else:
        print(f'{r.status_code} Error: {r.content}')
        return


def convert_meters(meters, to_feet: bool=False, to_miles: bool=False, to_km: bool=False):
    if to_feet:
        converted = '%.0f' % (meters * 3.28084)
    elif to_miles:
        converted = '%.2f' % (meters / 1609.34)
    elif to_km:
        converted = '%.2f' % (meters / 1000.0)
    else:  # METERS
        converted = '%.0f' % meters
    return converted


def convert_meterspersecond_to_perhour(meters, to_miles: bool=False):
    if not to_miles:  # KM
        converted = '%0.1f' % (meters * 3.6)
    else:  # MILES
        converted = '%0.1f' % (meters * 2.23694)
    return converted


def convert_seconds_to_minutes(seconds):
    converted = '%0.1f' % (seconds/60.0)
    return converted


def convert_celsius_to_fahrenheit(c: int):
    return '%.0f' % (c * 9 / 5 + 32)


def convert_datestr(d: str):
    da = dateutil.parser.parse(d)
    return da.strftime('%Y-%m-%d %H:%M:%S')


def columns_to_values(k: str, v):
    """perform any formatting conversions on columns, based on column name"""
    if v:
        if k in ['total_elevation_gain', 'elev_high', 'elev_low']:
            return convert_meters(v, to_feet=not is_metric)
        elif k in ['average_speed', 'max_speed']:
            return convert_meterspersecond_to_perhour(v, to_miles=not is_metric)
        elif k in ['distance']:
            return convert_meters(v, to_miles=not is_metric, to_km=is_metric)
        elif k in ['moving_time', 'elapsed_time']:
            return convert_seconds_to_minutes(v)
        elif k == 'id':
            return f'https://www.strava.com/activities/{v}'
        elif k in ['average_temp']:
            return convert_celsius_to_fahrenheit(v) if not is_celsius else '%.1f' % v
        elif k in ['average_watts', 'weighted_average_watts', 'kilojoules']:
            return '%.0f' % v
        elif k == 'start_date_local':
            return convert_datestr(v)
        else:
            return v
    else:
        return ""


def write_last_saved(_id:int = None):
    if _id:
        with open(LOCAL_LAST_SAVED_ID_FILE,'w') as fh:
            fh.write("%s" % _id)


def read_last_saved() -> Optional[int]:
    if os.path.exists(LOCAL_LAST_SAVED_ID_FILE):
        with open(LOCAL_LAST_SAVED_ID_FILE, 'r') as fh:
            data = fh.read()
            id = data.strip()
            if id:
                return int(id)
    return None


def get_activity_detail(tok: str, _id: int):
    # get calories and device name from activity detail
    details_full = call_strava(tok, route=f'/activities/{_id}')
    details = {}
    for k in DETAIL_LOOKUP_COLUMNS:
        details[k] = details_full.get(k, "") or "" #the or changes a defined None (not missing) to empty string too
    return details


def sanitize(output:str, field: str):
    return output
    # TEMP
    if output and field:
        if field in DELIMIT_FIELDS:
            output = output.replace("'","\"") #replace single with double quote
            if output:
                return f"'{output.strip()}'" # single quote delimit long text fields
    return output


def output(str, end="\n", file=sys.stdout):
    print(str, end=end, file=file)  # saved file
    if file != sys.stdout:
        print(str, end=end, file=sys.stdout)  # stdout


def get_activities(tok: str, max_results=None, page=START_PAGE):
    """https://developers.strava.com/docs/reference/#api-models-SummaryActivity"""

    data_written = False
    outfile = OUTPUT_FILE
    if os.path.exists(outfile):
        sys.exit(f"Output file already exists: {outfile}")

    try:
        fh = open(outfile, mode="w")
        last_saved_id = read_last_saved()
        # print header row
        for c in COLUMNS_ORDERED:
            if c in COLUMNS_TO_LABELS:
                output(COLUMNS_TO_LABELS[c], end="\t", file=fh)
            else:
                output(c.replace("_"," "), end="\t", file=fh)
        output("", file=fh)

        page_size = get_page_size(max_results)
        max_pages = get_max_pages(max_results)

        # page through strava results (or until we reach last saved record, if applicable)
        results = True
        gear_map = {}
        most_recent_id = None
        while results:
            results = call_strava(
                tok, route=f'/athlete/activities?per_page={page_size}&page={page}')
            for item in results:
                curr_id = item['id']
                if last_saved_id and last_saved_id == curr_id and not max_results:
                    break  # we've reached known data, exit
                if not most_recent_id:
                    most_recent_id = curr_id
                details = get_activity_detail(tok, curr_id)
                for k in COLUMNS_ORDERED:
                    v = item.get(k, "")
                    if k in DETAIL_LOOKUP_COLUMNS:
                        output(sanitize(details.get(k, ''),k), end='\t', file=fh)
                    elif k == 'gear_id' and v:
                        if v not in gear_map:
                            gear = get_gear(token, v)
                            gear_map[v] = gear
                        output(sanitize(gear_map.get(v, ''),k), end='\t', file=fh)
                    else:
                        output(sanitize(columns_to_values(k, v),k), end="\t", file=fh)
                output("", file=fh)
                data_written = True
            if max_pages and max_pages == page:
                break
            page += 1

        write_last_saved(most_recent_id)
        fh.close()
    except Exception:
        if not data_written:
            cleanup_empty()


def cleanup_empty():
    os.remove(OUTPUT_FILE)


def get_gear(tok: str, _id: str):
    results = call_strava(tok, f"/gear/{_id}")
    if results:
        return f"{results['brand_name']} {results['model_name']}"
    else:
        return ""


def get_page_size(max_results:int):
    if max_results and max_results < DEFAULT_PAGE_SIZE:
        return max_results
    return DEFAULT_PAGE_SIZE


def get_max_pages(max_results:int):
    if not max_results:
        return None  # get all there are to get if not capped
    max_pages,foo = divmod(max_results,DEFAULT_PAGE_SIZE)
    # if 101 results, get 2 pages, if <=100 results, get 1 page
    return max_pages + 1


if __name__ == '__main__':
    max_results = None
    parser = argparse.ArgumentParser(description="Pull Strava activities from API.")
    parser.add_argument("max_results",
                        type=int, default=DEFAULT_PAGE_SIZE,
                        nargs='?',  # `?` means 0 or 1 positional value - OPTIONAL
                        help=f"How many results to pull (default: {DEFAULT_PAGE_SIZE})")
    parser.add_argument(
        "-p", "--page", type=int, default=1,
        help="(Optional) starting page number (default: 1)"
    )
    args = parser.parse_args()
    print(f"Pulling {args.max_results} results starting from page {args.page}")

    token = cred_init()
    get_activities(token, max_results=args.max_results, page=args.page)
