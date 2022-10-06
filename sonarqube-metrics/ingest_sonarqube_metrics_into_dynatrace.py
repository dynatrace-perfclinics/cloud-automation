import requests
import logging
import argparse
import json
import regex
import sys

# Arguments
parser = argparse.ArgumentParser(description='Get metrics from a Sonarqube API, parse and format them and send to a Dynatrace endpoint for igestion')
parser.add_argument("-su", "--sonarqube-url", action="store", required=True, help="SonarQube Base URL without trailing slash, Example: https://sonarqube.company.com")
parser.add_argument("-st", "--sonarqube-token", action="store", required=True, help="SonarQube API Token")
parser.add_argument("-c", "--sonarqube-component", action="store", required=True, help="SonarQube Identifier for which project's data will be attained") #Future improvement may be to make this optional or accept more than a single entry
parser.add_argument("-m", "--sonarqube-metrickeys", action="store", required=False, nargs="*", type=str, help="List of values cooresponding to which metricKeys are desired from the SonarQube API, this will default to all available metrics if none are provided")
parser.add_argument("-b", "--sonarqube-branch", action="store", required=False, help="Branch name in SonarQube to pull data for")
parser.add_argument("-d", "--additional-dimensions", action="store", required=False, help="Optional additional dimensions in a comma separated list, without spaces (Ex. component.line_of_business='IT',component.portfolio='')")
parser.add_argument("-du", "--dynatrace-url", action="store", required=True, help="Dynatrace Base URL without trailing slash, Example: https://dynatrace.company.com") #This may be able to be made optional if OneAgent is installed where the script is running
parser.add_argument("-dt", "--dynatrace-token", action="store", required=True, help='Dynatrace token') #This may be able to be made optional if OneAgent is installed where the script is running
parser.add_argument("-i", "--ignore-warnings", action="store",type=bool, default=False, help="Flag used to suppress warnings and allow for hitting servers without good certs, Defaulted to False")
parser.add_argument("-l", "--logging", action="store", choices=["DEBUG","INFO","ERROR"],default="INFO", help="Optional logging levels, default is INFO if nothing is specified")
args = parser.parse_args()

# Logging
logging.basicConfig(stream=sys.stderr, format="[%(levelname)s] %(message)s") #Sets logging format to "[LEVEL] log message"
logger = logging.getLogger('sendSonarqubeMetricsToDynatrace')
logger.setLevel(args.logging)

# Funtion used to query user's SonarQube instance for all available metricKeys
# Returns list of metricKeys
def getAllAvailableSonarqubeMetrics(base_sonarqube_url, sonarqube_token): #This will onlt get up to 500 metrics, if there is a use case for more then it will need to be modified to paginate
    sonarqube_metrics_url = base_sonarqube_url + "/metrics/search"
    all_available_metrics = []
    try:
        logger.info("Querying SonarQube API for all available metrics")
        response = requests.get(sonarqube_metrics_url, auth=requests.auth.HTTPBasicAuth(username=sonarqube_token, password=""), verify=not args.ignore_warnings, params='ps=500')
        logger.debug(f"Response back from SonarQube was: {response}")
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to query SonarQube because of exception: {e}")
    all_metrics_dict = response.json()
    for metric in all_metrics_dict['metrics']:
        all_available_metrics.append(metric['key'])
    return all_available_metrics

# Processes SonarQube Data into ingestable format for Dynatrace endpoint
# Retruns a string of metric data via the format documented here: https://www.dynatrace.com/support/help/extend-dynatrace/extend-metrics/reference/metric-ingestion-protocol#metadata
def processData(data):
    logger.info("Processing Data")
    metrics = ""
    try:
        data_dict = data.json()
        for metric in data_dict['component']['measures']:
            if 'value' in metric.keys() and not regex.compile('(quality.*)|(ncloc_lang.*)|(alert.*)').match(metric['metric']): #avoiding non integer metrics
                metrics += f"custom.sonarqube.component.{metric['metric']},component.name=\'{sonarqube_component}\'{additional_dimensions} {metric['value']}\n"
            else:
                logger.debug(f"This metric is being skipped: {metric}" )
        logger.debug(f"The processed metrics look like this:\n{metrics}")
    except Exception as e:
        logger.error(f"Failed to process data to dynatrace because of {e}")
    return metrics

