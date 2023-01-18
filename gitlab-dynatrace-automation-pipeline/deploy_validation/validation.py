import json, requests, copy, time, logging, sys
from argparse import ArgumentParser

parser = ArgumentParser()

parser.add_argument("-token", "--token", dest="token", help="DT Token", required=True)
parser.add_argument("-uri", "--url", dest="url", help="DT Url", required=True)
parser.add_argument("-proj", "--project", dest="project", help="Project of the release", required=True)
parser.add_argument("-stage", "--stage", dest="stage", help="Stage of the release", required=True)
parser.add_argument("-product", "--product", dest="product", help="Product of the release", required=True)
parser.add_argument("-l", "--logging", action="store", choices=["DEBUG","INFO","ERROR"],default="INFO", help="Optional logging levels, default is INFO if nothing is specified")

args = parser.parse_args()

# Logging
logging.basicConfig(stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s",datefmt='%Y-%m-%d %H:%M:%S') #Sets logging format to "[LEVEL] log message"
logger = logging.getLogger('Dynatrace Automation Bootstrap - Release Automation')
logger.setLevel(args.logging)


token = args.token
url = args.url
project = args.project
stage = args.stage
product = args.product

def gettests(url, header, project, stage, product, jsonEvent):
    params = {
    "tag":"deploy-validation","tag":"project:{project}".format(project=project),
    "tag":"stage:{stage}".format(stage=stage),
    "tag":"service:{product}".format(product=product)
    }

    total = 0
    getTests = handleGet("{url}/api/v1/synthetic/monitors".format(url=url),header,params, logger)
    
    if 'monitors' not in getTests:
        logger.info("No synthetic tests found with the tags: deploy-validation, project:{project}, stage:{stage}, service:{product}".format(project=project, stage=stage, product=product))
        return jsonEvent
    if not getTests["monitors"]:
        logger.info("No synthetic tests found with the tags: deploy-validation, project:{project}, stage:{stage}, service:{product}".format(project=project, stage=stage, product=product))
        return jsonEvent
    for i in getTests["monitors"]:
        id = i["entityId"]
        getTestDetails = handleGet("{url}/api/v1/synthetic/monitors/{id}".format(url=url,id=id),header,{}, logger)
        tempMonitor = {"monitorId":id, "locations":[]}
        for j in getTestDetails["locations"]:
            getLocation =  handleGet("{url}/api/v2/synthetic/locations/{id}".format(url=url,id=j),header,{}, logger)
            if 'entityId' not in getLocation:
                continue
            tempMonitor["locations"].append(getLocation["entityId"])
            total += 1
        jsonEvent["monitors"].append(tempMonitor)
    return jsonEvent, total

def deployvalidation():
    header = {
    "accept" : "application/json; charset=utf-8",
    "Authorization" : "Api-Token {token}".format(token=token),
    "Content-Type" : "application/json; charset=utf-8"
    }
    jsonEvent = {
    "processingMode": "EXECUTIONS_DETAILS_ONLY",
    "failOnPerformanceIssue": "false",
    "stopOnProblem": "false",
    "monitors": []
    }
    jsonEvent, total = gettests(url, header, project, stage, product, jsonEvent)
    logger.info(json.dumps(jsonEvent,indent=2))
    if total == 0:
        logger.error("No on-demand executions to run")
        exit()
    batch = {}
    while True:
        batch = handlePost("{url}/api/v2/synthetic/executions/batch".format(url=url), header, {}, jsonEvent, logger)
        logger.info(json.dumps(batch, indent=2))
        if 'batchId' not in batch:
            logger.error("Batch Failed")
            exit()
        k = batch["triggeredCount"]
        if total == k:
            logger.info("Sucessfuly triggered all executions")
            break
        for i in batch["triggeringProblemsDetails"]:
            if i['cause'] == "Monitor disabled" or i["cause"] == "Incorrect location identifier format" or i["cause"] == "Incorrect monitor identifier format" or i["cause"] == "Monitor not found":
                batch["triggeringProblemsCount"] -= 1
        if batch["triggeringProblemsCount"] == 0:
            logger.info("Sucessfuly triggered all executions")
            break
        time.sleep(30)
    time.sleep(3)
    while True:
        result = handleGet("{url}/api/v2/synthetic/executions/batch/{batchid}".format(url=url,batchid = batch["batchId"]), header, {}, logger)
        if 'batchStatus' not in result:
            break
        if result["batchStatus"] == "NOT_TRIGGERED":
            logger.info(json.dumps(result,indent=2))
            logger.info("No job was triggered.")
            break
        if result["batchStatus"] == "SUCCESS":
            logger.info(json.dumps(result,indent=2))
            logger.info("Succesully ran the job.")
            break
        logger.info(json.dumps(result,indent=2))
        time.sleep(3)

def handlePost(url, header, x, y, logger):
    try:
        logger.debug(f"handlePost: {url}")
        logger.debug(json.dumps(y))
        post = requests.post(url, headers=header, params=x, data=json.dumps(y))
        logger.debug(json.dumps(post.json()))
        logger.debug(post.status_code)
        return post.json()
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

def handleGet(url, header, x, logger):
    try:
        logger.debug(f"handleGet: {url}")
        logger.debug(json.dumps(x))
        get = requests.get(url, headers=header, params=x)
        get.raise_for_status()
        resp = get.json()
        return resp
    except requests.exceptions.HTTPError as err:
        logger.error({err})
        raise SystemExit(err)
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
        logger.error(f"Failed to get the dynatrace url: {url}, with exception: {e}")
        return get.text

if __name__ == "__main__":
    deployvalidation()