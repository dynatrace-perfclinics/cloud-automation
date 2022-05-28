import json, requests, subprocess, io, yaml

def prepareMonaco(projectDir):
    check = subprocess.check_call(["monaco","--version"])
    if check:
        print("Finished! You can now run:")
        print("monaco --environments=environments.yaml {projectDir}/".format(projectDir=projectDir))
    else:
        print("Running Monaco to deploy dashboard - ({projectDir})".format(projectDir = projectDir))
        subprocess.run(["monaco", "--environments=environments.yaml", r'{projectDir}/'.format(projectDir=projectDir)])

def handleGet(url, header, x):
    try:
        get = requests.get(url, headers=header, params=x)
        get.raise_for_status()
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

def getFileJSON(s_name):
    try:
        fileObj = io.open(s_name, mode="r", encoding="utf-8")
        fileJSON = json.loads(fileObj.read())
        fileObj.close()
        return fileJSON
    except FileNotFoundError:
        return(400, "{} is not a valid file in the serviceflow_cache directory".format(s_name))
        sys.exit()