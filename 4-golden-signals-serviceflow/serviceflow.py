import os, copy, json
from typing import Dict
from argparse import ArgumentParser
from utils import prepareMonaco, createCADashboardProject, handleGet, getFileJSON
parser = ArgumentParser()

parser.add_argument("-dtUrl", "--dynatrace-url", dest="dtUrl", help="Dynatrace URL (https://*.live.com)", required=True)
parser.add_argument("-dtToken", "--dynatrace-api-token", dest="dtToken", help="Dynatrace API Token", required=True)
parser.add_argument("-svcId", "--service-id", dest="svcId", help="Id of the service you are interested in.", required=True)
parser.add_argument("-owner", "--dashboard-owner", dest="owner", help="Owner of the Dynatrace Dashboard", required=True)
parser.add_argument("-shared", "--dashboard-shared", dest="shared", help="Set Dynatrace Dashboard to shared", required=True)
parser.add_argument("-preset", "--dashboard-preset", dest="preset", help="Set Dynatrace Dashboard to preset", required=True)
parser.add_argument("-timeFrame", "--dashboard-timeFrame", dest="timeFrame", help="Time Frame to evaluate thresholds", required=True)
parser.add_argument("-warn", "--warn-percent", dest="warnP", help="Percent at which to be warned via threshold", required=True)
parser.add_argument("-pass", "--pass-percent", dest="passP", help="Percent at which to be passed via threshold", required=True)
parser.add_argument("-am","--auto-monaco",dest="autoMonaco",help="Use this to automatically execute monaco to deploy dashboards. (missing = false)", action="store_false")
parser.add_argument("-sre","--sre-tag",dest="sre",help="Use this to only include services tagged with 'sre' as part of the serviceflow.", action="store_false")

args = parser.parse_args()

url = args.dtUrl
token = args.dtToken
id = args.svcId
owner = args.owner
shared = args.shared
preset = args.preset
timeFrame = args.timeFrame
warnP = int(args.warnP)
passP = int(args.passP)
autoMonaco = args.autoMonaco
sre = args.sre

SERVICER = {}
HEIGHT = 0
WIDTH = 0
def calculateDepthRelationship(layer: Dict, url: str, api: Dict, callee: Dict, entitySelector : str, layerSelector : str, startId : str, index=0, initialLevel=2):
    global SERVICER, HEIGHT, WIDTH
    #if index > HEIGHT:
    #    HEIGHT = index
    breakpoint()
    relationshipCalls = layer["entities"][0]['fromRelationships'].get('calls')
    if relationshipCalls is None or index == len(relationshipCalls):
        return None
    else:
        id = relationshipCalls[index]["id"]
        if id+str(initialLevel) in callee:
            return calculateDepthRelationship(layer, url, api, callee, entitySelector, entitySelector, startId, index + 1, initialLevel)
        entitySelector = "type(service),entityId({id}),toRelationships.calls({entitySelector})".format(id = id, entitySelector = entitySelector)
        if sre:
            httpResult = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":entitySelector,"from":"now-2h","fields":"fromRelationships.calls,properties.serviceType"})
        else:
            httpResult = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":entitySelector+",tag(sre)","from":"now-2h","fields":"fromRelationships.calls,properties.serviceType"})
        callee[id+str(initialLevel)] = "1"
        if len(httpResult["entities"]) == 0:
            entitySelector = layerSelector
            calculateDepthRelationship(layer, url, api, callee, entitySelector, entitySelector, startId, index + 1, initialLevel)
        else:
            calculateDepthRelationship(layer, url, api, callee, layerSelector, layerSelector, startId, index + 1, initialLevel)
            temp = httpResult["entities"][0]
            #print("Working on relationships of ({name})".format(name = temp['displayName']))
            #print("---")
            #if initialLevel in SERVICER:
            #    SERVICER[initialLevel][id] = {'id': id, 'name' : temp['displayName'], 'servicetype': temp["properties"]['serviceType'], "baseline": getBaseline(url, api, temp["properties"]['serviceType'], id ,timeFrame,warnP,passP)}
            #else:
            #    SERVICER[initialLevel] = {}
            #    SERVICER[initialLevel][id] = {'id': id, 'name' : temp['displayName'], 'servicetype': temp["properties"]['serviceType'], "baseline": getBaseline(url, api, temp["properties"]['serviceType'], id ,timeFrame,warnP,passP)}          
            #if initialLevel > WIDTH:
            #    WIDTH = initialLevel
            initialLevel += 1
            return calculateDepthRelationship(httpResult, url, api, callee, entitySelector, entitySelector, startId, 0, initialLevel)

