import requests, json, os, yaml, copy, subprocess, base64
from argparse import ArgumentParser
from statistics import mean
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

parser = ArgumentParser()

parser.add_argument("-v", "--verify", dest="verify", help="Verify SSL Cert. (missing = true)", action='store_false')
parser.add_argument("-am","--auto-monaco",dest="autoMonaco",help="Use this to automatically execute monaco to deploy dashboards. (missing = false)", action="store_false")
parser.add_argument("-aca","--auto-cloud-automation",dest="autoCloudAutomation",help="Use this to automatically setup a CloudAutomation Project (missing = false)", action="store_false")
parser.add_argument("-caTenant", "--cloud-automation-tenant", dest="caTenant", help="CloudAutomation Tenant", required=True)
parser.add_argument("-caToken", "--cloud-automation-token", dest="caToken", help="CloudAutomation Token", required=True)
parser.add_argument("-dtUrl", "--dynatrace-url", dest="dtUrl", help="Dynatrace URL (https://*.live.com)", required=True)
parser.add_argument("-dtToken", "--dynatrace-api-token", dest="dtToken", help="Dynatrace API Token", required=True)

args = parser.parse_args()

verifySSL = args.verify
autoMonaco = args.autoMonaco
autoCloudAutomation = args.autoCloudAutomation
caTenant = args.caTenant
caToken = args.caToken
url = args.dtUrl
token = args.dtToken

caBaseUrl = "https://{caTenant}.cloudautomation.{x}".format(caTenant=caTenant,x=url.split(".",1)[1])

