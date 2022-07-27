import requests, json, io, os, yaml, copy, math

def main():
    config = getFileJSON("config/config.json")
    a = os.path.split(os.getcwd())[0]
    f = os.listdir(a)
    for i in range(len(f)):
        if 'environments.yaml' in f[i]:
            env = getFileYAML('{dir}\{file}'.format(dir=a,file=f[i]))
    for i in env:
        url,token,name = verifyEnvironment(env, i)
        cleanSlo = getSlo(url, token)
        slos = loadSlosYaml(config["slos"],config["customer"],config["service"],name)
        #print(json.dumps(slos, indent=2))
        dash = copy.deepcopy(config["dash"])
        finalDashboard = buildDashboard(cleanSlo, slos, dash, config["customers"], config["dashes"], config["dashLine"], config["line"], config["services"], config["slas"], config["indicators"])
        #print(json.dumps(finalDashboard, indent=2))
        buildProject(finalDashboard, name)

def loadSlosYaml(slos,customer,service,name):
    s = {}
    image = 0
    dir = os.path.split(os.getcwd())[0]
    for i in slos:
        for j in slos[i]:
            slo = getFileYAML('{dir}\\{i}\\{j}\\{k}'.format(dir = dir, i=i, j=j, k=slos[i][j][0]))
            metric = ""
            if "builtin" in slos[i][j][1]:
                metric = slos[i][j][1]
            else:
                mTemp = getFileYAML('{dir}\\{i}\\{j}\\{k}'.format(dir = dir, i=i, j=j, k=slos[i][j][1]))
            try:
                for l in slo["config"]:
                    for key in list(l.keys()):
                        if key.startswith(name):
                            responseTime = None
                            if "builtin" not in metric:
                                if key in getValue("calcMetric", slo[key]):
                                    metric = getValue("name", mTemp[key])
                                    responseTime = getValue("responseTime", mTemp[key])
                                else:
                                    print("The env:{name} was not found in the config:{key} in this project:{proj} \nThe calcMetric parameter should reference the correct env.".format(name=name, key=key, proj = '{dir}\\{i}\\{j}\\{k}'.format(dir = dir, i=i, j=j, k=slos[i][j][0])))
                                    break
                            cust = getValue("customerGroup", slo[key])
                            svc = getValue("service", slo[key])
                            ind = getValue("sli", slo[key])
                            proj = getValue("tagKeyValue", slo[key])
                            func = getValue("func", slo[key])
                            targ = getValue("target", slo[key])
                            req = getValue("request", slo[key])
                            aName = getValue("name", slo[key])
                            if cust in s:
                                if svc in s[cust]["service"]:
                                    addIndicator(ind, targ, proj, func, req, metric, aName, responseTime, j, s[cust]["service"][svc]["indicators"])
                                else:
                                    s[cust]["service"][svc] = {"image":service[s[cust]["num"]], "indicators":[]}
                                    addIndicator(ind, targ, proj, func, req, metric, aName, responseTime, j ,s[cust]["service"][svc]["indicators"])
                            else:
                                s[cust] = {"image":customer[image],"num":image,"service":{svc:{"image":service[image], "indicators": []}}}
                                addIndicator(ind, targ, proj, func, req, metric, aName, responseTime, j ,s[cust]["service"][svc]["indicators"])
                                if image < 2:
                                    image += 1
                                else: 
                                    image = 0
            except: 
                break
    return s

'''
  returns value of a key from a list of dict.
  x = key
  y = list of dict
''' 
def getValue(x, y):
    try:
        return list(filter(lambda obj: x in obj.keys(), y))[0][x]
    except:
        return None

'''
  adds all properties of an slo/indicator as a dict in a list
  x = list
''' 
def addIndicator(ind, targ, proj, func, req, metric, aName, responseTime, j, x):
    if "builtin" in metric:
        try:
            metric = metric.format(name = req)
        except:
            None
        try:
            metric = metric.format(project = proj, func = func)
        except:
            None
        try:
            metric = metric.format(project = proj)
        except:
            None
    else:
        if "calc:apps." in metric:
            metric = metric + ":count"
    x.append({"sli":ind, "target":targ, "project":proj, "function":func, "req":req, "name": aName, "responseTime" :responseTime,"metric":metric, "type":j})

def buildProject(finalDashboard,name):
    dashboardYaml = {'config':[{name:"dashboard.json"}],name:[{"name":"[SLO-Dashboard] {name} SLOs".format(name=name)},{"owner":"OWNER"},{"shared":"true"},{"timeFrame":"now-1d"},{"preset":"True"}]}
    projectDir = "{dir}\\{name}-dashboard".format(dir=os.path.split(os.getcwd())[0], name = name)
    

    if not os.path.exists(projectDir):
        os.makedirs(projectDir)
        projectDir = "{dir}\\dashboard".format(dir=projectDir)
        os.makedirs(projectDir)
        with open('{dir}\\dashboard.json'.format(dir=projectDir), 'w') as f:
            json.dump(finalDashboard,f,indent=2)
        with open('{dir}\\dashboard.yaml'.format(dir=projectDir), 'w') as f:
            yaml.dump(dashboardYaml, f)

    else:
        with open('{dir}\\dashboard\\dashboard.json'.format(dir=projectDir), 'w') as f:
           json.dump(finalDashboard,f,indent=2)

