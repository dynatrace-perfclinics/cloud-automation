import requests, json, os, yaml, copy, subprocess
from argparse import ArgumentParser
from statistics import mean
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

parser = ArgumentParser()

parser.add_argument("-a","--auto-monaco",dest="autoMonaco",help="Use this to automatically execute monaco to deploy dashboards. (missing = false)", action="store_false")
parser.add_argument("-v", "--verify", dest="verify", help="Verify SSL Cert. (missing = true)", action='store_false')
    
args = parser.parse_args()

verifySSL = args.verify
autoMonaco = args.autoMonaco

def main():
    
    config = {
            "generic":getFileJSON("config/generic.json"), 
            "nodejs":getFileJSON("config/nodejs.json"), 
            "go": getFileJSON("config/go.json"), 
            "java":getFileJSON("config/java.json"),
            "dotnet":getFileJSON("config/dotnet.json")
            }

    env = getFileYAML('environments.yaml')
    for i in env:
        url,token,name = verifyEnvironment(env, i)

        print("Reaching out to Dynatrace Environment ({envname}) via URL: {apiurl}".format(envname=name,apiurl=url))

        dashes = getFileYAML("config.yaml")
        if dashes:
            for j in dashes["dashboards"]:
                if "mzName" not in j:
                    print("One of the dashboard configurations in environments.yaml doesn't include a mzName")
                elif "technology" not in j:
                    print("The technology field is not present for the dashboard with MZ : {mz}".format(mz=j["mzName"]))
                elif j["technology"] not in config:
                    print("The technology: {tech} is currently not supported for the dashboard with MZ: {mz}.".format(tech=j["technology"],mz=j["mzName"]))
                else:
                    getMzId(j, url, token)
                    if "mzId" not in j:
                        print("The mzName : {mz} is invalid. It didn't match any existing mz in the env: {name}".format(mz=j["mzName"],name=name))
                    else:
                        print("Validated Management Zone ({mzName}) with id={mzId}".format(mzName=j["mzName"],mzId=j["mzId"]))

                        finalDash, metricKey = calculatePass(copy.deepcopy(config[j["technology"]]["dash"]), copy.deepcopy(config[j["technology"]]["count"]), config[j["technology"]]["num"], url, token, j["dash"]["timeFrame"], j["mzName"], j["baseline"]["app_pass"], j["baseline"]["service_pass"], j["baseline"]["infra_pass"], j["baseline"]["app_warn"], j["baseline"]["service_warn"], j["baseline"]["infra_warn"])
                        buildProject(finalDash, metricKey, name, j["mzName"], j["mzId"], j["technology"], j["dash"]["project"], j["dash"]["stage"], j["dash"]["service"], j["dash"]["owner"], j["dash"]["timeFrame"], j["dash"]["preset"], j["dash"]["shared"])
        else:
            print("Add the dashboard configurations you'd like a dashboard created for in config/config.yaml")

