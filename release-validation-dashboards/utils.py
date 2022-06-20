import requests, json, yaml, subprocess, os, base64

def handlePut(url, header, x, y,  verifySSL):
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

def handlePost(url, header, x, y, verifySSL):
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

def handleGet(url, header, x, verifySSL):
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

def prepareMonaco(projectDir):
    check = subprocess.check_call(["monaco","--version"])
    if check:
        print("Finished! You can now run:")
        print("monaco --environments=environments.yaml -p=\"{projectDir}\"".format(projectDir=projectDir))
    else:
        print("Running Monaco to deploy dashboard - ({projectDir})".format(projectDir = projectDir))
        subprocess.run(["monaco", "--environments=environments.yaml", r'-p={projectDir}/'.format(projectDir=projectDir)])

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

def prepareCA(ca, project, service, stage, caBaseUrl, caToken, verifySSL):
    for i in ca:
        project = i
        service = ""
        for k in ca[i]["service"]:
            service = k
            stage = ""
            for j in ca[i]["stage"]:
                stage = j
                print("Working on Project:{project}, Stage:{stage}, Service:{service}".format(project=project,stage=stage,service=service))
                check = handleGet(caBaseUrl + "/api/controlPlane/v1/project/{project}/stage/{stage}/service/{service}".format(project=project,stage=stage,service=service),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{}, verifySSL)
                if "message" not in check:
                    if '401 Authorization Required' in check:
                        print("The Cloud Automation Token ({caToken}) is invalid".format(caToken = caToken))
                        continue
                    print("Finished! The Cloud Automation Project:{project}, exists with Stage:{stage}, Service:{service}".format(project=project,stage=stage,service=service))
                    print("..............................")
                else:
                    if "service not found" in check["message"]:
                        print("Service not Found - Creating Service ({service}) for Project ({project})".format(service=service,project=project))
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project/{project}/service".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"serviceName":service}, verifySSL)
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
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project",{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"name":project, "shipyard":str(base64.b64encode(shipyard.encode("utf-8")),"utf-8")}, verifySSL)
                        handlePost(caBaseUrl + "/api/controlPlane/v1/project/{project}/service".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"serviceName":service}, verifySSL)
                        handlePut(caBaseUrl + "/api/configuration-service/v1/project/{project}/resource".format(project=project),{'Content-Type': 'application/json', 'Accept':'application/json', 'x-token': '{apitoken}'.format(apitoken=caToken)},{},{"resources":[{"resourceURI":"/dynatrace/dynatrace.conf.yaml","resourceContent":str(base64.b64encode(dynatraceConf.encode("utf-8")),"utf-8")}]}, verifySSL)
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

def getConfig():
    base = getFileJSON("config/base.json")
    config = {
            "generic":getFileJSON("config/generic.json"), 
            "nodejs":getFileJSON("config/nodejs.json"), 
            "go": getFileJSON("config/go.json"), 
            "java":getFileJSON("config/java.json"),
            "dotnet":getFileJSON("config/dotnet.json")
            }
    
    dash = getFileYAML("config.yaml")
    return base, config, dash

def validateInput(j, x, default):
    if x not in j:
        return default
    else:
        return j[x]

def getMzId(mzName, url, token, verifySSL):
    resp = handleGet("{url}/api/config/v1/managementZones".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {}, verifySSL)
    if 'values' in resp:
        for i in resp["values"]:
            if mzName == i["name"]:
                return i["id"]
    else:
        return resp

def getApplication(url, token, app, timeFrame, verifySSL):
    entitySelector = "type(application),entityName({app})".format(app=app)
    resp = handleGet("{url}/api/v2/entities".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {"from":timeFrame,"entitySelector":entitySelector}, verifySSL)
    return resp

def getUAType(type, app, tempData, url, token, timeFrame, verifySSL):
    entitySelector = "type(application_method),fromRelationShip.isApplicationMethodOf(type(application),entityName({app}))".format(app=app)
    metric = "builtin:apps.web.action.count.({type}).browser:splitBy(dt.entity.application_method):sort(value(avg,descending)):limit(10):names".format(type=type)
    resp = handleGet("{url}/api/v2/metrics/query".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {"from":timeFrame,"resolution":"inf","metricSelector":metric,"entitySelector":entitySelector}, verifySSL)
    if 'error' in resp:
        print("Couldn't complete request. {error}".format(error=resp["error"]))
        print("***********************************")
        exit()
    if resp["result"][0]["data"]:
        for i in resp["result"][0]["data"]:
            i["type"] = type
        tempData.extend(resp["result"][0]["data"])

def getMetric(metric, merge, agg):
    return "{metric}{merge}{agg}".format(metric = metric, merge = merge, agg = agg)

def setMetricKey(key, string, metricKey, val):
    s = key + string
    if not isinstance(val, int):
        metricKey.append({s: "{:.3f}".format(val)})
    else:
        metricKey.append({s: str(val)})
    return s