def create_dashboard(serviceRelation,url, timeFrame, size):
    dashTemp = getFileJSON('etc/dashboard/template.json')
    if size != "large":
        index = len(dashTemp["bounds"][size])
        for i in range(0,index):
            dashTemp["dashboard"]["tiles"][i]["bounds"] = dashTemp["bounds"][size][i]

    tiles = getFileJSON('etc/dashboard/service_tiles.json')
    if size != "large":
        for i in tiles:
            tiles[i]["tile"]["bounds"] = tiles[i]["bounds"][size]

    names = ["Latency","Traffic","Errors","Saturation"]
    index = len(serviceRelation)
    left = 0
    for i in range(1,index+1):
        top = 0
        for j in serviceRelation[i]:
            header = copy.deepcopy(tiles["tileHeader"])["tile"]
            header["markdown"] = header["markdown"].format(name=serviceRelation[i][j]["name"],url=url,timeFrame=timeFrame,id=serviceRelation[i][j]["id"])
            header["bounds"]["top"] = top
            header["bounds"]["left"] = left
            dashTemp["dashboard"]["tiles"].append(header)
            top += header["bounds"]["height"]
            count = 0
            tempLeft = left
            for k in serviceRelation[i][j]["baseline"]:
                tile = copy.deepcopy(tiles["tile"])["tile"]
                tile["name"] = names[count]
                tile["queries"][0]["metric"] = k
                tile["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"][0]["value"] = serviceRelation[i][j]["id"]
                tile["visualConfig"]["thresholds"][0]["rules"] = serviceRelation[i][j]["baseline"][k]
                tile["bounds"]["top"] = top
                tile["bounds"]["left"] = tempLeft
                dashTemp["dashboard"]["tiles"].append(tile)
                tempLeft += tile["bounds"]["width"]
                count += 1
            if i != index:
                arrow = copy.deepcopy(tiles["arrow"])["tile"]
                arrow["bounds"]["top"] = top
                arrow["bounds"]["left"] = tempLeft
                dashTemp["dashboard"]["tiles"].append(arrow)
                tempLeft += arrow["bounds"]["width"]
                top += arrow["bounds"]["height"] 
            else:
                top += tile["bounds"]["height"]
        left = tempLeft
    return dashTemp["dashboard"]

def buildProject(name, owner,shared,preset,timeFrame, finalDash):
    dashboardYaml = {'config':[{name:"dashboard.json"}],name:[{"name": "[4-Golden-Signals] {name}-serviceflow".format(name = name)},{"owner":owner},{"shared":shared},{"preset":preset},{"timeFrame":timeFrame}]}
    projectDir = "{name}-serviceflow".format(name = name)
    # replace some special characters we may have in the name and mz
    projectDir = projectDir
    # target directory for dashboards is dashboard
    dashboardDir = "{dir}/dashboard".format(dir = projectDir)
    if not os.path.exists(dashboardDir):
        os.makedirs(dashboardDir)
    createCADashboardProject(dashboardDir, "/dashboard.json", "/dashboard.yaml", dashboardYaml, finalDash)
    return projectDir

