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
        return 'service', id;
    elif idSplit in processGroup:
        return 'process_group', id
    elif idSplit in process:
        return 'process_group_instance', id
    else:
        tags = id.split(',')
        entitySelector = ""
        for i in tags:
            entitySelector = entitySelector + "tag({id})".format(id=i)
            entitySelector = entitySelector + ","
        id = entitySelector.rstrip(",")
        return 'tag', id;

def getEntityList(id, type, relation, url, api):
    entityList = {"SERVICE":[],"PROCESS_GROUP_INSTANCE":[]}
    
    if(type != 'tag'):
        entities = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type({type}),entityId({id})".format(type=type,id=id),"from":timeFrame,"fields":relation,"pageSize":500})
    
        if(not entities['entities']):
           print("No entities could be identified with the identifier: {id}".format(id=id))
           return None

        entities = entities['entities'][0]
        if(type == "service" or type == "process_group_instance"):
            relation = relation.split(',')
            if type == "process_group_instance":
                tempRelation = relation[1].split('.')
                start = tempRelation[0]
                end = tempRelation[1]
                if end in entities[start]:
                    entityList[entities["type"]].append({'id' : entities['entityId'],"fromRelationships":{"isInstanceOf":[{"id":entities[start][end][0]["id"],"type":"PROCESS_GROUP"}]}})
            else:
                entityList[entities["type"]].append({'id' : entities['entityId']})
            tempRelation = relation[0].split('.')
            start = tempRelation[0]
            end = tempRelation[1]
            if end in entities[start]:
                tempType = entities[start][end][0]["type"]
                entityList[tempType].extend(entities[start][end])
                if(tempType == "PROCESS_GROUP_INSTANCE"):
                    for i in entityList[tempType]:
                        tempRelation = relation[1].split('.')
                        start = tempRelation[0]
                        end = tempRelation[1]
                        if end in entities[start]:
                            i["fromRelationships"] = {"isInstanceOf": [{"id":entities[start][end][0]["id"],"type":"PROCESS_GROUP"}]}
        else:
            try:
                if entities["toRelationships"]["runsOn"]:
                    entityList["SERVICE"].extend(entities["toRelationships"]["runsOn"])
            except:
                print("No service relationship was identified")
            try:
                if entities["toRelationships"]["isInstanceOf"]:
                    entityList["PROCESS_GROUP_INSTANCE"].extend(entities["toRelationships"]["isInstanceOf"])
                    for i in entityList["PROCESS_GROUP_INSTANCE"]:
                        i["fromRelationships"] = {"isInstanceOf": [{"id":id,"type":"PROCESS_GROUP"}]}
            except:
                print("No process group instance relationship was identified")
    else:
         entities = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(service),{id}".format(id=id),"from":timeFrame,"pageSize":500})
         tempCheck = 0
         if(entities["entities"]):
            entityList["SERVICE"].extend(entities["entities"])
         else:
             tempCheck += 1
             print("No services were found with this tag: {tag}".format(tag=id))
         entities = handleGet('{url}/api/v2/entities'.format(url = url), api, {"entitySelector":"type(process_group_instance),{id}".format(id=id),"from":timeFrame,"pageSize":500, "fields":"fromRelationships.isInstanceOf"})
         if(entities["entities"]):
             entityList["PROCESS_GROUP_INSTANCE"].extend(entities["entities"])
         else:
             tempCheck += 1
             print("No processes were found with this tag: {tag}".format(tag=id))
         if(tempCheck == 2):
            return None

    return entityList

