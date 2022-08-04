import os, copy, json, statistics, time
from typing import Dict
from argparse import ArgumentParser
from utils import handleGet, getFileJSON, handlePost, handlePut
parser = ArgumentParser()

parser.add_argument("-dtUrl", "--dynatrace-url", dest="dtUrl", help="Dynatrace URL (https://*.live.com)", required=True)
parser.add_argument("-dtToken", "--dynatrace-api-token", dest="dtToken", help="Dynatrace API Token", required=True)

parser.add_argument("-identifier", "--identifier", dest="id", help="Id Or Tag of the service/processes to automate release", required=True)
parser.add_argument("-ver", "--version", dest="version", help="Version of the release", required=True)
parser.add_argument("-proj", "--project", dest="project", help="Project of the release", required=True)
parser.add_argument("-stage", "--stage", dest="stage", help="Stage of the release", required=True)
parser.add_argument("-product", "--product", dest="product", help="Product of the release", required=True)
parser.add_argument("-remUrl", "--remediationUrl", dest="remUrl", help="Remediation URL of the release", required=True)

parser.add_argument("-sloTarg", "--slo-target", dest="sloTarg", help="Target for the SLOs")
parser.add_argument("-sloWarn", "--slo-warning", dest="sloWarn", help="Warning for the SLOs")
parser.add_argument("-slo","--auto-slo",dest="autoSlo",help="Use this to automatically generate SLOs (missing = false)", action="store_false")

parser.add_argument("-pass", "--pass-percent", dest="passP", help="Percent at which to be passed via threshold", required=True)

parser.add_argument("-owner", "--dashboard-owner", dest="owner", help="Owner of the Dynatrace Dashboard", required=True)
parser.add_argument("-shared", "--dashboard-shared", dest="shared", help="Set Dynatrace Dashboard to shared", required=True)
parser.add_argument("-preset", "--dashboard-preset", dest="preset", help="Set Dynatrace Dashboard to preset", required=True)
parser.add_argument("-timeFrame", "--dashboard-timeFrame", dest="timeFrame", help="Time Frame to evaluate thresholds", required=True)
parser.add_argument("-dashboard","--auto-dashboard",dest="autoDash",help="Use this to automatically generate Release Dashboard (missing = false)", action="store_false")


args = parser.parse_args()

url = args.dtUrl
token = args.dtToken

id = args.id
version = args.version
project = args.project
stage = args.stage
product = args.product
remUrl = args.remUrl

if(args.sloTarg):
    sloTarg = int(args.sloTarg)
else:
    sloTarg = 95
if(args.sloWarn):
    sloWarn = int(args.sloWarn)
else:
    sloWarn = 97.5

autoSlo = args.autoSlo

owner = args.owner
shared = args.shared
preset = args.preset
timeFrame = args.timeFrame
passP = int(args.passP)
autoDash = args.autoDash

def checkId(id):
    service = ["SERVICE","service"]
    process = ["PROCESS_GROUP_INSTANCE", "process_group_instance"]
    processGroup = ["process_group","PROCESS_GROUP"]

    idSplit = id.split('-')[0]

    if idSplit in service:
        return 'service';
    elif idSplit in processGroup:
        return 'process_group'
    elif idSplit in process:
        return 'process_group_instance'
    else:
        return 'tag';

def getEntityList(id, type, relation, url, api):
    entityList = {"SERVICE":[],"PROCESS_GROUP_INSTANCE":[]}
    
    if(type != 'tag'):
        entities = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type({type}),entityId({id})".format(type=type,id=id),"from":timeFrame,"fields":relation,"pageSize":500})
    
        if(not entities['entities']):
           print("No entities could be identified with the identifier: {id}".format(id=id))
           return None

        entities = entities['entities'][0]
        if(type == "service" or type == "process_group_instance"):
            entityList[entities["type"]].append({'id' : entities['entityId']})
            relation = relation.split('.')
            start = relation[0]
            end = relation[1]
            if end in entities[start]:
                type = entities[start][end][0]["type"]
                entityList[type].extend(entities[start][end])
        else:
            try:
                if entities["toRelationships"]["runsOn"]:
                    entityList["SERVICE"].extend(entities["toRelationships"]["runsOn"])
            except:
                print("No service relationship was identified")
            try:
                if entities["toRelationships"]["isInstanceOf"]:
                    entityList["PROCESS_GROUP_INSTANCE"].extend(entities["toRelationships"]["isInstanceOf"])
            except:
                print("No process group instance relationship was identified")
    else:
         entities = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(service),tag({id})".format(id=id),"from":timeFrame,"pageSize":500})
         tempCheck = 0
         if(entities["entities"]):
            entityList["SERVICE"].extend(entities["entities"])
         else:
             tempCheck += 1
             print("No services were found with this tag: {tag}".format(tag=id))
         entities = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(process_group_instance),tag({id})".format(id=id),"from":timeFrame,"pageSize":500})
         if(entities["entities"]):
             entityList["PROCESS_GROUP_INSTANCE"].extend(entities["entities"])
         else:
             tempCheck += 1
             print("No processes were found with this tag: {tag}".format(tag=id))
         if(tempCheck == 2):
            return None

    return entityList