# Parse and validate arguments
base_sonarqube_url = args.sonarqube_url.strip()
if not regex.compile('^.*/api$').match(base_sonarqube_url): #add /api as needed to the base url provided
    base_sonarqube_url = base_sonarqube_url + "/api"
sonarqube_measures_url = base_sonarqube_url + "/measures/component"
sonarqube_token = args.sonarqube_token.strip()
sonarqube_component = args.sonarqube_component.strip()
base_dynatrace_url = args.dynatrace_url.strip()
if not regex.compile('^.*/api/v2/metrics/ingest$').match(base_dynatrace_url): #add /api/v2/metrics/ingest as needed to the base url provided
    dynatrace_url = base_dynatrace_url + "/api/v2/metrics/ingest"
dynatrace_token = args.dynatrace_token.strip()
if args.sonarqube_metrickeys is None:
    logger.debug(f"No metricKeys provided so getting all available metrics from {base_sonarqube_url}")
    sonarqube_metric_keys = getAllAvailableSonarqubeMetrics(base_sonarqube_url, sonarqube_token)
else:
    sonarqube_metric_keys = args.sonarqube_metrickeys
if args.additional_dimensions is None:
    additional_dimensions = "" if args.sonarqube_branch is None else f",component.branch=\'{args.sonarqube_branch.strip()}\'"
else:
    additional_dimensions = ","+"".join(args.additional_dimensions.strip().split()) if args.sonarqube_branch is None else ","+"".join(args.additional_dimensions.strip().split()) + f",component.branch=\'{args.sonarqube_branch.strip()}\'"
if args.ignore_warnings:
    requests.packages.urllib3.disable_warnings() #supressing warnings

# Querying SonarQube for metrics
logger.info("Querying SonarQube API for component specific metrics")
metrics = ""
still_more_metric_keys = True #this is used to break up requests into smaller chunks as it seems the SonarQube api fails when asked for too many metrics all at once
while still_more_metric_keys:
    if len(sonarqube_metric_keys) > 50:
        metric_keys = ",".join(sonarqube_metric_keys[0:50])
        sonarqube_metric_keys = sonarqube_metric_keys[50:len(sonarqube_metric_keys)]
    else:
        metric_keys = ",".join(sonarqube_metric_keys)
        still_more_metric_keys = False
    if args.sonarqube_branch is not None:
        params = {'component': sonarqube_component, 'branch':args.sonarqube_branch.strip(), 'metricKeys': metric_keys}
    else:
        params = {'component': sonarqube_component, 'metricKeys': metric_keys}
    logger.debug(f"Sending GET to {sonarqube_measures_url} with these params: {params}")
    try:
        response = requests.get(sonarqube_measures_url, auth=requests.auth.HTTPBasicAuth(username=sonarqube_token, password=""), verify=not args.ignore_warnings,params=params)
        logger.debug(f"Response back from SonarQube was: {response.content}")
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to query SonarQube because of exception: {e}")
    metrics += processData(response)

# Send metrics to Dynatrace to ingest
logger.info("Sending Metrics to Dynatrace Endpoint")
logger.debug(f"ALL of the metrics aggregated together being sent:\n{metrics}")
headers = {'accept': '*/*', 'Authorization': f'Api-Token {dynatrace_token}', 'Content-Type': 'text/plain; charset=utf-8',}
logger.debug(f"Sending the above metrics to {dynatrace_url}")
try:
    response = requests.post(dynatrace_url, headers=headers, verify=not args.ignore_warnings, data=metrics)
    logger.debug(f"Response back from dynatrace was: {response.content}")
    response.raise_for_status()
except Exception as e:
    logger.error(f"Failed to ingest data to dynatrace because of exception: {e}")