def createSLOs(entityList, url, api):
    metrics = getFileJSON('etc/metrics.json')["dash1"]
    dash = getFileJSON('etc/dashboard.json')
    dash["tiles"][0]["bounds"] = {"top": 0,"left": 0,"width": 684,"height": 38}
    dash["tiles"][0]["markdown"] = "## | ---- Processes --- | --------- SLI -------- | --------------- SLO ------------- |"
    dash["tiles"][1]["bounds"] =  {"top": 0,"left": 684,"width": 1178,"height": 38}
    dash["tiles"][1]["markdown"] = "## | ----- Services ---- | --------- SLI -------- | -------------- SLO --------------- | -------- SLI --------- | ------------ SLO --------------- |"
    slo = getFileJSON('etc/slo.json')
    tile = getFileJSON('etc/tile.json')
    tile["dataExplorer"]["visualConfig"]["type"] = "GRAPH_CHART"
    slo["target"] = sloTarg
    slo["warning"] = sloWarn
    slo["timeframe"] = timeFrame
    for i in entityList:
        if i == "SERVICE":
            top = dash["tiles"][1]["bounds"]["height"]
            left = dash["tiles"][1]["bounds"]["left"]
            markdown = "#### [{name}]({url}/#serviceOverview;id={id};gtf={timeFrame};gf=all)\n\n- Response Time Threshold : **{time} ms**".format(name="{name}",url=url,id="{id}",timeFrame=timeFrame,time="{time}")
        else:
            top = dash["tiles"][0]["bounds"]["height"]
            left = dash["tiles"][0]["bounds"]["left"]
            markdown = "[{name}]({url}/#processdetails;id={id};gtf={timeFrame};gf=all)\n\n- [Link to Release]({url}/ui/releases/{pg}%7C{version}%7C{stage}%7C{product}?gf=all&gtf={timeFrame})".format(name="{name}",url=url,id="{id}",timeFrame=timeFrame, pg = "{pg}", stage = stage, product = product, version = version)
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
            tempMarkdown = copy.deepcopy(tile["markDown"])
            for k in metrics[i]:
                getMetric = handleGet('{url}/api/v2/metrics/query'.format(url = url), api, {"metricSelector":metrics[i][k]["metric"]+":names","entitySelector":entitySelector,"from":timeFrame})
                name = getMetric["result"][0]["data"][0]["dimensions"][0].replace(" ","").replace(".","").replace("*","")
                #try:
                if(not getMetric["result"][0]["data"][0]["values"]):
                    continue
                try:
                    data = getMetric["result"][0]["data"][0]["values"]
                    value = statistics.fmean(list(filter(lambda x: isinstance(x, (int,float)), data)))
                except:
                    continue
                slo["name"] = "{project} {sli} {name}".format(project=project,sli=k,name=name)
                if "response.time" in metrics[i][k]["metric"]:
                    passV = round(value + (value*(passP/100)), 2)
                    slo["metricExpression"] = metrics[i][k]["slo"].format(value=passV)
                else:
                    slo["metricExpression"] = metrics[i][k]["slo"]
                getSlo = handleGet('{url}/api/v2/slo'.format(url=url),api,{'sloSelector':'name("{sloName}")'.format(sloName = slo["name"])})
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
                    tempData = copy.deepcopy(tile["dataExplorer"])
                    tempSlo = copy.deepcopy(tile["slo"])
                    # MarkDown Tile
                    tempMarkdown["bounds"]["left"] = left
                    tempMarkdown["bounds"]["top"] = top
                    if i == "SERVICE" and k == "Response Time":
                        tempMarkdown["markdown"] = markdown.format(name=name,id=entityId,time=passV)
                        dash["tiles"].append(tempMarkdown)
                    elif i == "PROCESS_GROUP_INSTANCE":
                        tempMarkdown["markdown"] = markdown.format(name=name,id=entityId, pg = j["fromRelationships"]["isInstanceOf"][0]["id"])
                        dash["tiles"].append(tempMarkdown)
                    # dataExplorer Tile
                    tempData["bounds"]["top"] = top
                    if(k == "Failure Rate"):
                        tempData["bounds"]["left"] = tempLeft
                    else:
                        tempData["bounds"]["left"] = tempMarkdown["bounds"]["left"] + tempMarkdown["bounds"]["width"]
                    tempData["queries"][0]["metricSelector"] = metrics[i][k]["metricExpression"].format(id=entityId)
                    if k == "Response Time":
                        try:
                            maxValue = round((max(data) + statistics.fmean(data)) / 2,2)
                            if(passV > maxValue):
                                tempData["visualConfig"]["axes"]["yAxes"][0]["max"] = passV
                            else:
                                tempData["visualConfig"]["axes"]["yAxes"][0]["max"] = maxValue
                        except:
                            tempData["visualConfig"]["axes"]["yAxes"][0]["max"] = "AUTO"
                        tempData["visualConfig"]["rules"][0]["unitTransform"] = "MilliSecond"
                        tempData["visualConfig"]["thresholds"][0]["rules"][0]["value"] = 0
                        tempData["visualConfig"]["thresholds"][0]["rules"][2]["value"] = passV
                    else:
                        tempData["visualConfig"]["thresholds"][0]["rules"][0]["value"] = sloTarg
                        tempData["visualConfig"]["thresholds"][0]["rules"][2]["value"] = 0
                    dash["tiles"].append(tempData)
                    # SLO tile
                    tempSlo["bounds"]["top"] = top
                    tempSlo["bounds"]["left"] = tempData["bounds"]["left"] + tempData["bounds"]["width"]
                    tempSlo["assignedEntities"].append(id)
                    tempSlo["metric"] = tempSlo["metric"].format(title=k)
                        

                    tempLeft = tempSlo["bounds"]["left"] + tempSlo["bounds"]["width"]
                    dash["tiles"].append(tempSlo)
                #except:
                #   print("There were no values reported for the following entitiySelector:{selector} \n.......".format(selector=entitySelector))
            top += tile["markDown"]["bounds"]["height"]
    return dash