def main():
    base = getFileJSON("config/base.json")
    config = {
            "generic":getFileJSON("config/generic.json"), 
            "nodejs":getFileJSON("config/nodejs.json"), 
            "go": getFileJSON("config/go.json"), 
            "java":getFileJSON("config/java.json"),
            "dotnet":getFileJSON("config/dotnet.json")
            }
    
    dash = getFileYAML("config.yaml")
    ca = {}
    if dash:
        for j in dash["dashboards"]:
                if ('automation' not in j and 'dashboard' not in j) or ('mzName' not in j and 'application' not in j) or ('mzName' in j and 'application' in j):
                    print("Requirements not met. The config needs at most the following parameters: \nmzName:'MZNAME'\ndashboard:\n   owner:'OWNER'\nautomation:\n   project:'CAPROJECT'\n   stage:'CASTAGE'\n   service:'CASERVICE'")
                    print("OR")
                    print("application:'APPNAME'\ndashboard:\n   owner:'OWNER'\nautomation:\n   project:'CAPROJECT'\n   stage:'CASTAGE'\n   service:'CASERVICE'")
                    continue
                else:
                    project = j["automation"]["project"]
                    stage = j["automation"]["stage"]
                    service = j["automation"]["service"]
                    addToCa(ca, project, stage, service)
                    technology = validateInput(j, 'technology', 'generic')
                    owner = j["dashboard"]["owner"]
                    timeFrame = validateInput(j["dashboard"],'timeFrame', 'now-1d')
                    preset = validateInput(j["dashboard"],'preset', 'false')
                    shared = validateInput(j["dashboard"],'shared', 'false')
                    total_pass = validateInput(j, 'total_pass', '80%')
                    total_warn = validateInput(j, 'total_warn', '60%')
                    baseline = validateInput(j, 'baseline', {"app_pass":5,"app_warn":10,"service_pass":5,"service_warn":10,"infra_pass":20,"infra_warn":25})
                    weight = validateInput(j, "weight",{"app":1,"service":1,"infra":1})
                    keySli = validateInput(j, "keySli",{"app":"false","service":"false","infra":"false"})

                    print("Reaching out to Dynatrace Environment - ({apiurl})".format(apiurl=url))
                    tempDash = copy.deepcopy(base)
                    if 'application' in j:
                        appId = getApplication(url, token, j['application'], timeFrame)
                        if not appId or len(appId["entities"]) != 1:
                            print("No application was found with the name: {app}".format(app = j["application"]))
                            print("***********************************")
                            continue
                        if 'error' in appId:
                            print("Couldn't compelte request. {error}".format(error = appId["error"]))
                            print("***********************************")
                            continue
                        else:
                            print("Validated Application ({app}) with id={id}".format(app=j["application"], id = appId["entities"][0]["entityId"]))
                            print("***********************************")
                            topUa = getTopUA(url, token, j['application'], timeFrame)
                            num, count = configAppDash(tempDash,topUa)
                            entitySelector = "type(application_method),entityId({id}),fromRelationShip.isApplicationMethodOf(type(application),entityName({app}))".format(app=j["application"], id="{id}")
                            finalDash, metricKey = calculatePass(tempDash,entitySelector, count,num,url,token,timeFrame,'', j["application"],baseline,weight,keySli)
                            s = finalDash["dashboardMetadata"]["name"].format(project = project, stage = stage, service = service)
                            dashboardYaml = {'config':[{project:"dashboard.json"}],project:[{"name":s},{"owner":owner},{"shared":shared},{"timeFrame":timeFrame},
                                                                  {"preset":preset},{"project":project},{"stage":stage},{"service":service},
                                                                  {"total_pass":total_pass},{"appName":j['application']},{"total_warn":total_warn},{"caUrl":caBaseUrl + "/bridge/project/{name}/service".format(name=project)}]}
                            del finalDash["dashboardMetadata"]["dashboardFilter"]["managementZone"]

                            projectDir = buildProject(finalDash, metricKey, dashboardYaml, project, stage, service)
                    else:
                        mzName = j["mzName"]
                        mzId = getMzId(mzName, url, token)
                        if not mzId:
                            print("The mzName : {mz} is invalid. It didn't match any existing mz in the env: {name}".format(mz=mzName,name=url))
                            print("***********************************")
                            continue
                        if 'error' in mzId:
                            print("Couldn't compelte request. {error}".format(error = mzId["error"]))
                            print("***********************************")
                            continue
                        print("Validated Management Zone ({mzName}) with id={mzId}".format(mzName=mzName,mzId=mzId))
                        print("***********************************")
                        entitySelector = "type({type}),mzName({mzName})".format(mzName = mzName, type = "{type}")
                        tempDash["tiles"].extend(config[technology]["dash"])
                        finalDash, metricKey = calculatePass(tempDash,entitySelector,copy.deepcopy(config[technology]["count"]),config[technology]["num"],url,token,timeFrame,mzName,'',baseline,weight,keySli)       
                        s = finalDash["dashboardMetadata"]["name"].format(project = project, stage = stage, service = service)
                        dashboardYaml = {'config':[{project:"dashboard.json"}],project:[{"name":s},{"owner":owner},{"shared":shared},{"timeFrame":timeFrame},
                                        {"preset":preset},{"project":project},{"stage":stage},{"service":service},
                                        {"mzId":mzId}, {"mzName":mzName},{"total_pass":total_pass},
                                        {"total_warn":total_warn},{"caUrl":caBaseUrl + "/bridge/project/{name}/service".format(name=project)}]}
                        projectDir = buildProject(finalDash, metricKey, dashboardYaml, project, stage, service)
                    print("***********************************")
                    print("Testing Auto Monaco")
                    if not autoMonaco:
                        print("")
                        prepareMonaco(projectDir)
                    else:
                        print("")
                        print("Finished! Review ({projectDir}) and run:".format(projectDir=projectDir))
                        print(r'monaco --environments=environments.yaml -p={projectDir}/'.format(projectDir=projectDir))
                    print("***********************************")

        print("Testing Auto Cloud Automation")
        if not autoCloudAutomation:
                print("Reaching out to Cloud Automation - ({caBaseUrl})".format(caBaseUrl = caBaseUrl))
                prepareCA(ca)
        else:
            print("Before the SLI Evaluation can be ran, create the cloud automation project with stage and service")
        print("***********************************")
    else:
            print("Add the dashboard configurations you'd like a dashboard created for in config/config.yaml")

