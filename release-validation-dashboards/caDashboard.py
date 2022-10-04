import requests, json, os, yaml, copy, subprocess, base64, logging, sys
from argparse import ArgumentParser
from statistics import mean
from utils import handleGet, handlePut, handlePost, getFileYAML, getFileJSON, prepareMonaco, addToCa, prepareCA, buildProject, getConfig, validateInput, getMzId, getApplication, getUAType, setMetricKey, getMetric
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
parser.add_argument("-l", "--logging", action="store", choices=["DEBUG","INFO","ERROR"],default="INFO", help="Optional logging levels, default is INFO if nothing is specified")

args = parser.parse_args()

# Logging
logging.basicConfig(stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s",datefmt='%Y-%m-%d %H:%M:%S') #Sets logging format to "[LEVEL] log message"
logger = logging.getLogger('Dynatrace Automation Bootstrap - cloud Automation Evaluation Dashboard')
logger.setLevel(args.logging)

verifySSL = args.verify
autoMonaco = args.autoMonaco
autoCloudAutomation = args.autoCloudAutomation
caTenant = args.caTenant
caToken = args.caToken
url = args.dtUrl
token = args.dtToken

caBaseUrl = "https://{caTenant}.cloudautomation.{x}".format(caTenant=caTenant,x=url.split(".",1)[1])

def main():
    base, config, dash = getConfig(logger)
    ca = {}
    if dash:
        for j in dash["dashboards"]:
                if ('automation' not in j and 'dashboard' not in j) or ('mzName' not in j and 'application' not in j) or ('mzName' in j and 'application' in j):
                    logger.info("Requirements not met. The config needs at most the following parameters: \nmzName:'MZNAME'\ndashboard:\n   owner:'OWNER'\nautomation:\n   project:'CAPROJECT'\n   stage:'CASTAGE'\n   service:'CASERVICE'")
                    logger.info("OR")
                    logger.info("application:'APPNAME'\ndashboard:\n   owner:'OWNER'\nautomation:\n   project:'CAPROJECT'\n   stage:'CASTAGE'\n   service:'CASERVICE'")
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

                    logger.info("Reaching out to Dynatrace Environment - ({apiurl})".format(apiurl=url))
                    tempDash = copy.deepcopy(base)
                    if 'application' in j:
                        appId = getApplication(url, token, j['application'], timeFrame, verifySSL, logger)
                        if not appId or len(appId["entities"]) != 1:
                            logger.info("No application was found with the name: {app}".format(app = j["application"]))
                            logger.info("***********************************")
                            continue
                        if 'error' in appId:
                            logger.info("Couldn't compelte request. {error}".format(error = appId["error"]))
                            logger.info("***********************************")
                            continue
                        else:
                            logger.info("Validated Application ({app}) with id={id}".format(app=j["application"], id = appId["entities"][0]["entityId"]))
                            logger.info("***********************************")
                            topUa = getTopUA(url, token, j['application'], timeFrame)
                            num, count = configAppDash(tempDash,topUa)
                            entitySelector = "type(application_method),entityId({id}),fromRelationShip.isApplicationMethodOf(type(application),entityName({app}))".format(app=j["application"], id="{id}")
                            finalDash, metricKey = calculatePass(tempDash,entitySelector, count,num,url,token,timeFrame,'', j["application"],baseline,weight,keySli)
                            s = finalDash["dashboardMetadata"]["name"].format(project = project, stage = stage, service = service)
                            dashboardYaml = {'config':[{project:"dashboard.json"}],project:[{"name":s},{"owner":owner},{"shared":shared},{"timeFrame":timeFrame},
                                                                  {"preset":preset},{"project":project},{"stage":stage},{"service":service},
                                                                  {"total_pass":total_pass},{"appName":j['application']},{"total_warn":total_warn},{"caUrl":caBaseUrl + "/bridge/project/{name}/service".format(name=project)}]}
                            del finalDash["dashboardMetadata"]["dashboardFilter"]["managementZone"]

                            projectDir = buildProject(finalDash, metricKey, dashboardYaml, project, stage, service, logger)
                    else:
                        mzName = j["mzName"]
                        mzId = getMzId(mzName, url, token, verifySSL, logger)
                        if not mzId:
                            logger.info("The mzName : {mz} is invalid. It didn't match any existing mz in the env: {name}".format(mz=mzName,name=url))
                            logger.info("***********************************")
                            continue
                        if 'error' in mzId:
                            logger.info("Couldn't compelte request. {error}".format(error = mzId["error"]))
                            logger.info("***********************************")
                            continue
                        logger.info("Validated Management Zone ({mzName}) with id={mzId}".format(mzName=mzName,mzId=mzId))
                        logger.info("***********************************")
                        entitySelector = "type({type}),mzName({mzName})".format(mzName = mzName, type = "{type}")
                        tempDash["tiles"].extend(config[technology]["dash"])
                        finalDash, metricKey = calculatePass(tempDash,entitySelector,copy.deepcopy(config[technology]["count"]),config[technology]["num"],url,token,timeFrame,mzName,'',baseline,weight,keySli)       
                        s = finalDash["dashboardMetadata"]["name"].format(project = project, stage = stage, service = service)
                        dashboardYaml = {'config':[{project:"dashboard.json"}],project:[{"name":s},{"owner":owner},{"shared":shared},{"timeFrame":timeFrame},
                                        {"preset":preset},{"project":project},{"stage":stage},{"service":service},
                                        {"mzId":mzId}, {"mzName":mzName},{"total_pass":total_pass},
                                        {"total_warn":total_warn},{"caUrl":caBaseUrl + "/bridge/project/{name}/service".format(name=project)}]}
                        projectDir = buildProject(finalDash, metricKey, dashboardYaml, project, stage, service, logger)
                    logger.info("***********************************")
                    logger.info("Testing Auto Monaco")
                    if not autoMonaco:
                        logger.info("")
                        prepareMonaco(projectDir, logger)
                    else:
                        logger.info("")
                        logger.info("Finished! Review ({projectDir}) and run:".format(projectDir=projectDir))
                        logger.info(r'monaco --environments=environments.yaml -p={projectDir}/'.format(projectDir=projectDir))
                    logger.info("***********************************")

        logger.info("Testing Auto Cloud Automation")
        if not autoCloudAutomation:
                logger.info("Reaching out to Cloud Automation - ({caBaseUrl})".format(caBaseUrl = caBaseUrl))
                prepareCA(ca, project, service, stage, caBaseUrl, caToken, verifySSL, logger)
        else:
            logger.info("Before the SLI Evaluation can be ran, create the cloud automation project with stage and service")
        logger.info("***********************************")
    else:
            logger.info("Add the dashboard configurations you'd like a dashboard created for in config/config.yaml")

def getTopUA(url, token, app, timeFrame):
    ua = []
    tempData = []
    getUAType("xhr",app, tempData, url, token, timeFrame, verifySSL, logger)
    getUAType("load",app, tempData, url, token, timeFrame, verifySSL, logger)
    tempData = sorted(tempData, key = lambda i: i["values"][0],reverse=True)
    for i in range(10):
        try:
            if tempData[i]:
                ua.append(tempData[i])
        except:
            pass
    return ua

def configAppDash(tempDash, topUa):
    tempGraph = []
    tempSing = []
    app = getFileJSON("config/app.json", logger)
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

def calculatePass(dash, entitySelector, count, num, url, token, timeFrame, mzName, app, baseline, weight, keySli):
    metricKey = []
    totalTiles = len(dash["tiles"])
    startIndex = count
    logger.info("Calculating Baseline for {totalTiles} dashboard tiles! ".format(totalTiles=(totalTiles-startIndex)))
    while count < totalTiles:
        logger.info("Progress: {count} of {totalTiles}".format(count=count-startIndex+1,totalTiles=totalTiles-startIndex))
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

def getData(entitySelector, metric, url, token, timeFrame, num, count, dash, percent, warn, metricKey, weight, keySli):
    resp = handleGet("{url}/api/v2/metrics/query".format(url=url), {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}".format(token=token)}, {"from":timeFrame,"resolution":"inf","metricSelector":metric,"entitySelector":entitySelector}, verifySSL, logger)
    if 'error' in resp:
        logger.info("Couldn't complete request. {error}".format(error=resp["error"]))
        logger.info("***********************************")
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

if __name__ == "__main__":
    main()