def dashboardNoSlo(entityList, url, api):
    metrics = getFileJSON('etc/metrics.json')["dash2"]
    dash = getFileJSON('etc/dashboard.json')
    tile = getFileJSON('etc/tile.json')
    dash["tiles"][0]["bounds"] = {"top": 0,"left": 0,"width": 760,"height": 38}
    dash["tiles"][0]["markdown"] = "## | ----- Processes ---- | ------ Availability ----- | ---- CPU ----- | ----- Memory ---- |"
    dash["tiles"][1]["bounds"] =  {"top": 0,"left": 760,"width": 950,"height": 38}
    dash["tiles"][1]["markdown"] = "## | ----- Services ---- | ------ Latency ----- | ----- Traffic -------- | ----- Errors ------- | ---- Saturation --- |"
    tile["dataExplorer"]["visualConfig"]["type"] = "SINGLE_VALUE"
    for i in entityList:
        if i == "SERVICE":
            top = dash["tiles"][1]["bounds"]["height"]
            left = dash["tiles"][1]["bounds"]["left"]
            markdown = "#### [{name}]({url}/#serviceOverview;id={id};gtf={timeFrame};gf=all)\n".format(name="{name}",url=url,id="{id}",timeFrame=timeFrame)
        else:
            top = dash["tiles"][0]["bounds"]["height"]
            left = dash["tiles"][0]["bounds"]["left"]
            markdown = "[{name}]({url}/#processdetails;id={id};gtf={timeFrame};gf=all)\n\n- [Link to Release]({url}/ui/releases/{pg}%7C{version}%7C{stage}%7C{product}?gf=all&gtf={timeFrame})\n\n".format(name="{name}",url=url,id="{id}",timeFrame=timeFrame, pg = "{pg}", stage = stage, product = product, version = version)
        for j in entityList[i]:
            if("id" in j):
                entityId = j["id"]
            elif("entityId" in j):
                entityId = j["entityId"]
            else:
                continue
            entitySelector = "type({type}),entityId({id})".format(type = i, id = entityId)
            tempLeft = 0
            tempMarkdown = copy.deepcopy(tile["markDown"])
            for k in metrics[i]:
                getMetric = handleGet('{url}/api/v2/metrics/query'.format(url = url), api, {"metricSelector":metrics[i][k]["metric"]+":names","entitySelector":entitySelector,"from":timeFrame})
                #try:
                if(not getMetric["result"][0]["data"]):
                    continue
                try:
                    data = getMetric["result"][0]["data"][0]["values"]
                    if(k == "Traffic"):
                        value = sum(list(filter(lambda x: isinstance(x, (int,float)), data)))
                        passV = round(value - (value*(sloTarg/100)), 2)
                    else:
                        value = statistics.fmean(list(filter(lambda x: isinstance(x, (int,float)), data)))
                        passV = round(value + (value*(passP/100)), 2)
                        if k == "Error" and passV > 100:
                            passV = sloTarg
                except:
                    tempLeft = tempLeft + tempData["bounds"]["width"]
                    continue
                name = getMetric["result"][0]["data"][0]["dimensions"][0].replace(" ","").replace(".","").replace("*","")
                print("Working on: entity:{entity}, type:{type}".format(entity=name,type=k))
                tempData = copy.deepcopy(tile["dataExplorer"])
                # MarkDown Tile
                tempMarkdown["bounds"]["left"] = left
                tempMarkdown["bounds"]["top"] = top
                if i == "SERVICE" and k == "Latency":
                    tempMarkdown["markdown"] = markdown.format(name=name,id=entityId)
                    dash["tiles"].append(tempMarkdown)
                if i == "PROCESS_GROUP_INSTANCE" and k == "Availability":
                    tempMarkdown["markdown"] = markdown.format(name=name,id=entityId, pg = j["fromRelationships"]["isInstanceOf"][0]["id"])
                    dash["tiles"].append(tempMarkdown)
                
                # dataExplorer Tile
                tempData["bounds"]["top"] = top
                if k == "Latency" or k == "Availability":
                    tempData["bounds"]["left"] = tempMarkdown["bounds"]["left"] + tempMarkdown["bounds"]["width"]
                else:
                    tempData["bounds"]["left"] = tempLeft
                tempData["queries"][0]["metricSelector"] = metrics[i][k]["metricExpression"].format(id=entityId)
                if(k == "Latency" or k == "Saturation"):
                    tempMarkdown["markdown"] += metrics[i][k]["mda"].format(url = url, id = entityId, passV = round(passV*1000), timeFrame = timeFrame)
                    tempData["visualConfig"]["rules"][0]["unitTransform"] = "MilliSecond"
                if k == "Traffic":
                    tempMarkdown["markdown"] += metrics[i][k]["mda"].format(url = url, id = entityId, timeFrame = timeFrame)
                    tempData["visualConfig"]["thresholds"][0]["rules"][0]["value"] = passV
                    tempData["visualConfig"]["thresholds"][0]["rules"][2]["value"] = 0
                    tempData["queriesSettings"] = {}
                elif k == "Availability":
                    tempData["visualConfig"]["thresholds"][0]["rules"][0]["value"] = sloTarg
                    tempData["visualConfig"]["thresholds"][0]["rules"][2]["value"] = 0
                elif(k == "Error"):
                    tempMarkdown["markdown"] += metrics[i][k]["mda"].format(url = url, id = entityId, timeFrame = timeFrame)
                    tempData["visualConfig"]["thresholds"][0]["rules"][0]["value"] = 0
                    tempData["visualConfig"]["thresholds"][0]["rules"][2]["value"] = 100-sloTarg
                else:
                    tempData["visualConfig"]["thresholds"][0]["rules"][0]["value"] = 0
                    tempData["visualConfig"]["thresholds"][0]["rules"][2]["value"] = passV
                dash["tiles"].append(tempData)
                #except:
                #   print("There were no values reported for the following entitiySelector:{selector} \n.......".format(selector=entitySelector))
                tempLeft = tempData["bounds"]["left"] + tempData["bounds"]["width"]
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
        release["entitySelector"] = release["entitySelector"].format(type = '{type}',id = id)
        if(entityList["PROCESS_GROUP_INSTANCE"]):
            release["entitySelector"] = release["entitySelector"].format(type="PROCESS_GROUP_INSTANCE")
        else:
            release["entitySelector"] = release["entitySelector"].format(type="SERVICE")
        print(json.dumps(release, indent=2))
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
                print(json.dumps(tempRelease, indent=2))
                postRelease(url, api, tempRelease)