def createSLOs(entityList, url, api):
    metrics = getFileJSON('etc/metrics.json')
    dash = getFileJSON('etc/dashboard.json')
    slo = getFileJSON('etc/slo.json')
    tile = getFileJSON('etc/tile.json')
    slo["target"] = sloTarg
    slo["warning"] = sloWarn
    slo["timeframe"] = timeFrame
    rule1 = sloTarg
    rule2 = 0
    for i in entityList:
        if i == "SERVICE":
            top = dash["tiles"][1]["bounds"]["height"]
            left = dash["tiles"][1]["bounds"]["left"]
            markdown = "### [{name}]({url}/#serviceOverview;id={id};gtf={timeFrame};gf=all)\n\n- Response Time Threshold : **{time} ms**".format(name="{name}",url=url,id="{id}",timeFrame=timeFrame,time="{time}")
        else:
            top = dash["tiles"][0]["bounds"]["height"]
            left = dash["tiles"][0]["bounds"]["left"]
            markdown = "### [{name}]({url}/#processdetails;id={id};gtf={timeFrame};gf=all)".format(name="{name}",url=url,id="{id}",timeFrame=timeFrame)
        for j in entityList[i]:
            if("id" in j):
                entityId = j["id"]
            elif("entityId" in j):
                entityId = j["entityId"]
            else:
                continue

            entitySelector = "type({type}),entityId({id})".format(type = i, id = entityId)
            slo["filter"] = entitySelector
            tempLeft = 0
            for k in metrics[i]:
                getMetric = handleGet('{url}/api/v2/metrics/query'.format(url = url), api, {"metricSelector":metrics[i][k]["metric"]+":names","entitySelector":entitySelector,"from":timeFrame})
                name = getMetric["result"][0]["data"][0]["dimensions"][0].replace(" ","").replace(".","").replace("*","")
                #try:
                if(not getMetric["result"][0]["data"][0]["values"]):
                    continue
                try:
                    value = statistics.mean(list(filter(None, getMetric["result"][0]["data"][0]["values"])))
                except:
                    continue
                slo["name"] = "{project} {sli} {name}".format(project=project,sli=k,name=name)
                if "response.time" in metrics[i][k]["metric"]:
                    passV = round(value + (value*(passP/100)), 2)
                    slo["metricExpression"] = metrics[i][k]["slo"].format(value=passV)
                else:
                    slo["metricExpression"] = metrics[i][k]["slo"]
                getSlo = handleGet('{url}/api/v2/slo'.format(url=url),api,{'sloSelector':'name("{sloName}")'.format(sloName = slo["name"])})
                sloStatus = ""
                id = ""
                print("POST SLO; name:{name}, entity:{entity}, type:{type}".format(name=slo["name"],entity=name,type=k))
                if(not getSlo['slo']):
                    sloResp = handlePost('{url}/api/v2/slo'.format(url=url),api,{},slo)
                    time.sleep(.5)
                    getSlo = handleGet('{url}/api/v2/slo'.format(url=url),api,{'sloSelector':'name("{sloName}")'.format(sloName = slo["name"])})
                    try:
                        id = getSlo["slo"][0]["id"]
                    except:
                        print("Not Found, SLO with name: {name}".format(name = slo["name"]))
                else:
                    id = getSlo["slo"][0]["id"]
                    sloResp = handlePut('{url}/api/v2/slo/{id}'.format(url=url, id=id),api,{},slo)
                if(sloResp == 200 or sloResp == 201):
                    print("Sucessfully generated the slo with id:{id} \n......".format(id=id))
                    tempTile = copy.deepcopy(tile)
                    # MarkDown Tile
                    tempTile["markDown"]["bounds"]["left"] = left
                    tempTile["markDown"]["bounds"]["top"] = top
                    if i == "SERVICE" and k == "Response Time":
                        tempTile["markDown"]["markdown"] = markdown.format(name=name,id=entityId,time=passV)
                        dash["tiles"].append(tempTile["markDown"])
                    elif i == "PROCESS_GROUP_INSTANCE":
                        tempTile["markDown"]["markdown"] = markdown.format(name=name,id=entityId)
                        dash["tiles"].append(tempTile["markDown"])
                    # dataExplorer Tile
                    tempTile["dataExplorer"]["bounds"]["top"] = top
                    if(k == "Failure Rate"):
                        tempTile["dataExplorer"]["bounds"]["left"] = tempLeft
                    else:
                        tempTile["dataExplorer"]["bounds"]["left"] = tempTile["markDown"]["bounds"]["left"] + tempTile["markDown"]["bounds"]["width"]
                    tempTile["dataExplorer"]["queries"][0]["metricSelector"] = metrics[i][k]["metricExpression"].format(id=entityId)
                    if k == "Response Time":
                        try:
                            maxValue = round((max(getMetric["result"][0]["data"][0]["values"]) + statistics.mean(getMetric["result"][0]["data"][0]["values"])) / 2,2)
                            tempTile["dataExplorer"]["visualConfig"]["axes"]["yAxes"][0]["max"] = maxValue
                        except:
                            tempTile["dataExplorer"]["visualConfig"]["axes"]["yAxes"][0]["max"] = "AUTO"
                        tempTile["dataExplorer"]["visualConfig"]["rules"][0]["unitTransform"] = "MilliSecond"
                        tempTile["dataExplorer"]["visualConfig"]["thresholds"][0]["rules"][0]["value"] = 0
                        tempTile["dataExplorer"]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = passV
                    else:
                        tempTile["dataExplorer"]["visualConfig"]["thresholds"][0]["rules"][0]["value"] = rule1
                        tempTile["dataExplorer"]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = rule2
                    dash["tiles"].append(tempTile["dataExplorer"])
                    # SLO tile
                    tempTile["slo"]["bounds"]["top"] = top
                    tempTile["slo"]["bounds"]["left"] = tempTile["dataExplorer"]["bounds"]["left"] + tempTile["dataExplorer"]["bounds"]["width"]
                    tempTile["slo"]["assignedEntities"].append(id)
                    tempTile["slo"]["metric"] = tempTile["slo"]["metric"].format(title=k)
                        

                    tempLeft = tempTile["slo"]["bounds"]["left"] + tempTile["slo"]["bounds"]["width"]
                    dash["tiles"].append(tempTile["slo"])
                #except:
                #   print("There were no values reported for the following entitiySelector:{selector} \n.......".format(selector=entitySelector))
            top += tile["markDown"]["bounds"]["height"]
    return dash

