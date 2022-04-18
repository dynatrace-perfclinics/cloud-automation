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
                if 'ca' not in j or 'mzName' not in j or 'dash' not in j:
                    print("Requirements not met. The config needs at most the following parameters: \nmzName:'MZNAME'\ndash:\n   owner:'OWNER'\nca:\n   project:'CAPROJECT'\n   stage:'CASTAGE'\n   service:'CASERVICE'")
                else:
                    project = j["ca"]["project"]
                    stage = j["ca"]["stage"]
                    service = j["ca"]["service"]
                    addToCa(ca, project, stage, service)
                    mzName = j["mzName"]

                    print("Reaching out to Dynatrace Environment - ({apiurl})".format(apiurl=url))
                    mzId = getMzId(mzName, url, token)
                    if not mzId:
                        print("The mzName : {mz} is invalid. It didn't match any existing mz in the env: {name}".format(mz=mzName,name=url))
                        continue
                    if 'error' in mzId:
                        print("Couldn't compelte request. {error}".format(error = mzId["error"]))
                        print("***********************************")
                        continue
                    technology = validateInput(j, 'technology', 'generic')
                    owner = j["dash"]["owner"]
                    timeFrame = validateInput(j["dash"],'timeFrame', 'now-1d')
                    preset = validateInput(j["dash"],'preset', 'false')
                    shared = validateInput(j["dash"],'shared', 'false')
                    total_pass = validateInput(j, 'total_pass', '80%')
                    total_warn = validateInput(j, 'total_warn', '60%')
                    baseline = validateInput(j, 'baseline', {"app_pass":5,"app_warn":10,"service_pass":5,"service_warn":10,"infra_pass":20,"infra_warn":25})
                    weight = validateInput(j, "weight",{"app":1,"service":1,"infra":1})
                    keySli = validateInput(j, "keySli",{"app":"false","service":"false","infra":"false"})
                    print("Validated Management Zone ({mzName}) with id={mzId}".format(mzName=mzName,mzId=mzId))
                    print("***********************************")

                    print("Building Release Validation Dashboard Project - Project:{project};Stage:{stage};Service:{service}".format(project=project,stage=stage,service=service))
                    finalDash, metricKey = calculatePass(copy.deepcopy(config[technology]["dash"]),copy.deepcopy(config[technology]["count"]),config[technology]["num"],url,token,timeFrame,mzName,baseline,weight,keySli)       
                    projectDir = buildProject(finalDash,metricKey,mzName,mzId,technology,project,stage,service,owner,timeFrame,preset,shared,total_pass,total_warn)
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
                        print("Project not Found - Creating Project ({project}) with Stage ({stage}) and Service ({service})".format(stage=json.dumps(ca[project]["stage"]), service=service,project=project))
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project",{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"name":project, "shipyard":str(base64.b64encode(shipyard.encode("utf-8")),"utf-8")})
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project/{project}/service".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"serviceName":service})
                        handlePut(caBaseUrl + "/api/configuration-service/v1/project/{project}/resource".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"resources":[{"resourceURI":"/dynatrace/dynatrace.conf.yaml","resourceContent":"c3BlY192ZXJzaW9uOiAnMC4xLjAnCmRhc2hib2FyZDogcXVlcnkKYXR0YWNoUnVsZXM6CiAgdGFnUnVsZToKICAtIG1lVHlwZXM6CiAgICAtIFBST0NFU1NfR1JPVVBfSU5TVEFOQ0UKICAgIHRhZ3M6CiAgICAtIGNvbnRleHQ6IENPTlRFWFRMRVNTCiAgICAgIGtleToga2VwdG5fcHJvamVjdAogICAgICB2YWx1ZTogJFBST0pFQ1QKICAgIC0gY29udGV4dDogQ09OVEVYVExFU1MKICAgICAga2V5OiBrZXB0bl9zZXJ2aWNlCiAgICAgIHZhbHVlOiAkU0VSVklDRQogICAgLSBjb250ZXh0OiBDT05URVhUTEVTUwogICAgICBrZXk6IGtlcHRuX3N0YWdlCiAgICAgIHZhbHVlOiAkU1RBR0U="}]})
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


def calculatePass(dash, count, num, url, token, timeFrame, mzName, baseline, weight, keySli):
    metricKey = []
    totalTiles = len(dash["tiles"])
    startIndex=count
    print("Calculating Baseline for {totalTiles} dashboard tiles! ".format(totalTiles=(totalTiles-startIndex)))
    while count < totalTiles:
        print("Progress: {count} of {totalTiles}".format(count=count-startIndex+1,totalTiles=totalTiles-startIndex))
        metric = dash["tiles"][count]["queries"][0]["metric"]
        agg = ":{a}".format(a=dash["tiles"][count]["queries"][0]["spaceAggregation"])
        if "PERCENTILE" in agg:
            agg = ":percentile({x})".format(x = agg.split("_")[1])
            
        entitySelector = "type({type}),mzName({mzName})".format(mzName = mzName, type = "{type}")
        if "host" in metric:
            entitySelector = entitySelector.format(type="host")
            if "disk" in metric:
                metric = getMetric(metric, ":merge(dt.entity.host,dt.entity.disk)", agg)
            else:
                metric = getMetric(metric, ":merge(dt.entity.host)", agg)
            getData(entitySelector, metric, url, token, timeFrame, num, count, dash, baseline["infra_pass"], baseline["infra_warn"], metricKey, weight["infra"], keySli["infra"])
        elif "service" in metric:
            entitySelector = entitySelector.format(type="service")
            metric = getMetric(metric, ":merge(dt.entity.service)", agg)
            getData(entitySelector, metric, url, token, timeFrame, num, count, dash, baseline["service_pass"], baseline["service_warn"], metricKey, weight["service"],keySli["service"])
        elif "generic" in metric or "pgi" in metric or "tech" in metric:
            entitySelector = entitySelector.format(type="process_group_instance")
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
                getData(entitySelector, metric, url, token, timeFrame, num, count, dash, baseline["infra_pass"], baseline["infra_warn"],metricKey, weight["infra"],keySli["infra"])
            else:
                dash["tiles"][count]["name"] = dash["tiles"][count]["name"].split(';')[0]
        elif "apps" in metric:
            entitySelector = entitySelector.format(type="application")
            if "actionDuration" in metric:
                metric = getMetric(metric, ":merge(dt.entity.application,dt.entity.browser)", agg)
            else:
                metric = getMetric(metric, ":merge(dt.entity.application,User type)", agg)
            getData(entitySelector, metric, url, token, timeFrame, num, count, dash, baseline["app_pass"], baseline["app_warn"],metricKey,weight["app"],keySli["app"])
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

def setMetricKey(key, string, metricKey, val):
    s = key + string
    if not isinstance(val, int):
        metricKey.append({s: "{:.3f}".format(val)})
    else:
        metricKey.append({s: str(val)})
    return s

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

def buildProject(finalDash,metricKey,mzName, mzId, tech, project, stage, service, owner, timeFrame, preset, shared, totalPass, totalWarn):
    s = finalDash["dashboardMetadata"]["name"].format(project = project, stage = stage, service = service)
    dashboardYaml = {'config':[{project:"dashboard.json"}],project:[{"name":s},{"owner":owner},{"shared":shared},{"timeFrame":timeFrame},
                                                              {"preset":preset},{"project":project},{"stage":stage},{"service":service},
                                                              {"mzId":mzId}, {"mzName":mzName},{"total_pass":totalPass},
                                                              {"total_warn":totalWarn},{"caUrl":caBaseUrl + "/bridge/project/{name}/service".format(name=project)}]}
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