def postRelease(url, api, release):
    print("POST Release({name}); Entity:{entity}, Version:{version}, Project:{project}".format(name=release["properties"]["dt.event.deployment.name"], entity=release["entitySelector"], version = release["properties"]["dt.event.deployment.version"],project=release["properties"]["dt.event.deployment.project"]))
    handlePost('{url}/api/v2/events/ingest'.format(url=url), api, {}, release)

def createDashboard(dash, url, api):
    dash["dashboardMetadata"]["name"] = dash["dashboardMetadata"]["name"].format(project = project,version=version,stage=stage,product=product)
    dash["dashboardMetadata"]["shared"] = shared
    dash["dashboardMetadata"]["owner"] = owner
    dash["dashboardMetadata"]["preset"] = preset
    dash["dashboardMetadata"]["tags"][0] = dash["dashboardMetadata"]["tags"][0].format(version=version)
    dash["dashboardMetadata"]["tags"][2] = dash["dashboardMetadata"]["tags"][2].format(project=project)
    dash["dashboardMetadata"]["tags"][3] = dash["dashboardMetadata"]["tags"][3].format(stage=stage)
    dash["dashboardMetadata"]["tags"][4] = dash["dashboardMetadata"]["tags"][4].format(product=product)
    dash["dashboardMetadata"]["dashboardFilter"]["timeframe"] = timeFrame

    #dash["tiles"][2]["markdown"] = dash["tiles"][2]["markdown"].format(url=url,project=project,stage=stage,product=product,)
    getDashboard = handleGet("{url}/api/config/v1/dashboards".format(url=url),api,{"tags":"auto-release","tags":"project:{project}".format(project=project),"tags":"stage:{stage}".format(stage=stage),"tags":"product:{product}".format(product=product)})

    name = "[Release-CA] {project}-{stage}-{product}".format(project = project,stage=stage,product=product)
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
            print("Succesfully updated the Release-CA dasbhoard for the project:{project}, stage:{stage}, product:{product}. Old Version:{oldVersion} -> New Version:{version}".format(project=project,oldVersion=oldVersion,version=version,stage=stage,product=product))

    else:
        resp = handlePost("{url}/api/config/v1/dashboards".format(url=url),api,{},dash)
        if(resp < 400):
            print("Succesfully updated the Release-CA dasbhoard for the project:{project}, stage:{stage}, product:{product}. Old Version:{oldVersion} -> New Version:{version}".format(project=project,oldVersion=oldVersion,version=version,stage=stage,product=product))