def validateInput(j, x, default):
    if x not in j:
        return default
    else:
        return j[x]

def getApplication(url, token, app, timeFrame):
    entitySelector = "type(application),entityName({app})".format(app=app)
    resp = handleGet("{url}/api/v2/entities".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {"from":timeFrame,"entitySelector":entitySelector})
    return resp

def getTopUA(url, token, app, timeFrame):
    ua = []
    tempData = []
    getUAType("xhr",app, tempData, url, token, timeFrame)
    getUAType("load",app, tempData, url, token, timeFrame)
    tempData = sorted(tempData, key = lambda i: i["values"][0],reverse=True)
    for i in range(10):
        try:
            if tempData[i]:
                ua.append(tempData[i])
        except:
            pass
    return ua

def getUAType(type, app, tempData, url, token, timeFrame):
    entitySelector = "type(application_method),fromRelationShip.isApplicationMethodOf(type(application),entityName({app}))".format(app=app)
    metric = "builtin:apps.web.action.count.({type}).browser:splitBy(dt.entity.application_method):sort(value(avg,descending)):limit(10):names".format(type=type)
    resp = handleGet("{url}/api/v2/metrics/query".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {"from":timeFrame,"resolution":"inf","metricSelector":metric,"entitySelector":entitySelector})
    if 'error' in resp:
        print("Couldn't complete request. {error}".format(error=resp["error"]))
        print("***********************************")
        exit()
    if resp["result"][0]["data"]:
        for i in resp["result"][0]["data"]:
            i["type"] = type
        tempData.extend(resp["result"][0]["data"])

def configAppDash(tempDash, topUa):
    tempGraph = []
    tempSing = []
    app = getFileJSON("config/app.json")
    tempDash["tiles"].extend(app["dash"])
    tempSing.extend(app["app_sing"])
    tempGraph.extend(app["app_graph"])
    top = app["ua_sing"][0]["bounds"]["top"]
    num = 1
    for i in topUa:
        name = i["dimensionMap"]["dt.entity.application_method.name"]
        id = i["dimensionMap"]["dt.entity.application_method"]
        type = i["type"]
        tempUaGraph = copy.deepcopy(app["ua_graph"])
        tempUaSing = copy.deepcopy(app["ua_sing"])
        tempUaMark = copy.deepcopy(app["ua_mark"])
        tempUaMark[0]["markdown"] = tempUaMark[0]["markdown"].format(name = name)
        tempUaMark[0]["bounds"]["top"] = top
        tempDash["tiles"].extend(tempUaMark)
        app["count"] += 1
        tempTop = 0
        for j in range(0,4):
            if '{type}' in tempUaSing[j]["queries"][0]["metric"]:
                tempUaSing[j]["queries"][0]["metric"] = tempUaSing[j]["queries"][0]["metric"].format(type=type)
            tempUaSing[j]["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"][0]["value"] = tempUaSing[j]["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"][0]["value"].format(id = id)
            tempUaSing[j]["bounds"]["top"] = top
            if j == 0:
                tempTop = top + tempUaSing[j]["bounds"]["height"]
            tempUaGraph[j]["name"] = tempUaGraph[j]["name"].format(num=num,cond="{cond}")
            if '{type}' in tempUaGraph[j]["queries"][0]["metric"]:
                tempUaGraph[j]["queries"][0]["metric"] = tempUaGraph[j]["queries"][0]["metric"].format(type=type)
            tempUaGraph[j]["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"][0]["value"] = tempUaGraph[j]["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"][0]["value"].format(id = id)
            tempUaGraph[j]["bounds"]["top"] = tempTop
            if j == 3:
                top = tempTop + tempUaGraph[j]["bounds"]["height"]
            app["num"] += 1
            app["count"] += 1
        num += 1
        tempGraph.extend(tempUaGraph)
        tempSing.extend(tempUaSing)
    tempDash["tiles"].extend(tempSing)
    tempDash["tiles"].extend(tempGraph)

    return app["num"], app["count"]

