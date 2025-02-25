# SETUP

This script fetches your strava historical data and outputs to tab separated values.
You can copy into excel, or redirect into a .tsv file and import to a spreadsheet.

This script does not pull segment data, map data, or gpx data.

# Prerequisites
* This script assumes the following are installed
  * python3
  * homebrew

# One time setup
* install pipenv if needed

        brew install pipenv
        pipenv shell
        pipenv install

* if you don't have a Strava Client Application, Register for one here: https://www.strava.com/settings/api
   * Tips:
     * Application Name: (whatever you like)
     * Category: Data Importer
     * Website: http://notarealsite.com or your real url
     * Description: developer
     * Authorization Callback Domain: localhost:4000
     * Club (skip this)

* create your `client_secret.json` file

        cp client_secret.json.sample client_secret.json

* customize your `client_secret.json` file

  * fill in the `client_id` (e.g. 5 digits) assigned to your registered [client application](https://www.strava.com/settings/api)
  * fill in your `client_secret` with the Client Secret assigned to your [client application](https://www.strava.com/settings/api)
  * fill in the `redirect_uri` with the fully qualified url for your Authorization Callback Domain for your [client application](https://www.strava.com/settings/api)
    * e.g. http://localhost:4000

# To run
* load environment and run

        pipenv shell
        python3 strava_pull.py

* the first time you run this
  * the file `credentials.json` will be saved locally
  * a browser will open for the authentication flow

* to customize:
   * edit the `strava_pull.py` script variables near the top


            is_celsius = False  # set to True for C, False for F
            is_metric = False  # set to True for metric, False for standard
            max_pages = None  # set to 1 for quick test or None to get all pages


   * comment out or reorder columns in `COLUMNS_ORDERED` list to change output

   * Subsequent runs will only download newest activities. To redownload all activities,
        delete the generated file `last_saved.txt` from this directory.

* to exit pipenv environment

        exit


# Future Things To Do
* lookup lat/long where city is missing
* find a more performant way to gather ride detail, like calories
* what else? drop me a line.
