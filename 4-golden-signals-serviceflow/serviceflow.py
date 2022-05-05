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

DEPTH = 0
def calculateDepthRelationship(layer: Dict, url: str, api: Dict, index=0, relationships=[], initialLevel=2, levels=[], callee={}):
    global DEPTH
    relationshipCalls = layer['fromRelationships'].get('calls')
    if relationshipCalls is None or index == len(relationshipCalls):
        return [{level: relationship} for (level, relationship) in zip(levels, relationships)]
    else:
        id = relationshipCalls[index]["id"]
        httpResult = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(service),entityId({id})".format(id=id),"from":"now-2h","fields":"fromRelationships,properties.serviceType"})
        if httpResult["entities"]:
            httpResult = httpResult["entities"][0]
            print("Working on relationships of ({name})".format(name = httpResult['displayName']))
            print("---")
            relationships.append({'id': id, 'name' : httpResult['displayName'], 'servicetype': httpResult["properties"]['serviceType'], 'Calledby': layer['displayName']})
            levels.append(initialLevel)
            calculateDepthRelationship(layer, url, api, index + 1, relationships, initialLevel, levels, httpResult)
            initialLevel += 1
            if(initialLevel > DEPTH):
                DEPTH = initialLevel
            return calculateDepthRelationship(httpResult, url, api, 0, relationships, initialLevel, levels, httpResult)
        else:
            return calculateDepthRelationship(httpResult, url, api, 0, relationships, initialLevel, levels, httpResult)

def create_dashboard(serviceRelation,url, timeFrame):
    dashTemp = getFileJSON('etc/dashboard/template.json')
    tiles = getFileJSON('etc/dashboard/service_tiles.json')
    names = ["Latency","Traffic","Errors","Saturation"]
    index = len(serviceRelation)
    left = 0
    for i in range(1,index+1):
        top = 0
        tempIndex = len(serviceRelation[i])
        for j in serviceRelation[i]:
            header = copy.deepcopy(tiles["tileHeader"])
            header["markdown"] = header["markdown"].format(name=serviceRelation[i][j]["name"],url=url,timeFrame=timeFrame,id=serviceRelation[i][j]["id"])
            header["bounds"]["top"] = top
            header["bounds"]["left"] = left
            dashTemp["tiles"].append(header)
            top += header["bounds"]["height"]
            count = 0
            tempLeft = left
            for k in serviceRelation[i][j]["baseline"]:
                tile = copy.deepcopy(tiles["tile"])
                tile["name"] = names[count]
                tile["queries"][0]["metric"] = k
                tile["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"][0]["value"] = serviceRelation[i][j]["id"]
                tile["visualConfig"]["thresholds"][0]["rules"] = serviceRelation[i][j]["baseline"][k]
                tile["bounds"]["top"] = top
                tile["bounds"]["left"] = tempLeft
                dashTemp["tiles"].append(tile)
                tempLeft += tile["bounds"]["width"]
                count += 1
            if i != index:
                arrow = copy.deepcopy(tiles["arrow"])
                arrow["bounds"]["top"] = top
                arrow["bounds"]["left"] = tempLeft
                dashTemp["tiles"].append(arrow)
                tempLeft += arrow["bounds"]["width"]
                top += arrow["bounds"]["height"] 
            else:
                top += tile["bounds"]["height"]
        left = tempLeft
    return dashTemp

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
    if serviceType == "DATABASE":
        metricSelector = "builtin:service.response.time,builtin:service.requestCount.total,builtin:service.dbconnections.failureRate,builtin:service.dbconnections.total"
    else:
        metricSelector = "builtin:service.response.time,builtin:service.requestCount.total,builtin:service.errors.total.rate,builtin:service.cpu.perRequest"
    getMetric = handleGet('{url}/api/v2/metrics/query'.format(url = url), api, {"metricSelector":metricSelector,"resolution":"INF","entitySelector":"type(service),entityId({id})".format(id=id),"from":timeFrame})
    if "result" in getMetric:
        for i in getMetric["result"]:
            if not i["data"]:
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

def clean_t(t, depth, url, api, timeFrame, warnP, passP):
    complete_t = {}
    for i in t:
        for j in i:
            if j in complete_t:
                if i[j]["id"] not in complete_t[j] and "Unexpected service" != i[j]["name"]:
                    complete_t[j][i[j]["id"]] = i[j]
                    complete_t[j][i[j]["id"]]["baseline"] = getBaseline(url, api, i[j]["servicetype"], i[j]["id"], timeFrame, warnP, passP)
            else:
                complete_t[j] = {}
                complete_t[j][i[j]["id"]] = i[j]
                complete_t[j][i[j]["id"]]["baseline"] = getBaseline(url, api, i[j]["servicetype"], i[j]["id"], timeFrame, warnP, passP)
    return complete_t

def serviceflow():
    api = {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}
    print("Reaching out to Dynatrace ({url})".format(url = url))
    resultJ = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(service),entityId({id})".format(id=id),"from":"now-2h","fields":"fromRelationships,properties.serviceType"})
    if resultJ["entities"]:
        resultJ = resultJ["entities"][0]
        svcName = resultJ["displayName"].replace(":","_").replace("/","_").replace(" ","_")
        print("Building Service Flow Relation for ({svc})".format(svc = svcName))
        serviceRelation = calculateDepthRelationship(resultJ, url, api)
        serviceRelation.append({1: {'id': resultJ['entityId'], 'name' : resultJ['displayName'],'servicetype': resultJ["properties"]['serviceType'],'Calledby': None}})
        serviceRelation = clean_t(serviceRelation, DEPTH, url, api, timeFrame, warnP, passP)
        print("***********************************")
        print("Building Service Flow Dashboard Project for ({svc})".format(svc = svcName))
        finalDash = create_dashboard(serviceRelation, url, timeFrame)
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
        print("The service with id:{id}, wasn't found.".format(id=id))

if __name__ == "__main__":
    serviceflow()