def addToCa(ca, project, stage, service):
    if project in ca:
        if stage in ca[project]["stage"]:
            ca[project]["stage"][stage] += 1
        else:
            ca[project]["stage"][stage] = 1
        if service in ca[project]["service"]:
            ca[project]["service"][service] += 1
        else:
            ca[project]["service"][service] = 1
    else:
        ca[project] = {"stage":{stage:1},"service":{service:1}}

def prepareCA(ca):
    for i in ca:
        project = i
        service = ""
        for k in ca[i]["service"]:
            service = k
            stage = ""
            for j in ca[i]["stage"]:
                stage = j
                print("Working on Project:{project}, Stage:{stage}, Service:{service}".format(project=project,stage=stage,service=service))
                check = handleGet(caBaseUrl + "/api/controlPlane/v1/project/{project}/stage/{stage}/service/{service}".format(project=project,stage=stage,service=service),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{})
                if "message" not in check:
                    if '401 Authorization Required' in check:
                        print("The Cloud Automation Token ({caToken}) is invalid".format(caToken = caToken))
                        continue
                    print("Finished! The Cloud Automation Project:{project}, exists with Stage:{stage}, Service:{service}".format(project=project,stage=stage,service=service))
                    print("..............................")
                else:
                    if "service not found" in check["message"]:
                        print("Service not Found - Creating Service ({service}) for Project ({project})".format(service=service,project=project))
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project/{project}/service".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"serviceName":service})
                    elif "stage not found" in check["message"]:
                        #print("Stage not Found - Creating Stage ({stage}) with Service ({service}) for Project ({project})".format(stage=stage, service=service,project=project))
                        print("Cloud Automation Doesn't currently supported altering of stages - error on {project}".format(project=project))
                        #caProject = handleGet(caBaseUrl + "/api/controlPlane/v1/project/{project}".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{})
                        #shipyard = yaml.safe_load(caProject["shipyard"])
                        #shipyard["spec"]["stages"].append({"name":stage,"sequences":[{"tasks":[{"name":"evaluation","properties":None}]}]})
                        #shipyard = json.dumps(shipyard)
                        #handlePut(caBaseUrl + "/api/controlPlane/v1/project",{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"name":project, "shipyard":str(base64.b64encode(shipyard.encode("utf-8")),"utf-8")})
                        #handlePost(caBaseUrl + "/api/controlPlane/v1/project/{project}/service".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"serviceName":service})
                    elif "project not found" in check["message"]:
                        shipyard = createShipyard(project, ca[project]["stage"])
                        shipyard = json.dumps(shipyard)
                        dynatraceConf = json.dumps(getFileYAML("dynatrace.conf.yaml"))
                        print("Project not Found - Creating Project ({project}) with Stage ({stage}) and Service ({service})".format(stage=json.dumps(ca[project]["stage"]), service=service,project=project))
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project",{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"name":project, "shipyard":str(base64.b64encode(shipyard.encode("utf-8")),"utf-8")})
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project/{project}/service".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"serviceName":service})
                        handlePut(caBaseUrl + "/api/configuration-service/v1/project/{project}/resource".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"resources":[{"resourceURI":"/dynatrace/dynatrace.conf.yaml","resourceContent":str(base64.b64encode(dynatraceConf.encode("utf-8")),"utf-8")}]})
                        break
                    else:
                        print("something else")

def createShipyard(project, stages):
    shipyard = {
            "apiVersion": "spec.keptn.sh/0.2.3",
	        "kind": "Shipyard",
	        "metadata": {"name": project},
	        "spec": {"stages": []}
            }
    for stage in stages:
        shipyard["spec"]["stages"].append({"name": stage,"sequences": [{"name": "evaluation","tasks": [{"name": "evaluation"}]}]})
    return shipyard


