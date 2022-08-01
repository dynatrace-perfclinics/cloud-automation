import os, copy, json, statistics
from typing import Dict
from argparse import ArgumentParser
from utils import handleGet, getFileJSON, handlePost, handlePut
parser = ArgumentParser()

parser.add_argument("-dtUrl", "--dynatrace-url", dest="dtUrl", help="Dynatrace URL (https://*.live.com)", required=True)
parser.add_argument("-dtToken", "--dynatrace-api-token", dest="dtToken", help="Dynatrace API Token", required=True)

parser.add_argument("-identifier", "--identifier", dest="id", help="Id Or Tag of the service/processes to automate release", required=True)
parser.add_argument("-ver", "--version", dest="version", help="Version of the release", required=True)
parser.add_argument("-proj", "--project", dest="project", help="Project of the release", required=True)
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
            if(j == "nonKeyService"):
                header["markdown"] = "## {name}".format(name=serviceRelation[i][j]["name"])
            else:
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
                if(j == "nonKeyService"):
                    tile["visualConfig"]["type"] = "HONEYCOMB"
                    tile["bounds"]["height"] = 304
                    tile["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"] = []
                    for id in serviceRelation[i][j]["id"]:
                        tile["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"].append({"value":id,"evaluator":"IN"})
                else:
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
            if entities["toRelationships"]["runsOn"]:
                entityList["SERVICE"].extend(entities["toRelationships"]["runsOn"])
            if entities["toRelationships"]["isInstanceOf"]:
                entityList["PROCESS_GROUP_INSTANCE"].extend(entities["toRelationships"]["isInstanceOf"])
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
            markdown = "### [{name}]({url}/#serviceOverview;id={id};gtf={timeFrame};gf=all)\n\n- Response Time Threshold : {time} ms".format(name="{name}",url=url,id="{id}",timeFrame=timeFrame,time="{time}")
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
                name=getMetric["result"][0]["data"][0]["dimensions"][0].replace(" ","").replace(".","").replace("*","")
                #try:
                value = statistics.mean(list(filter(None, getMetric["result"][0]["data"][0]["values"])))
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
                    getSlo = handleGet('{url}/api/v2/slo'.format(url=url),api,{'sloSelector':'name("{sloName}")'.format(sloName = slo["name"])})
                    id = getSlo["slo"][0]["id"]
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