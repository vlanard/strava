from oauth2client import file, client, tools
from datetime import datetime
import dateutil.parser
import json
import os
import requests
import sys
from typing import Optional

'''
Call Strava API, connect oauth. Download your workout history to tab separated output.
Last saved workout is stored in `last_saved.txt` so future runs only output new activities.
Delete last saved file to download all history.

Usage: python strava_pull.py [outfilename]

'''

max_pages = None  # set to 1 for quick test or None to get all pages
page_size = 100  # 100
is_celsius = False  # set to True for C, False for F
is_metric = False  # set to True for metric, False for standard

LOCAL_CREDS_FILE = 'credentials.json'
LOCAL_SECRET_FILE = 'client_secret.json'
LOCAL_LAST_SAVED_ID_FILE = 'last_saved.txt'
SCOPES = "view_private"  # https://developers.strava.com/docs/authentication/
OUTPUT_FILE = 'strava_%s.tsv'  % datetime.now().strftime("%Y%m%d_%H%M")

# todo optimize detail/calorie fetch. Too slow, would be nice to batch or async join :-(
# todo lookup lat/long -> city (but not paying)
# todo test single and double quote in description
# todo change tsv to csv

# desired order (and inclusion) of columns from Strava's API
COLUMNS_ORDERED = [
    'start_date_local',
    'name',
    'description',
    'type',
    'distance',
    'moving_time',
    'elapsed_time',
    "calories",
    'total_elevation_gain',
    'elev_high',
    'elev_low',
    'average_speed',
    'max_speed',
    'suffer_score',
    'average_heartrate',
    'max_heartrate',
    'average_temp',
    'athlete_count',
    "device_name",
    'gear_id',
    'location_city',
    'location_state',
    'start_latlng',
    'end_latlng',
    'average_watts',
    'weighted_average_watts',
    'kilojoules',
    'average_cadence',
    'id',
]

# fields that require a per-activity lookup
DETAIL_LOOKUP_COLUMNS = {
    'device_name',
    'calories',
    'description'
}

COLUMNS_TO_LABELS = {
    # 'external_id': 'device_src_id',
    'moving_time': 'moving_time min',
    'elapsed_time': 'elapsed_time min',
    'average_temp': 'average_temp %s' % ('C' if is_celsius else 'F'),
    'elev_high': 'elev_high %s' % ('m' if is_metric else 'ft'),
    'elev_low': 'elev_low %s' % ('m' if is_metric else 'ft'),
    'total_elevation_gain': 'total_elevation_gain %s' % ('m' if is_metric else 'ft'),
    'average_speed': 'average_speed %s' % ('km/h' if is_metric else 'mi/h'),
    'max_speed': 'max_speed %s' % ('km/h' if is_metric else 'mi/h'),
    'distance': 'distance %s' % ('km' if is_metric else 'mi'),
    'id': 'url',
    'gear_id': 'gear'
}

DELIMIT_FIELDS = ['name', 'description', 'gear_id', 'device_name', 'type']

def init():
    # Setup the API oauth token locally, and return access token
    # NOTE: TO CHANGE SCOPES, DELETE credentials.json file locally & RERUN
    store = file.Storage(LOCAL_CREDS_FILE)
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets(LOCAL_SECRET_FILE, SCOPES)
        creds = tools.run_flow(flow, store)
    if creds and creds.access_token:
        return creds.access_token
    return None


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
        details[k] = details_full.get(k, "")
    return details


def sanitize(output:str, field: str):
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


def get_activities(tok: str, outfile: Optional[str]=None):
    """https://developers.strava.com/docs/reference/#api-models-SummaryActivity"""

    if os.path.exists(outfile):
        sys.exit(f"Output file already exists: {outfile}")

    fh = open(outfile, mode="w")
    last_saved_id = read_last_saved()
    # print header row
    for c in COLUMNS_ORDERED:
        if c in COLUMNS_TO_LABELS:
            output(COLUMNS_TO_LABELS[c], end="\t", file=fh)
        else:
            output(c, end="\t", file=fh)
    output("", file=fh)

    # page through strava results (or until we reach last saved record, if applicable)
    page = 1
    results = True
    gear_map = {}
    most_recent_id = None
    while results:
        results = call_strava(
            tok, route=f'/athlete/activities?per_page={page_size}&page={page}')
        for item in results:
            curr_id = item['id']
            if last_saved_id and last_saved_id == curr_id:
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
        if max_pages and max_pages == page:
            break
        page += 1

    write_last_saved(most_recent_id)
    fh.close()


def get_gear(tok: str, _id: str):
    results = call_strava(tok, f"/gear/{_id}")
    if results:
        return f"{results['brand_name']} {results['model_name']}"
    else:
        return ""


if __name__ == '__main__':
    if len(sys.argv) > 1:
        outputfile = sys.argv[1]
    else:
        outputfile = OUTPUT_FILE
    token = init()
    get_activities(token, outputfile)
