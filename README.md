# SETUP

This script fetches your strava historical data and outputs to tab separated values.
You can copy into excel, or redirect into a .tsv file and import to a spreadsheet.

This script does not pull segment data, map data, or gpx data.

# Prerequisites
* This script assumes the following are installed
  * python3.7
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

* create your `client_secret.json` file

        cp client_secret.json.sample client_secret.json

* customize your `client_secret.json` file

  * fill in the `client_id` (e.g. 5 digits) assigned to your registered [client application](https://www.strava.com/settings/api)
  * fill in your `client_secret` with the Client Secret assigned to your [client application](https://www.strava.com/settings/api)
  * fill in the `redirect_uri` with the fully qualified url for your Authorization Callback Domain for your [client application](https://www.strava.com/settings/api)
    * e.g. http://localhost:4000

# To run
* load environment

        pipenv shell
        python strava_pull.py

* the first time you run this,
  * the file `credentials.json` will be saved locally
  * a browser will open for the authentication flow

* to modify:
   * edit the `strava_pull` script variables near the top

        is_celsius = False  # set to True for C, False for F
        is_metric = False  # set to True for metric, False for standard
        max_pages = None  # set to 1 for quick test or None to get all pages

   * comment out or reorder columns in `COLUMNS_ORDERED` list

* to exit pipenv environment

        exit