def calculatePass(dash, entitySelector, count, num, url, token, timeFrame, mzName, app, baseline, weight, keySli):
    metricKey = []
    totalTiles = len(dash["tiles"])
    startIndex = count
    print("Calculating Baseline for {totalTiles} dashboard tiles! ".format(totalTiles=(totalTiles-startIndex)))
    while count < totalTiles:
        print("Progress: {count} of {totalTiles}".format(count=count-startIndex+1,totalTiles=totalTiles-startIndex))
        metric = dash["tiles"][count]["queries"][0]["metric"]
        agg = ":{a}".format(a=dash["tiles"][count]["queries"][0]["spaceAggregation"])
        if "PERCENTILE" in agg:
            agg = ":percentile({x})".format(x = agg.split("_")[1])
            
        if "host" in metric:
            tempEntitySelector = copy.deepcopy(entitySelector).format(type="host")
            if "disk" in metric:
                metric = getMetric(metric, ":merge(dt.entity.host,dt.entity.disk)", agg)
            else:
                metric = getMetric(metric, ":merge(dt.entity.host)", agg)
            getData(tempEntitySelector, metric, url, token, timeFrame, num, count, dash, baseline["infra_pass"], baseline["infra_warn"], metricKey, weight["infra"], keySli["infra"])
        elif "service" in metric:
            tempEntitySelector = copy.deepcopy(entitySelector).format(type="service")
            metric = getMetric(metric, ":merge(dt.entity.service)", agg)
            getData(tempEntitySelector, metric, url, token, timeFrame, num, count, dash, baseline["service_pass"], baseline["service_warn"], metricKey, weight["service"],keySli["service"])
        elif "generic" in metric or "pgi" in metric or "tech" in metric:
            tempEntitySelector = copy.deepcopy(entitySelector).format(type="process_group_instance")
            if "generic" in metric or "pgi" in metric:
                metric = getMetric(metric, ":merge(dt.entity.process_group_instance)", agg)
            elif "jvm" in metric or "dotnet.gc" in metric:
                if "threads" in metric:
                    metric = getMetric(metric, ':merge(dt.entity.process_group_instance,API,Thread state)', agg)
                elif "pool" in metric:
                    metric = getMetric(metric, ":merge(dt.entity.process_group_instance,rx_pid,poolname)", agg)
                else:
                    metric = getMetric(metric, ":merge(dt.entity.process_group_instance)", agg)
            else:
                metric = getMetric(metric, ":merge(dt.entity.process_group_instance,rx_pid)", agg)
            if "pgi.availability" not in metric:
                getData(tempEntitySelector, metric, url, token, timeFrame, num, count, dash, baseline["infra_pass"], baseline["infra_warn"],metricKey, weight["infra"],keySli["infra"])
            else:
                dash["tiles"][count]["name"] = dash["tiles"][count]["name"].split(';')[0]
        elif '.action.' in metric:
            tempEntitySelector = copy.deepcopy(entitySelector).format(type="application_method",id=dash["tiles"][count]["queries"][0]["filterBy"]["nestedFilters"][0]["criteria"][0]["value"])
            if '.duration.' in metric or '.count.' in metric:
                metric = getMetric(metric, ":merge(dt.entity.application_method,dt.entity.browser)", agg)
            elif '.apdex' in metric:
                metric = getMetric(metric, ":merge(dt.entity.application_method,User type)", agg)
            elif ".countOfErrors" in metric:
                metric = getMetric(metric, ":merge(dt.entity.application_method,Error type,Error origin)", agg)
            else:
                metric = getMetric(metric, ":merge(dt.entity.application_method)", agg)
            getData(tempEntitySelector, metric, url, token, timeFrame, num, count, dash, baseline["app_pass"], baseline["app_warn"],metricKey,weight["app"],keySli["app"])
        elif "apps" in metric:
            if mzName:
                tempEntitySelector = "type({type}),mzName({mzName})".format(mzName = mzName, type = "application")
            else:
                tempEntitySelector = "type({type}),entityName({app})".format(app = app, type = "application")
            if "actionDuration" in metric:
                metric = getMetric(metric, ":merge(dt.entity.application,dt.entity.browser)", agg)
            elif ".countOfErrors" in metric:
                metric = getMetric(metric, ":merge(dt.entity.application,Error type,Error origin)", agg)
            elif ".actionCount." in metric:
                metric = getMetric(metric, ":merge(dt.entity.application,Action type,dt.entity.geolocation)", agg)
            else:
                metric = getMetric(metric, ":merge(dt.entity.application,User type)", agg)
            getData(tempEntitySelector, metric, url, token, timeFrame, num, count, dash, baseline["app_pass"], baseline["app_warn"],metricKey,weight["app"],keySli["app"])
        else:
            count += 1
            continue
        count += 1
    return dash, metricKey

