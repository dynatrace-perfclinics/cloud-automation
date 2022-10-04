import json, requests, subprocess, io, yaml

def prepareMonaco(projectDir, logger):
    check = subprocess.check_call(["monaco","--version"])
    if check:
        logger.info("Finished! You can now run:")
        logger.info("monaco --environments=environments.yaml {projectDir}/".format(projectDir=projectDir))
    else:
        logger.info("Running Monaco to deploy dashboard - ({projectDir})".format(projectDir = projectDir))
        subprocess.run(["monaco", "--environments=environments.yaml", r'{projectDir}/'.format(projectDir=projectDir)])

def createCADashboardProject(dir,j,d,dashboardYaml,finalDash):
    with open('{dir}{j}'.format(dir=dir, j = j), 'w') as f:
        json.dump(finalDash,f, indent=2)
    with open('{dir}{d}'.format(dir=dir, d = d), 'w') as f:
        yaml.dump(dashboardYaml, f)

def handleGet(url, header, x, logger):
    try:
        logger.debug(f"handleGet: {url}")
        logger.debug(json.dumps(x, indent=2))
        get = requests.get(url, headers=header, params=x)
        get.raise_for_status()
        resp = get.json()
        return resp
    except requests.exceptions.HTTPError as err:
        logger.error({err})
        raise SystemExit(err)
    except requests.exceptions.Timeout as err:
        logger.error(f"The request timed out. Couldn't reach - {url}")
        raise SystemExit(err)
    except requests.exceptions.ConnectionError as err:
        logger.error(f"The URL was malformed - {url}")
        raise SystemExit(err)
    except requests.exceptions.TooManyRedirects as err:
        logger.error(f"The URL was malformed - {url}")
        raise SystemExit(err)
    except Exception as e:
        logger.error(f"Failed to get the dynatrace url: {url}, with exception: {e}")
        return get.text

def getFileJSON(s_name):
    try:
        fileObj = io.open(s_name, mode="r", encoding="utf-8")
        fileJSON = json.loads(fileObj.read())
        fileObj.close()
        return fileJSON
    except FileNotFoundError:
        return(400, "{} is not a valid file in the serviceflow_cache directory".format(s_name))
        sys.exit()