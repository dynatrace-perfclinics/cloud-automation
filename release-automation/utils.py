import json, requests, subprocess, io, yaml

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

def handlePost(url, header, x, y):
    try:
        #print(json.dumps(y))
        post = requests.post(url, headers=header, params=x, data=json.dumps(y))
        print(json.dumps(post.json()))
        #post.raise_for_status()
        return post.status_code
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

def handlePut(url, header, x, y):
    try:
        #print(json.dumps(y))
        post = requests.put(url, headers=header, params=x, data=json.dumps(y))
        #print(json.dumps(post.json()))
        post.raise_for_status()
        return(post.status_code)
        #print(post.status_code)
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