def calculatePass(dash, count, num, url, token, timeFrame, mzName, app, service, infra, appWarn, serviceWarn, infraWarn):
    metricKey = []
    totalTiles = len(dash["tiles"])
    startIndex=count
    print("Calculating Baseline for {totalTiles} dashboard tiles! ".format(totalTiles=(totalTiles-startIndex)))
    while count < totalTiles:
        print("Progress: {count} of {totalTiles}".format(count=count-startIndex+1,totalTiles=totalTiles-startIndex))
        metric = dash["tiles"][count]["queries"][0]["metric"]
        agg = dash["tiles"][count]["queries"][0]["spaceAggregation"]
        entitySelector = "type({type}),mzName({mzName})".format(mzName = mzName, type = "{type}")
        if "host" in metric:
            entitySelector = entitySelector.format(type="host")
            if "disk" in metric:
                metric = metric + ":merge(dt.entity.host,dt.entity.disk)"
            else:
                metric = metric + ":merge(dt.entity.host)"
            getData(entitySelector, metric, url, token, timeFrame, num, count, dash, infra, infraWarn, metricKey)
        elif "service" in metric:
            entitySelector = entitySelector.format(type="service")
            metric = metric + ":merge(dt.entity.service)"
            getData(entitySelector, metric, url, token, timeFrame, num, count, dash, service, serviceWarn, metricKey)
        elif "generic" in metric or "pgi" in metric or "tech" in metric:
            entitySelector = entitySelector.format(type="process_group_instance")
            if "generic" in metric or "pgi" in metric:
                metric = metric + ":merge(dt.entity.process_group_instance)"
            elif "jvm" in metric or "dotnet.gc" in metric:
                if "threads" in metric:
                    metric = metric + ':merge(dt.entity.process_group_instance,API,Thread state)'
                elif "pool" in metric:
                    metric = metric + ":merge(dt.entity.process_group_instance,rx_pid,poolname)"
                else:
                    metric = metric + ":merge(dt.entity.process_group_instance)"
            else:
                metric = metric + ":merge(dt.entity.process_group_instance,rx_pid)"
            getData(entitySelector, metric, url, token, timeFrame, num, count, dash, infra, infraWarn,metricKey)
        elif "apps" in metric:
            entitySelector = entitySelector.format(type="application")
            if "actionDuration" in metric:
                metric = metric + ":merge(dt.entity.application,dt.entity.browser)"
            else:
                metric = metric + ":merge(dt.entity.application,User type)"
            getData(entitySelector, metric, url, token, timeFrame, num, count, dash, app, appWarn,metricKey)
        else:
            count += 1
            continue
        count += 1
    return dash, metricKey

def getData(entitySelector, metric, url, token, timeFrame, num, count, dash, percent, warn, metricKey):
    resp = handleRequest("{url}/api/v2/metrics/query".format(url=url), token, {"from":timeFrame,"metricSelector":metric,"entitySelector":entitySelector})
    key = dash["tiles"][count]["name"].split("sli=")[1].split(";")[0]
    if resp["result"][0]["data"]:
        resp = list(filter(None, resp["result"][0]["data"][0]["values"]))
        sign = dash["tiles"][count]["name"].split("pass=")[1].split("{")[0]
        if resp:
            base = mean(resp)
            if '>' == sign:
                value = base - (base*(percent/100))
                warn = base - (base*(warn/100))
                baseKey = setMetricKey(key, "_base", metricKey, base)
                valueKey = setMetricKey(key, "_pass", metricKey, value)
                warnKey = setMetricKey(key, "_warn", metricKey, warn)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][0]["value"] = "{{{{ .{s} }}}}".format(s = valueKey)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][1]["value"] = "{{{{ .{s} }}}}".format(s = warnKey)
                dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="{{{{ .{s} }}}}".format(s = valueKey))
            else:
                value = base + (base*(percent/100))
                warn = base + (base*(warn/100))
                baseKey = setMetricKey(key, "_base", metricKey, base)
                valueKey = setMetricKey(key, "_pass", metricKey, value)
                warnKey = setMetricKey(key, "_warn", metricKey, warn)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][1]["value"] = "{{{{ .{s} }}}}".format(s = valueKey)
                dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = "{{{{ .{s} }}}}".format(s = warnKey)
                dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="{{{{ .{s} }}}}".format(s = valueKey))
        else:
            valueKey = setMetricKey(key, "_pass", metricKey, percent)
            dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = "{{{{ .{s} }}}}".format(s = valueKey)
            dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="+{{{{ .{s} }}}}%".format(s = valueKey))
    else:
        valueKey = setMetricKey(key, "_pass", metricKey, percent)
        dash["tiles"][count-num]["visualConfig"]["thresholds"][0]["rules"][2]["value"] = '{{{{ .{s} }}}}'.format(s = valueKey)
        dash["tiles"][count]["name"] = dash["tiles"][count]["name"].format(cond="+{{{{ .{s} }}}}%".format(s = valueKey))

def handleRequest(url, token, x):
    try:
        get = requests.get(url, headers={'Content-Type': 'application/json', 'Authorization' : 'Api-Token {apitoken}'.format(apitoken=token)}, params=x, verify=verifySSL)
        get.raise_for_status()
        resp = get.json()
        return resp
    except requests.exceptions.HTTPError as err:
        raise SystemExit(err)
    except requests.exceptions.Timeout:
        print("The request timed out. Couldn't reach - {url}".format(url = url))
    except requests.exceptions.ConnectionError:
        print("The URL was malformed - {url}".format(url = url))
    except requests.exceptions.TooManyRedirects:
        print("The URL was malformed - {url}".format(url = url))
    except requests.exceptions.RequestException as e:
        print("Something went wrong when connecting to Dynatrace API")
        raise SystemExit(e)