def getMetric(metric, merge, agg):
    return "{metric}{merge}{agg}".format(metric = metric, merge = merge, agg = agg)

def getData(entitySelector, metric, url, token, timeFrame, num, count, dash, percent, warn, metricKey, weight, keySli):
    resp = handleGet("{url}/api/v2/metrics/query".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {"from":timeFrame,"resolution":"inf","metricSelector":metric,"entitySelector":entitySelector})
    if 'error' in resp:
        print("Couldn't complete request. {error}".format(error=resp["error"]))
        print("***********************************")
        exit()
    key = dash["tiles"][count]["name"].split("sli=")[1].split(";")[0]
    indx = len(resp["result"])
    if indx > 1:
        cleanUpData(resp, indx)
    if resp["result"][0]["data"]:
        resp = list(filter(None, resp["result"][0]["data"][0]["values"]))[0]
        sign = dash["tiles"][count]["name"].split("pass=")[1].split("{")[0]
        if resp:
            #if ":max" in metric.lower():
            #    base = max(resp)
            #else:
            #    base = mean(resp)
            base = resp
            if '>=' == sign:
                value = base - (base*(percent/100))
                warn = base - (base*(warn/100))
                baseKey = setMetricKey(key, "_base", metricKey, base)
                passKey = setMetricKey(key, "_pass", metricKey, value)
                warnKey = setMetricKey(key, "_warn", metricKey, warn)
                weightKey = setMetricKey(key, "_weight",metricKey, weight)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][0]["value"] = "{{{{ .{s} }}}}".format(s = passKey)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][1]["value"] = "{{{{ .{s} }}}}".format(s = warnKey)
                dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="{{{{ .{s} }}}};weight={{{{ .{w} }}}};key_sli={k}".format(s = passKey, w = weightKey, k = keySli))
            else:
                value = base + (base*(percent/100))
                warn = base + (base*(warn/100))
                baseKey = setMetricKey(key, "_base", metricKey, base)
                passKey = setMetricKey(key, "_pass", metricKey, value)
                warnKey = setMetricKey(key, "_warn", metricKey, warn)
                weightKey = setMetricKey(key, "_weight",metricKey, weight)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][1]["value"] = "{{{{ .{s} }}}}".format(s = passKey)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = "{{{{ .{s} }}}}".format(s = warnKey)
                if "pool" in metric or "service.response.time" in metric:
                    dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="{s};weight={{{{ .{w} }}}};key_sli={k}".format(s = "{:.3f}".format(value/1000), w = weightKey, k = keySli))
                else:
                    dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="{{{{ .{s} }}}};weight={{{{ .{w} }}}};key_sli={k}".format(s = passKey, w = weightKey, k = keySli))
        else:
            passKey = setMetricKey(key, "_pass", metricKey, percent)
            weightKey = setMetricKey(key, "_weight",metricKey, weight)
            dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = "{{{{ .{s} }}}}".format(s = passKey)
            dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="+{{{{ .{s} }}}}%;weight={{{{ .{w} }}}};key_sli={k}".format(s = passKey, w = weightKey,k = keySli))
    else:
        passKey = setMetricKey(key, "_pass", metricKey, percent)
        weightKey = setMetricKey(key, "_weight",metricKey, weight)
        dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = '{{{{ .{s} }}}}'.format(s = passKey)
        dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="+{{{{ .{s} }}}}%;weight={{{{ .{w} }}}};key_sli={k}".format(s = passKey, w = weightKey,k = keySli))