def releaseauto():
    api = {'Accept': 'application/json; charset=utf-8', 'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}
    print("Reaching out to Dynatrace ({url})".format(url = url))
    resultCheckId, tempId = checkId(id)

    print("---------------------------------------------------")
    print("Checking for matching entities, the type:{type}, with id: {id}".format(type=resultCheckId, id=tempId))
    entityList = {}
    if('service' == resultCheckId):
        entityList = getEntityList(tempId, resultCheckId, 'fromRelationships.runsOnProcessGroupInstance,fromRelationships.runsOn', url, api)
    elif('process_group_instance' == resultCheckId):
        entityList = getEntityList(tempId, resultCheckId, 'toRelationships.runsOnProcessGroupInstance,fromRelationships.isInstanceOf', url, api)
    elif('process_group' == resultCheckId):
        entityList = getEntityList(tempId, resultCheckId, 'toRelationships.runsOn,toRelationships.isInstanceOf', url, api)
    else:
        entityList = getEntityList(tempId, resultCheckId, '', url, api)
    if(entityList):
        print("Found the following entities: ")
        print(json.dumps(entityList,indent=1))

        print("---------------------------------------------------")
        print("Posting releases with the following values; project:{project}, version:{version}, stage:{stage}, remUrl:{remUrl}".format(project=project, stage=stage, version=version, remUrl=remUrl))
        createRelease(tempId, resultCheckId, url, api, entityList)
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
        elif(not autoDash):
            print("---------------------------------------------------")
            print("Creating Auto Release Dashboard")
            dash = dashboardNoSlo(entityList, url, api)
            createDashboard(dash,url,api)
        else:
            print("To automatically generate a dashboard, add the -dasbhoard or --auto-dashboard parameter")
            print("To automatically generate SLOs, add the -slo or --auto-slo parameter.")
    else:
        print("No entities matched the identifier, not able to post release.")

if __name__ == "__main__":
    releaseauto()