def getBaseline(url, api, serviceType, id, timeFrame, warnP, passP):
    baseline = {}
    if serviceType == "DATABASE_SERVICE":
        metricSelector = "builtin:service.response.time,builtin:service.requestCount.total,builtin:service.dbconnections.failureRate,builtin:service.dbconnections.total"
    else:
        metricSelector = "builtin:service.response.time,builtin:service.requestCount.total,builtin:service.errors.total.rate,builtin:service.cpu.perRequest"
    getMetric = handleGet('{url}/api/v2/metrics/query'.format(url = url), api, {"metricSelector":metricSelector,"resolution":"INF","entitySelector":"type(service),entityId({id})".format(id=id),"from":timeFrame})
    if "result" in getMetric:
        for i in getMetric["result"]:
            if not i["data"]:
                if serviceType != "DATABASE":
                    base = None
                    passV = None
                    warnV = None
                    rules = [{"color": "#7dc540"},{"color": "#f5d30f"},{"color": "#dc172a"}]
            else:
                base = i["data"][0]["values"][0]
                if base == 0:
                    if i["metricId"] in "builtin:service.errors.total.rate,builtin:service.dbconnections.failureRate":
                        passV = passP
                        warnV = warnP
                        rules = [{"value": 0,"color": "#7dc540"},{"value": passV,"color": "#f5d30f"},{"value": warnV,"color": "#dc172a"}]
                else:
                    if i["metricId"] in "builtin:service.response.time,builtin:service.cpu.perRequest,builtin:service.errors.total.rate,builtin:service.dbconnections.failureRate":
                        passV = base + (base*(passP/100))
                        warnV = base + (base*(warnP/100))
                        rules = [{"value": 0,"color": "#7dc540"},{"value": passV,"color": "#f5d30f"},{"value": warnV,"color": "#dc172a"}]
                    else:
                        passV = base - (base*(passP/100))
                        warnV = base - (base*(warnP/100))
                        rules = [{"value": warnV,"color": "#7dc540"},{"value": passV,"color": "#f5d30f"},{"value": 0,"color": "#dc172a"}]
            baseline[i["metricId"]] = rules
    return baseline

def checkSize(height, width):
    if height <= 22 and width <= 5:
        return "large"
    elif height <= 26 and width <= 7:
        return "medium"
    elif height<= 33 and width <= 9: 
        return "small"
    else:
        print("The serviceflow is too big to dashboard")
        return None

def serviceflow():
    global SERVICER,HEIGHT,WIDTH
    api = {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}
    print("Reaching out to Dynatrace ({url})".format(url = url))
    if sre:
        resultJ = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(service),entityId({id})".format(id=id),"from":"now-2h","fields":"fromRelationships.calls,properties.serviceType"})
    else:
        resultJ = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(service),entityId({id})".format(id=id),"from":"now-2h","fields":"fromRelationships.calls,properties.serviceType"})
    if resultJ["entities"]:
        displayName = resultJ["entities"][0]["displayName"]
        entityId = resultJ["entities"][0]["entityId"]
        prop = resultJ["entities"][0]["properties"]["serviceType"]

        svcName = displayName.replace(":","_").replace("/","_").replace(" ","_").replace("*","_").replace(".","_")
        print("Building Service Flow Relation for ({svc})".format(svc = svcName))
        callee = {entityId:"1"}
        entitySelector = "type(service),entityId({id})".format(id=entityId)
        calculateDepthRelationship(resultJ, url, api, callee, entitySelector,entitySelector, entityId)
        SERVICER[1] = {}
        SERVICER[1][entityId] = {'id': entityId, 'name' : displayName,'servicetype': prop,'Calledby': None, "baseline" : getBaseline(url, api, prop, entityId,timeFrame,warnP,passP)}
        print("height: {h}, width: {w}".format(h=HEIGHT,w=WIDTH))
        print("***********************************")
        size = checkSize(HEIGHT, WIDTH)
        if not size:
            exit()
        print("Building Service Flow Dashboard Project for ({svc})".format(svc = svcName))
        finalDash = create_dashboard(SERVICER, url, timeFrame, size)
        projectDir = buildProject("{}".format(svcName),owner,shared,preset,timeFrame,finalDash)
        print("***********************************")
    
        print("Testing Auto Monaco")
        if not autoMonaco:
            print("")
            prepareMonaco(projectDir)
        else:
            print("")
            print("Finished! Review ({projectDir}) and run:".format(projectDir=projectDir))
            print(r'monaco --environments=environments.yaml {projectDir}/'.format(projectDir=projectDir))
        print("***********************************")
    else:
        print("The service with id:{id}, wasn't found.OR there hasn't been traffic in the last 2 hours.".format(id=id))

if __name__ == "__main__":
    serviceflow()