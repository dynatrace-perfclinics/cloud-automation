import json, requests, copy, time
from argparse import ArgumentParser

parser = ArgumentParser()

parser.add_argument("-token", "--token", dest="token", help="DT Token", required=True)
parser.add_argument("-uri", "--url", dest="url", help="DT Url", required=True)
parser.add_argument("-proj", "--project", dest="project", help="Project of the release", required=True)
parser.add_argument("-stage", "--stage", dest="stage", help="Stage of the release", required=True)
parser.add_argument("-product", "--product", dest="product", help="Product of the release", required=True)

args = parser.parse_args()

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
    getTests = handleGet("{url}/api/v1/synthetic/monitors".format(url=url),header,params)
    
    if 'monitors' not in getTests:
        print("No synthetic tests found with the tags: deploy-validation, project:{project}, stage:{stage}, service:{product}".format(project=project, stage=stage, product=product))
        return jsonEvent
    if not getTests["monitors"]:
        print("No synthetic tests found with the tags: deploy-validation, project:{project}, stage:{stage}, service:{product}".format(project=project, stage=stage, product=product))
        return jsonEvent
    for i in getTests["monitors"]:
        id = i["entityId"]
        getTestDetails = handleGet("{url}/api/v1/synthetic/monitors/{id}".format(url=url,id=id),header,{})
        tempMonitor = {"monitorId":id, "locations":[]}
        for j in getTestDetails["locations"]:
            getLocation =  handleGet("{url}/api/v2/synthetic/locations/{id}".format(url=url,id=j),header,{})
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
    print(json.dumps(jsonEvent,indent=2))
    if total == 0:
        exit("No on-demand executions to run")
    batch = {}
    while True:
        batch = handlePost("{url}/api/v2/synthetic/executions/batch".format(url=url), header, jsonEvent)
        print(json.dumps(batch, indent=2))
        if 'batchId' not in batch:
            print("Batch Failed")
            exit()
        k = batch["triggeredCount"]
        if total == k:
            print("Sucessfuly triggered all executions")
            break
        for i in batch["triggeringProblemsDetails"]:
            if i['cause'] == "Monitor disabled" or i["cause"] == "Incorrect location identifier format" or i["cause"] == "Incorrect monitor identifier format" or i["cause"] == "Monitor not found":
                batch["triggeringProblemsCount"] -= 1
        if batch["triggeringProblemsCount"] == 0:
            print("Sucessfuly triggered all executions")
            break
        time.sleep(30)
    time.sleep(3)
    while True:
        result = handleGet("{url}/api/v2/synthetic/executions/batch/{batchid}".format(url=url,batchid = batch["batchId"]), header, {})
        if 'batchStatus' not in result:
            break
        if result["batchStatus"] == "NOT_TRIGGERED":
            print(json.dumps(result,indent=2))
            print("No job was triggered.")
            break
        if result["batchStatus"] == "SUCCESS":
            print(json.dumps(result,indent=2))
            print("Succesully ran the job.")
            break
        print(json.dumps(result,indent=2))
        time.sleep(3)

def handlePost(url, header, y):
    try:
        #print(json.dumps(y))
        post = requests.post(url, headers=header, data=json.dumps(y))
        #print(json.dumps(post.json()))
        post.raise_for_status()
        return post.json()
    except requests.exceptions.Timeout as err:
        print("The request timed out. Couldn't reach - {url}".format(url = url))
        raise SystemExit(err)
    except requests.exceptions.ConnectionError as err:
        print("The URL was malformed - {url}".format(url = url))
        raise SystemExit(err)
    except requests.exceptions.TooManyRedirects as err:
        print("The URL was malformed - {url}".format(url = url))
        raise SystemExit(err)
    except Exception as e:
        print(e)

def handleGet(url, header, x):
    try:
        get = requests.get(url, headers=header, params=x)
        get.raise_for_status()
        resp = get.json()
        return resp
    except requests.exceptions.HTTPError as err:
        raise SystemExit(err)
    except requests.exceptions.Timeout as err:
        print("The request timed out. Couldn't reach - {url}".format(url = url))
        raise SystemExit(err)
    except requests.exceptions.ConnectionError as err:
        print("The URL was malformed - {url}".format(url = url))
        raise SystemExit(err)
    except requests.exceptions.TooManyRedirects as err:
        print("The URL was malformed - {url}".format(url = url))
        raise SystemExit(err)
    except Exception as e:
        print(e)
        return get.text

if __name__ == "__main__":
    deployvalidation()