def createRelease(id, type, url, api, entityList):
    release = getFileJSON('etc/release.json')
    release["title"] = project + " " + version
    release["properties"]["dt.event.deployment.name"] = project + " " + version
    release["properties"]["dt.event.deployment.project"] = project
    release["properties"]["dt.event.deployment.remediation_action_link"] = remUrl
    release["properties"]["dt.event.deployment.version"] = version
    release["properties"]["dt.event.deployment.release_stage"] = stage
    release["properties"]["dt.event.deployment.release_product"] = product

    if (type == "tag"):
        release["entitySelector"] = release["entitySelector"].format(type = '{type}',id = 'tag({tag})'.format(tag=id))
        if(entityList["PROCESS_GROUP_INSTANCE"]):
            release["entitySelector"] = release["entitySelector"].format(type="PROCESS_GROUP_INSTANCE")
        else:
            release["entitySelector"] = release["entitySelector"].format(type="SERVICE")
        postRelease(url, api, release)
    elif(type == "service"):
        if(entityList["PROCESS_GROUP_INSTANCE"]):
            for i in entityList["PROCESS_GROUP_INSTANCE"]:
                tempRelease = copy.deepcopy(release)
                tempRelease["entitySelector"] = tempRelease["entitySelector"].format(type = 'PROCESS_GROUP_INSTANCE',id = 'entityId({id})'.format(id=i["id"]))
                postRelease(url, api, tempRelease)
        else:
            release["entitySelector"] = release["entitySelector"].format(type = type,id = 'entityId({id})'.format(id=id))
            postRelease(url, api, release)
    elif(type == "process_group_instance"):
        release["entitySelector"] = release["entitySelector"].format(type = type, id = 'entityId({id})'.format(id=id))
        postRelease(url, api, release)
    else:
        if(entityList["PROCESS_GROUP_INSTANCE"]):
            for i in entityList["PROCESS_GROUP_INSTANCE"]:
                tempRelease = copy.deepcopy(release)
                tempRelease["entitySelector"] = tempRelease["entitySelector"].format(type = 'PROCESS_GROUP_INSTANCE',id = 'entityId({id})'.format(id=i["id"]))
                postRelease(url, api, tempRelease)

