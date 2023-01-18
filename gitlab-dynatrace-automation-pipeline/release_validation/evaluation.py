import json, requests, logging, sys
from argparse import ArgumentParser
from datetime import datetime, timedelta, date

parser = ArgumentParser()

parser.add_argument("-service", "--ca-service", dest="service", help="CA Service", required=True)
parser.add_argument("-stage", "--ca-stage", dest="stage", help="CA Stage", required=True)
parser.add_argument("-project", "--ca-project", dest="project", help="CA Project", required=True)
parser.add_argument("-buildNumber", "--ca-buildNumber", dest="buildNumber", help="CA BuildNumber", required=True)
parser.add_argument("-token", "--ca-token", dest="token", help="CA Token", required=True)
parser.add_argument("-uri", "--ca-url", dest="caUrl", help="CA Url", required=True)
parser.add_argument("-mindiff", dest="minDiff", help="Difference in minutes from start day", required=True)
parser.add_argument("-daydiff", dest="dayDiff", help="Difference in days from start day", required=True)
parser.add_argument("-daystart", dest="dayStart", help="Start day of evaluation", required=True)
#parser.add_argument("-startTime", dest="startTime", help="Start day of evaluation", required=True)
parser.add_argument("-l", "--logging", action="store", choices=["DEBUG","INFO","ERROR"],default="INFO", help="Optional logging levels, default is INFO if nothing is specified")

args = parser.parse_args()

# Logging
logging.basicConfig(stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s",datefmt='%Y-%m-%d %H:%M:%S') #Sets logging format to "[LEVEL] log message"
logger = logging.getLogger('Dynatrace Automation Bootstrap - Release Automation')
logger.setLevel(args.logging)

service = args.service
stage = args.stage
project = args.project
buildNumber = args.buildNumber
token = args.token
caUrl = args.caUrl
minDiff = int(args.minDiff)
dayDiff = int(args.dayDiff)
dayStart = int(args.dayStart)
#startTime = args.startTime

def releasevalidation():
    #pDate = datetime.strptime(startTime, "%Y-%m-%dT%H:%M:%S+01:00")
    cDate = datetime.today() + timedelta(days=-dayDiff)
    #pDate = cDate + timedelta(days=-dayStart)
    pDate = cDate + timedelta(minutes=-minDiff)
    #pDate = pDate + timedelta(minutes=-minDiff)
    logger.info("Start Time: {cDate}".format(cDate = cDate.strftime("%Y-%m-%dT%H:%M:%S")))
    #logger.info("End Time: {pDate}".format(pDate = pDate.strftime("%Y-%m-%dT%H:%M:%S")))
    
    jsonEvent = {
        "gitCommitId":"asdf123f",
        "labels":{
            "buildId": buildNumber,
            "executedBy": "gitLab"
        },
        "start": pDate.strftime("%Y-%m-%dT%H:%M:%S"),
        "end":cDate.strftime("%Y-%m-%dT%H:%M:%S")
    }
    """
    jsonEvent = {
        "gitCommitId":"asdf123f",
        "labels":{
            "buildId": buildNumber,
            "executedBy": "gitLab"
        },
        "start": pDate.strftime("%Y-%m-%dT%H:%M:%S"),
        "timeFrame": "5m"
    }
    """
    uri = "{caUrl}/api/controlPlane/v1/project/{project}/stage/{stage}/service/{service}/evaluation".format(caUrl=caUrl, project = project, stage = stage, service = service)
    header = {
        "accept" : "application/json",
        "x-token" : token,
        "Content-Type" : "application/json"
    }
    logger.info(json.dumps(jsonEvent,indent=2))
    logger.info(handlePost(uri, header, {}, jsonEvent, logger))

def handlePost(url, header, x, y, logger):
    try:
        logger.debug(f"handlePost: {url}")
        logger.debug(json.dumps(y))
        post = requests.post(url, headers=header, params=x, data=json.dumps(y))
        logger.debug(json.dumps(post.json()))
        logger.debug(post.status_code)
        return post.status_code, post.headers
    except requests.exceptions.Timeout as err:
        logger.error(f"The request timed out. Couldn't reach - {url}")
        raise SystemExit(err)
    except requests.exceptions.ConnectionError as err:
        logger.error(f"The URL was malformed - {url}")
        raise SystemExit(err)
    except requests.exceptions.TooManyRedirects as err:
        logger.error(f"The URL was malformed - {url}")
        raise SystemExit(err)
    except Exception as e:
        logger.error(f"Failed to post to the dynatrace url: {url}, with exception: {e}")

if __name__ == "__main__":
    releasevalidation()