import os, copy
from typing import Dict
from argparse import ArgumentParser
from utils import prepareMonaco, createCADashboardProject, handleGet, getFileJSON, clean_t 
parser = ArgumentParser()

parser.add_argument("-dtUrl", "--dynatrace-url", dest="dtUrl", help="Dynatrace URL (https://*.live.com)", required=True)
parser.add_argument("-dtToken", "--dynatrace-api-token", dest="dtToken", help="Dynatrace API Token", required=True)
parser.add_argument("-svcId", "--service-id", dest="svcId", help="Id of the service you are interested in.", required=True)
parser.add_argument("-owner", "--dashboard-owner", dest="owner", help="Owner of the Dynatrace Dashboard", required=True)
parser.add_argument("-shared", "--dashboard-shared", dest="shared", help="Set Dynatrace Dashboard to shared", required=True)
parser.add_argument("-preset", "--dashboard-preset", dest="preset", help="Set Dynatrace Dashboard to preset", required=True)
parser.add_argument("-am","--auto-monaco",dest="autoMonaco",help="Use this to automatically execute monaco to deploy dashboards. (missing = false)", action="store_false")

args = parser.parse_args()

url = args.dtUrl
token = args.dtToken
id = args.svcId
owner = args.owner
shared = args.shared
preset = args.preset
autoMonaco = args.autoMonaco

DEPTH = 0
def calculateDepthRelationship(layer: Dict, url: str, api: Dict, index=0, relationships=[], initialLevel=2, levels=[], callee={}):
    global DEPTH
    relationshipCalls = layer['fromRelationships'].get('calls')
    if relationshipCalls is None or index == len(relationshipCalls):
        return [{level: relationship} for (level, relationship) in zip(levels, relationships)]
    else:
        callRelationship = relationshipCalls[index]
        httpResult = handleGet('{url}/api/v1/entity/services/{id}'.format(url = url, id = callRelationship), api, {})
        print("Working on relationships of ({name})".format(name = httpResult['displayName']))
        print("---")
        relationships.append({'id': callRelationship, 'name' : httpResult['displayName'],'data':[],'servicetype': httpResult['serviceType'], 'Calledby': layer['displayName']})
        levels.append(initialLevel)
        calculateDepthRelationship(layer, url, api, index + 1, relationships, initialLevel, levels, httpResult)
        initialLevel += 1
        if(initialLevel > DEPTH):
            DEPTH = initialLevel
        return calculateDepthRelationship(httpResult, url, api, 0, relationships, initialLevel, levels, httpResult)

def create_dashboard(serviceRelation):
    dashTemp = getFileJSON('etc/dashboard/template.json')
    images = getFileJSON('etc/dashboard/images.json')
    top = dashTemp["tiles"][0]["bounds"]["height"]
    for level in serviceRelation:
        tiles = getFileJSON('etc/dashboard/service_tiles.json')
        tiles["tiles"][0]["image"] = images[int(level)-1]["image"]
        tiles["tiles"][0]["bounds"]["top"] = top
        dashTemp["tiles"].append(tiles["tiles"][0])
        for i in range(1,9):
            temp = copy.deepcopy(tiles["tile"])
            tiles["tiles"][i]["bounds"]["top"] = top
            for j in serviceRelation[level]:
                tiles["tiles"][i]["criteria"].append({"value":j["id"],"evaluator":"IN"})
            temp["bounds"] = tiles["tiles"][i]["bounds"]
            temp["customName"] = tiles["tiles"][i]["customName"]
            temp["name"] = tiles["tiles"][i]["name"]
            temp["queries"][0]["spaceAggregation"] = tiles["tiles"][i]["spaceAggregation"]
            temp["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"] = tiles["tiles"][i]["criteria"]
            temp["queries"][0]["metric"] = tiles["tiles"][i]["metric"]
            temp["visualConfig"]["type"] = tiles["tiles"][i]["type"]
            temp["visualConfig"]["rules"][0]["properties"]["seriesType"] = tiles["tiles"][i]["seriesType"]
            dashTemp["tiles"].append(temp)
        top += tiles["tiles"][0]["bounds"]["height"]
    return dashTemp

def buildProject(name, owner,shared,preset, finalDash):
    dashboardYaml = {'config':[{name:"dashboard.json"}],name:[{"name": "[4-Golden-Signals] {name}-serviceflow".format(name = name)},{"owner":owner},{"shared":shared},{"preset":preset}]}
    
    projectDir = "{name}-serviceflow".format(name = name)

    # replace some special characters we may have in the name and mz
    projectDir = projectDir

    # target directory for dashboards is dashboard
    dashboardDir = "{dir}/dashboard".format(dir = projectDir)

    if not os.path.exists(dashboardDir):
        os.makedirs(dashboardDir)

    createCADashboardProject(dashboardDir, "/dashboard.json", "/dashboard.yaml", dashboardYaml, finalDash)
    return projectDir

def serviceflow():
    api = {'Api-Token': token}
    print("Reaching out to Dynatrace ({url})".format(url = url))
    resultJ = handleGet('{url}/api/v1/entity/services/{id}'.format(url = url, id = id), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {})
    svcName = resultJ["displayName"].replace(":","_").replace("/","_").replace(" ","_")
    print("Building Service Flow Relation for ({svc})".format(svc = svcName))
    serviceRelation = calculateDepthRelationship(resultJ, url, {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)})
    serviceRelation.append({1: {'id': resultJ['entityId'], 'name' : resultJ['displayName'],'servicetype': resultJ['serviceType'], 'data':[], 'Calledby': None}})
    serviceRelation = clean_t(serviceRelation, DEPTH)
    print("***********************************")
    print("Building Service Flow Dashboard Project for ({svc})".format(svc = svcName))
    finalDash = create_dashboard(serviceRelation)
    projectDir = buildProject("{}".format(svcName),owner,shared,preset,finalDash)
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

if __name__ == "__main__":
    serviceflow()