def cleanUpData(resp, count):
    print(resp["result"][0])
    for i in range(1,count):
        print(i)
        if(resp["result"][i]["data"]):
            print(resp["result"][i])
            resp["result"][0]["data"][0]["values"].extend(resp["result"][i]["data"][0]["values"])
            print(resp["result"][i]["data"][0]["values"])

def setMetricKey(key, string, metricKey, val):
    s = key + string
    if not isinstance(val, int):
        metricKey.append({s: "{:.3f}".format(val)})
    else:
        metricKey.append({s: str(val)})
    return s

def handlePut(url, header, x, y):
    try:
        put = requests.put(url, headers=header, params=x, data=json.dumps(y), verify=verifySSL)
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

def handlePost(url, header, x, y):
    try:
        post = requests.post(url, headers=header, params=x, data=json.dumps(y), verify=verifySSL)
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
        get = requests.get(url, headers=header, params=x, verify=verifySSL)
        #get.raise_for_status()
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

'''            
  Iterates through all dashboard configs in envrionments.yaml and assigns the mzID 
''' 
def getMzId(mzName, url, token):
    resp = handleGet("{url}/api/config/v1/managementZones".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {})
    if 'values' in resp:
        for i in resp["values"]:
            if mzName == i["name"]:
                return i["id"]
    else:
        return resp

def buildProject(finalDash, metricKey, dashboardYaml, project, stage, service):
    print("Building Release Validation Dashboard Project - Project:{project};Stage:{stage};Service:{service}".format(project=project,stage=stage,service=service))
    dashboardYaml[project].extend(metricKey)
    finalDash["dashboardMetadata"]["name"] = "{{ .name }}"
    
    projectDir = "{name}-{stage}-{service}".format(name = project, stage = stage, service = service)

    # replace some special characters we may have in the name and mz
    projectDir = projectDir.replace(":", "_")

    # target directory for dashboards is dashboard
    dashboardDir = "{dir}/dashboard".format(dir = projectDir)

    if not os.path.exists(dashboardDir):
        os.makedirs(dashboardDir)

    createCADashboardProject(dashboardDir, "/dashboard.json", "/dashboard.yaml", dashboardYaml, finalDash)
    return projectDir

def createCADashboardProject(dir,j,d,dashboardYaml,finalDash):
    with open('{dir}{j}'.format(dir=dir, j = j), 'w') as f:
        json.dump(finalDash,f, indent=2)
    with open('{dir}{d}'.format(dir=dir, d = d), 'w') as f:
        yaml.dump(dashboardYaml, f)

def prepareMonaco(projectDir):
    check = subprocess.check_call(["monaco","--version"])
    if check:
        print("Finished! You can now run:")
        print("monaco --environments=environments.yaml -p=\"{projectDir}\"".format(projectDir=projectDir))
    else:
        print("Running Monaco to deploy dashboard - ({projectDir})".format(projectDir = projectDir))
        subprocess.run(["monaco", "--environments=environments.yaml", r'-p={projectDir}/'.format(projectDir=projectDir)])

def getFileYAML(fileName):
    try:
        with open(fileName, "r") as stream:
            try:
              fileYAML = yaml.safe_load(stream)
              return fileYAML
            except yaml.YAMLError as err:
              print(err)
              return None
    except Exception as e:
        print(e)
        exit()


def getFileJSON(fileName):
    try:
        with open (fileName, "r") as stream:
              fileJSON = json.loads(stream.read())
        return fileJSON
    except Exception as e:
        print(e)
        exit()

if __name__ == "__main__":
    main()