def setMetricKey(key, string, metricKey, val):
    s = key + string
    metricKey.append({s: "{:.2f}".format(val)})
    return s

'''            
  Iterates through all dashboard configs in envrionments.yaml and assigns the mzID 
''' 
def getMzId(x, url, token):
    resp = handleRequest("{url}/api/config/v1/managementZones".format(url=url), token, {})
    for i in resp["values"]:
        if x["mzName"] == i["name"]:
            x["mzId"] = i["id"]

def buildProject(finalDash,metricKey, name,mzName, mzId, tech, project, stage, service, owner, timeFrame, preset, shared):
    s = finalDash["dashboardMetadata"]["name"].format(project = project, stage = stage, service = service)
    dashboardYaml = {'config':[{name:"dashboard.json"}],name:[{"name":s},{"owner":owner},{"shared":shared},{"timeFrame":timeFrame},{"preset":preset},{"project":project},{"stage":stage},{"service":service},{"mzId":mzId}, {"mzName":mzName}]}
    dashboardYaml[name].extend(metricKey)
    finalDash["dashboardMetadata"]["name"] = "{{ .name }}"
    projectDir = "{name}-{mz}-{tech}".format(name = name, mz = mzName, tech=tech)

    # replace some special characters we may have in the name and mz
    projectDir = projectDir.replace(":", "_")

    # target directory for dashboards is dashboard
    dashboardDir = "{dir}/dashboard".format(dir = projectDir)

    if not os.path.exists(dashboardDir):
        os.makedirs(dashboardDir)
     
    createCADashboardProject(dashboardDir, "/dashboard.json", "/dashboard.yaml", dashboardYaml, finalDash)

    if not autoMonaco:
        check = subprocess.check_call(["monaco","--version"])
        if check:
            print("Finished! You can now run:")
            print("monaco --environments=environments.yaml -p=\"{projectDir}\"".format(projectDir=projectDir))
        else:
            print("Running Monaco to deploy dashboard - {projectDir}".format(projectDir = projectDir))
            subprocess.run(["monaco", "--environments=environments.yaml", r'-p={projectDir}/'.format(projectDir=projectDir)])
    else:
        print("Finished! Review {projectDir} and run:".format(projectDir=projectDir))
        print(r'monaco --environments=environments.yaml -p={projectDir}/'.format(projectDir=projectDir))
def createCADashboardProject(dir,j,d,dashboardYaml,finalDash):
    with open('{dir}{j}'.format(dir=dir, j = j), 'w') as f:
        json.dump(finalDash,f, indent=2)
    with open('{dir}{d}'.format(dir=dir, d = d), 'w') as f:
        yaml.dump(dashboardYaml, f)

def verifyEnvironment(env, i):
    for x in range(len(env[i])):
        if "env-url" in env[i][x]:
            url = env[i][x]["env-url"]
            if "http" in url and ".Env." in url:
                url = "{i}{j}".format(i = url.replace(" ", "").split("{{.Env.")[0], j = os.getenv(url.replace(" ", "").split("{{.Env.")[1].split("}}")[0]))
            elif not "http" in url and ".Env." in url:
                url = os.getenv(url.replace(" ", "").split("{{.Env.")[1].split("}}")[0])
            else:
                pass
        if "env-token-name" in env[i][x]:
            token = os.getenv(env[i][x]["env-token-name"])
        if "name" in env[i][x]:
            name = env[i][x]["name"]
    return url,token,name

def getFileYAML(fileName):
    with open(fileName, "r") as stream:
        try:
          fileYAML = yaml.safe_load(stream)
          return fileYAML
        except yaml.YAMLError as err:
          print(err)
          return None

def getFileJSON(fileName):
    with open (fileName, "r") as stream:
          fileJSON = json.loads(stream.read())
    return fileJSON

if __name__ == "__main__":
    main()