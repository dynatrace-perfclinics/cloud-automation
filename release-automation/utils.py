import json, requests, subprocess, io, yaml

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
        return(400, f"{s_name} is not a valid file in the serviceflow_cache directory")
        sys.exit()

def handlePost(url, header, x, y, logger):
    try:
        logger.debug(f"handlePost: {url}")
        logger.debug(json.dumps(y, indent=2))
        post = requests.post(url, headers=header, params=x, data=json.dumps(y))
        logger.debug(json.dumps(post.json(), indent=2))
        logger.debug(post.status_code)
        return post.status_code, post.headers
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
        logger.error(f"Failed to post to the dynatrace url: {url}, with exception: {e}")

def handlePut(url, header, x, y, logger):
    try:
        logger.debug(f"handlePut: {url}")
        logger.debug(json.dumps(y, indent=2))
        post = requests.put(url, headers=header, params=x, data=json.dumps(y))
        logger.debug(json.dumps(post.json(), indent=2))
        logger.debug(post.status_code)
        post.raise_for_status()
        return(post.status_code)
    except requests.exceptions.Timeout as err:
        logger.error("The request timed out. Couldn't reach - {url}".format(url = url))
        raise SystemExit(err)
    except requests.exceptions.ConnectionError as err:
        logger.error("The URL was malformed - {url}".format(url = url))
        raise SystemExit(err)
    except requests.exceptions.TooManyRedirects as err:
        logger.error("The URL was malformed - {url}".format(url = url))
        raise SystemExit(err)
    except Exception as e:
        logger.error(f"Failed to put to the dynatrace url: {url}, with exception: {e}")