def buildDashboard(cleanSlo, slos, dash, cust, dashes, dashLine, line, service, sla, indicator):
    top = 114
    sloTop = 114
    tempTop = 0
    for i in slos:
        addCS(cust,top,i,slos[i]["image"],dash)
        for j in slos[i]["service"]:
            addCS(service, top, j, slos[i]["service"][j]["image"],dash)
            for k in range(len(slos[i]["service"][j]["indicators"])):
                 if slos[i]["service"][j]["indicators"][k]["name"] not in cleanSlo:
                    print("Couldn't add the following SLI or SLO tile to dashboard : {sloName}. Try running monaco again.".format(sloName = slos[i]["service"][j]["indicators"][k]["name"]))
                    continue
                 else:
                    #addCS(service, top, j, slos[i]["service"][j]["image"],dash)
                    tempTop = addIndicatorDash(indicator, sloTop, slos[i]["service"][j]["indicators"][k]["metric"],slos[i]["service"][j]["indicators"][k]["sli"],slos[i]["service"][j]["indicators"][k]["responseTime"],dash)
                    addSlo(cleanSlo[slos[i]["service"][j]["indicators"][k]["name"]],sla, sloTop, slos[i]["service"][j]["indicators"][k]["name"], slos[i]["service"][j]["indicators"][k]["target"], slos[i]["service"][j]["indicators"][k]["type"], dash)
                    sloTop = tempTop
            top = tempTop
        #addDash(dashLine, dashes, top, tempTop, dash)
        top = tempTop
        top = addLine(line, top, dash)
        sloTop = top
        tempTop = 0
        
    return dash

def addLine(line, height, dash):
    lineTemp = copy.deepcopy(line)
    lineTemp[0]["bounds"]["top"] = height
    dash["tiles"].extend(lineTemp)
    return height + lineTemp[0]["bounds"]["height"]

def addDash(dashLine, dashes, top, height, dash):
    '''
    height = height - 114
    rem = math.ceil(height/1254)
    for i in range(len(dashLine)):
        tempTop = top
        if height > 1254:
            maxHeight = 1254
            for j in range(rem):
                tempDashes = copy.deepcopy(dashes)
                tempDashes[0]["bounds"]["left"] = dashLine[i]
                tempDashes[0]["bounds"]["top"] = tempTop
                tempDashes[0]["bounds"]["height"] = maxHeight
                dash["tiles"].extend(tempDashes)
                tempTop = tempTop + maxHeight
                maxHeight = height - maxHeight
        else:
            tempDashes = copy.deepcopy(dashes)
            tempDashes[0]["bounds"]["left"] = dashLine[i]
            tempDashes[0]["bounds"]["top"] = top
            tempDashes[0]["bounds"]["height"] = height
            dash["tiles"].extend(tempDashes)
    '''
    for i in range(len(dashLine)):
        tempDashes = copy.deepcopy(dashes)
        tempDashes[0]["bounds"]["left"] = dashLine[i]
        tempDashes[0]["bounds"]["top"] = top
        tempDashes[0]["bounds"]["height"] = height
        dash["tiles"].extend(tempDashes)


def addSlo(sloId, sla, top, name, target, type, dash):
    slaTemp = copy.deepcopy(sla)
    slaTemp[0]["assignedEntities"].append(sloId)
    slaTemp[0]["metric"] = slaTemp[0]["metric"].format(title = name)
    slaTemp[1]["name"] = "{targ}% {t}".format(targ = target, t = type)

    slaTemp[1]["bounds"]["top"] = top
    top = slaTemp[1]["bounds"]["height"] + top
    slaTemp[0]["bounds"]["top"] = top
    dash["tiles"].extend(slaTemp)

def addIndicatorDash(ind, top, metric, sli, responseTime, dash):
    indTemp = copy.deepcopy(ind)
    if responseTime:
        name = "{sliName} <= {resp}".format(sliName = sli,resp = responseTime)
        indTemp[1]["name"] = name
        indTemp[0]["name"] = name
    else:
        indTemp[1]["name"] = sli
        indTemp[0]["name"] = sli
    indTemp[0]["queries"][0]["metricSelector"] = metric

    indTemp[1]["bounds"]["top"] = top
    top = indTemp[1]["bounds"]["height"] + top
    indTemp[0]["bounds"]["top"] = top
    top = indTemp[0]["bounds"]["height"] + top
    dash["tiles"].extend(indTemp)
    return top

def addCS(cs, top, x, image, dash):
    csTemp = copy.deepcopy(cs)
    csTemp[0]["bounds"]["top"] = top
    csTemp[0]["image"] = image
    top = top + csTemp[0]["bounds"]["height"]
    csTemp[1]["bounds"]["top"] = top
    csTemp[1]["name"] = x
    dash["tiles"].extend(csTemp)

def getSlo(url, apiToken):
    try:
        get = requests.get("{url}/api/v2/slo?pageSize=10000&sort=name&timeFrame=CURRENT&pageIdx=1&demo=false&evaluate=false&enabledSlos=true&showGlobalSlos=true".format(url=url), headers={'Content-Type': 'application/json', 'Authorization' : 'Api-Token {apitoken}'.format(apitoken=apiToken)})
        #get.raise_for_status()
        slo = get.json()
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
    cleanSlo = {}
    for i in slo["slo"]:
        cleanSlo[i["name"]] = i["id"] 
    return cleanSlo

def verifyEnvironment(env, i):
    for x in range(len(env[i])):
        if "env-url" in env[i][x]:
            url = env[i][x]["env-url"]
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
        try:
          fileJSON = json.loads(stream.read())
        except ValueError as err:
            print(err)
    return fileJSON

if __name__ == "__main__":
    main()