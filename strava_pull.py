from oauth2client import file, client, tools
import dateutil.parser
import json
import requests

LOCAL_CREDS_FILE = 'credentials.json'
LOCAL_SECRET_FILE = 'client_secret.json'
SCOPES = "view_private"  # https://developers.strava.com/docs/authentication/

is_celsius = False  # set to True for C, False for F
is_metric = False  # set to True for metric, False for standard
max_pages = None  # set to 1 for quick test or None to get all pages

# todo optimize detail/calorie fetch. Too slow, would be nice to batch or async join :-(
# todo lookup lat/long -> city

# desired order (and inclusion) of columns from Strava's API
COLUMNS_ORDERED = [
    'name',
    'description',
    'type',
    'start_date_local',
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
    "average_watts",
    "weighted_average_watts",
    "kilojoules",
    "average_cadence",
    'id',
]

# fields that require a per-activity lookup
DETAIL_LOOKUP_COLUMNS = {
    "device_name",
    "calories",
    "description"
}

COLUMNS_TO_LABELS = {
    'external_id': 'device_src_id',
    "moving_time": "moving_time min",
    "elapsed_time": "elapsed_time min",
    "average_temp" : "average_temp %s" % ("C" if is_celsius else "F"),
    "elev_high" : "elev_high %s" % ("m" if is_metric else "ft"),
    "elev_low" : "elev_low %s" % ("m" if is_metric else "ft"),
    "total_elevation_gain" : "total_elevation_gain %s" % ("m" if is_metric else "ft"),
    "average_speed" : "average_speed %s" % ("km/h" if is_metric else "mi/h"),
    "max_speed" : "max_speed %s" % ("km/h" if is_metric else "mi/h"),
    "distance": "distance %s" % ("km" if is_metric else "mi"),
    "id" : "url",
    "gear_id" : "gear"
}


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


def call_strava(tok:str, route:str=None):
    """ call strava api and return data as python form"""
    headers = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f'https://www.strava.com/api/v3/{route}', headers=headers)
    if r.status_code == 200:
        return json.loads(r.content)
    else:
        print(f"{r.status_code} Error: {r.content}")
        return


def convert_meters(meters, to_feet:bool=False, to_miles=False, to_km=False):
    if to_feet:
        converted = "%.0f" % (meters * 3.28084)
    elif to_miles:
        converted = "%.2f" % (meters / 1609.34)
    elif to_km:
        converted = "%.2f" % (meters / 1000.0)
    else: # METERS
        converted = "%.0f" % meters
    return converted


def convert_meterspersecond_to_perhour(meters, to_miles:bool=False):
    if not to_miles:  # KM
        converted = "%0.1f" % (meters * 3.6)
    else:  # MILES
        converted = "%0.1f" % (meters * 2.23694)
    return converted


def convert_seconds_to_minutes(seconds):
    converted = "%0.1f" % (seconds/60.0)
    return converted


def convert_celsius_to_fahrenheit(c:int):
    return "%.0f" % (c * 9 / 5 + 32)


def convert_datestr(d:str):
    da = dateutil.parser.parse(d)
    return da.strftime("%Y-%m-%d %H:%M:%S")


def columns_to_values(k:str, v):
    """perform any formatting conversions on columns, based on column name"""
    if v:
        if k in ['total_elevation_gain', 'elev_high', 'elev_low']:
            return convert_meters(v,to_feet=not is_metric)
        elif k in ['average_speed','max_speed']:
            return convert_meterspersecond_to_perhour(v, to_miles=not is_metric)
        elif k in ['distance']:
            return convert_meters(v, to_miles=not is_metric, to_km=is_metric)
        elif k in ['moving_time', 'elapsed_time']:
            return convert_seconds_to_minutes(v)
        elif k == 'id':
            return f"https://www.strava.com/activities/{v}"
        elif k in ["average_temp"]:
            return convert_celsius_to_fahrenheit(v) if not is_celsius else "%.1f" % v
        elif k in ["average_watts", "weighted_average_watts", "kilojoules"]:
            return "%.0f" % v
        elif k  == "start_date_local":
            return convert_datestr(v)
        else:
            return v
    else:
        return ""


def get_activity_detail(tok:str, _id:int):
    # get calories and device name from activity detail
    details_full = call_strava(tok, route=f"/activities/{_id}")
    details = {}
    for k in DETAIL_LOOKUP_COLUMNS:
        details[k] = details_full.get(k,"")
    return details


def get_activities(tok:str):
    """https://developers.strava.com/docs/reference/#api-models-SummaryActivity"""

    # print header row
    for c in COLUMNS_ORDERED:
        if c in COLUMNS_TO_LABELS:
            print (COLUMNS_TO_LABELS[c], end="\t")
        else:
            print(c, end="\t")
    print("")

    # page through strava results
    page = 1
    results = True
    gear_map = {}
    while results:
        results = call_strava(tok, route=f'/athlete/activities?per_page=100&page={page}')
        for item in results:
            details = get_activity_detail(tok,item['id'])
            for k in COLUMNS_ORDERED:
                v = item.get(k,"")
                if k in DETAIL_LOOKUP_COLUMNS:
                    print(details.get(k,""), end="\t")
                elif k == "gear_id" and v:
                    if v not in gear_map:
                         gear = get_gear(token,v)
                         gear_map[v] = gear
                    print(gear_map.get(v,""), end="\t")
                else:
                    print(columns_to_values(k, v), end="\t")
            print()
        if max_pages and max_pages == page:
            break
        page +=1


# def get_athlete(token:str):
#     call_strava(token, route='athletes/1068362/stats?per_page=30')


def get_gear(tok:str, _id:str):
    results = call_strava(tok, f"/gear/{_id}")
    if results:
        return f"{results['brand_name']} {results['model_name']}"
    else:
        return ""


if __name__ == '__main__':
    token = init()
    get_activities(token)