def postRelease(url, api, release):
    print("POST Release({name}); Entity:{entity}, Version:{version}, Project:{project}".format(name=release["properties"]["dt.event.deployment.name"], entity=release["entitySelector"], version = release["properties"]["dt.event.deployment.version"],project=release["properties"]["dt.event.deployment.project"]))
    handlePost('{url}/api/v2/events/ingest'.format(url=url), api, {}, release)

def createDashboard(dash, url, api):
    dash["dashboardMetadata"]["name"] = dash["dashboardMetadata"]["name"].format(project = project,version=version)
    dash["dashboardMetadata"]["shared"] = shared
    dash["dashboardMetadata"]["owner"] = owner
    dash["dashboardMetadata"]["preset"] = preset
    dash["dashboardMetadata"]["tags"][0] = dash["dashboardMetadata"]["tags"][0].format(version=version)
    dash["dashboardMetadata"]["tags"][2] = dash["dashboardMetadata"]["tags"][2].format(project=project)
    dash["dashboardMetadata"]["dashboardFilter"]["timeframe"] = timeFrame

    getDashboard = handleGet("{url}/api/config/v1/dashboards".format(url=url),api,{"tags":"auto-release","tags":"project:{project}".format(project=project)})
    

    name = "[Release-CA] {project}".format(project = project)
    id = ""
    oldVersion = ""
    for i in getDashboard["dashboards"]:
        if (name in i["name"]):
            oldVersion = i["name"].split(" ")[2]
            id = i["id"]
    if(id):
        dash["id"] = id
        resp = handlePut("{url}/api/config/v1/dashboards/{id}".format(url=url,id=id),api,{},dash)
        if(resp < 400):
            print("Succesfully updated the Release-CA dasbhoard for the project:{project}. Old Version:{oldVersion} -> New Version:{version}".format(project=project,oldVersion=oldVersion,version=version))

    else:
        resp = handlePost("{url}/api/config/v1/dashboards".format(url=url),api,{},dash)
        if(resp < 400):
           print("Succesfully created the Release-CA dasbhoard for the project:{project}. Version:{version}".format(project=project,version=version))


def releaseauto():
    api = {'Accept': 'application/json; charset=utf-8', 'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}
    print("Reaching out to Dynatrace ({url})".format(url = url))
    resultCheckId = checkId(id)

    print("---------------------------------------------------")
    print("Checking for matching entities, the type:{type}, with id: {id}".format(type=resultCheckId, id=id))
    entityList = {}
    if('service' == resultCheckId):
        entityList = getEntityList(id, resultCheckId, 'fromRelationships.runsOnProcessGroupInstance', url, api)
    elif('process_group_instance' == resultCheckId):
        entityList = getEntityList(id, resultCheckId, 'toRelationships.runsOnProcessGroupInstance', url, api)
    elif('process_group' == resultCheckId):
        entityList = getEntityList(id, resultCheckId, 'toRelationships.runsOn,toRelationships.isInstanceOf', url, api)
    else:
        entityList = getEntityList(id, resultCheckId, '', url, api)
    if(entityList):
        print("Found the following entities: ")
        print(json.dumps(entityList,indent=1))

        print("---------------------------------------------------")
        print("Posting releases with the following values; project:{project}, version:{version}, remUrl:{remUrl}".format(project=project, version=version, remUrl=remUrl))
        createRelease(id, resultCheckId, url, api, entityList)
        if(not autoSlo):
            print("---------------------------------------------------")
            print("Creating SLOs")
            dash = createSLOs(entityList, url, api)
            if(dash and not autoDash):
                print("---------------------------------------------------")
                print("Creating Auto Release Dashboard")
                createDashboard(dash, url, api)
            else:
                print("To automatically gernerate Dashboard, add the -dashbord or --auto-dashboard parameter.")
        else:
            print("To automatically generate SLOs, add the -slo or --auto-slo parameter.")
    else:
        print("No entities matched the identifier, not able to post release.")

if __name__ == "__main__":
    releaseauto()