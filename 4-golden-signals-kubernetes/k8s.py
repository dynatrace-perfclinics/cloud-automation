import os, copy, json, yaml, logging, sys
from statistics import mean
from argparse import ArgumentParser
from utils import prepareMonaco, handleGet, getFileJSON
parser = ArgumentParser()

parser.add_argument("-dtUrl", "--dynatrace-url", dest="dtUrl", help="Dynatrace URL (https://*.live.com)", required=True)
parser.add_argument("-dtToken", "--dynatrace-api-token", dest="dtToken", help="Dynatrace API Token", required=True)
parser.add_argument("-owner", "--dashboard-owner", dest="owner", help="Owner of the Dynatrace Dashboard", required=True)
parser.add_argument("-shared", "--dashboard-shared", dest="shared", help="Set Dynatrace Dashboard to shared", required=True)
parser.add_argument("-preset", "--dashboard-preset", dest="preset", help="Set Dynatrace Dashboard to preset", required=True)
parser.add_argument("-timeFrame", "--dashboard-timeFrame", dest="timeFrame", help="Time Frame to evaluate thresholds", required=True)
parser.add_argument("-warn", "--warn-percent", dest="warnP", help="Percent at which to be warned via threshold", required=True)
parser.add_argument("-pass", "--pass-percent", dest="passP", help="Percent at which to be passed via threshold", required=True)
parser.add_argument("-am","--auto-monaco",dest="autoMonaco",help="Use this to automatically execute monaco to deploy dashboards. (missing = false)", action="store_false")
parser.add_argument("-l", "--logging", action="store", choices=["DEBUG","INFO","ERROR"],default="INFO", help="Optional logging levels, default is INFO if nothing is specified")

args = parser.parse_args()

# Logging
logging.basicConfig(stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s",datefmt='%Y-%m-%d %H:%M:%S') #Sets logging format to "[LEVEL] log message"
logger = logging.getLogger('Dynatrace Automation Bootstrap - 4 Golden Signal k8s')
logger.setLevel(args.logging)

url = args.dtUrl
token = args.dtToken
owner = args.owner
shared = args.shared
preset = args.preset
timeFrame = args.timeFrame
warnP = int(args.warnP)
passP = int(args.passP)
autoMonaco = args.autoMonaco

class Dashboard:
    _dash = getFileJSON("etc/template.json")
    _name = "[4-Golden-Signals] Kubernetes Overview"
    _dashYaml = {}
    _owner = ""
    _timeFrame = ""
    _shared = ""
    _preset = ""

    def __init__(self, owner, timeFrame, shared, preset):
        self._owner = owner
        self._timeFrame = timeFrame
        self._shared = shared
        self._preset = preset
        self._dashYaml = {
        "configs": [
            {
            "id": "k8s4gsignal",
            "type": {
                "api": "dashboard"
            },
            "config": {
                "name": self._name,
                "template": "object.json",
                "skip": False,
                "parameters": {
                    "owner": self._owner,
                    "shared": self._shared,
                    "preset": self._preset,
                    "timeFrame": self._timeFrame
                }
            }
            }
        ]
        }
            
    def addTileToDash(self, tile):
        self._dash["tiles"].append(copy.deepcopy(tile.getTile()))

    def setDashYaml(self, key, val):
        self._dashYaml["configs"][0]["config"]["parameters"][key] = val

    def getDashYaml(self):
        return self._dashYaml
    def getTimeFrame(self):
        return self._timeFrame
    def getDash(self):
        return self._dash

class Project():
    _projectDir = "k8s-4-golden-signals/"

    def __init__(self):
       return 

    def createProject(self, dash):
        if not os.path.exists(self._projectDir):
            os.makedirs(self._projectDir)
        with open('{dir}/{x}'.format(dir=self._projectDir, x = "object.json"), 'w') as f:
            json.dump(dash.getDash(),f, indent=2)
        with open('{dir}/{x}'.format(dir=self._projectDir, x = "config.yaml"), 'w') as f:
            yaml.dump(dash.getDashYaml(), f)
    def getProjectDir(self):
        return self._projectDir

class Tile():
    _tile = getFileJSON("etc/tile.json")
    _metricSelector = ""
    _name = ""
    _sign = ""
    _key = ""
    _entitySelctor = ""

    def __init__(self, metricSelector, name, bounds):
        self._metricSelector = metricSelector
        self._name = name
        self._sign = self._name.split("pass=")[1].split("{")[0]
        self._key = self._name.split("sli=")[1].split(";")[0]
        self._tile["name"] = self._name
        self._tile["queries"][0]["metricSelector"] = self._metricSelector
        self._tile["bounds"] = bounds

    def getTile(self):
        return self._tile
    def getSign(self):
        return self._sign
    def getKey(self):
        return self._key
    def getName(self):
        return self._name
    def setName(self,passKey):
        self._tile["name"] = self._tile["name"].format(cond = "{{{{ .{s} }}}}".format(s = passKey))
    def getMetricSelector(self):
        return self._metricSelector
    def setThreshold(self, threshold):
        self._tile["visualConfig"]["thresholds"][0]["rules"] = threshold["rules"]

class Baseline():
    _warnP = ""
    _passP = ""
    _url = ""
    _api = {'Content-Type': 'application/json', 'Authorization' : "Api-Token {token}"}

    def __init__(self, warnP, passP, url, token):
        self._warnP = warnP
        self._passP = passP
        self._url = url
        self._api["Authorization"] = self._api["Authorization"].format(token=token)

    def setBaseline(self, tile, dash):
        metric = tile.getMetricSelector()
        getMetric = handleGet('{url}/api/v2/metrics/query'.format(url = self._url), self._api, {"metricSelector":metric,"from":dash.getTimeFrame()}, logger)     
        key = tile.getKey()
        sign = tile.getSign()
        if not getMetric["result"][0]["data"]:
            passKey = self._setMetricKey(key,"_pass",self._passP,dash)
            threshold = self._setTreshold(0,0,"{{{{ .{s} }}}}".format(s=passKey))
        else:
            base = mean(filter(None,[i for data in getMetric["result"][0]["data"] for i in data["values"]]))
            if not base:
                passKey = self.setMetricKey(key,"_pass",self._passP,dash)
                threshold = self._setTreshold(0,0,"{{{{ .{s} }}}}".format(s=passKey))
            else:
                if '>=' == sign:
                    value = base - (base*(self._passP/100))
                    warn = base - (base*(self._warnP/100))
                    baseKey = self._setMetricKey(key, "_base",base,dash)
                    passKey = self._setMetricKey(key,"_pass",value,dash)
                    warnKey = self._setMetricKey(key,"_warn",warn,dash)
                    threshold = self._setTreshold("{{{{ .{s} }}}}".format(s=warnKey),"{{{{ .{s} }}}}".format(s=passKey),0)
                else:
                    value = base + (base*(self._passP/100))
                    warn = base + (base*(self._warnP/100))
                    baseKey = self._setMetricKey(key, "_base",base,dash)
                    passKey = self._setMetricKey(key,"_pass",value,dash)
                    warnKey = self._setMetricKey(key,"_warn",warn,dash)
                    threshold = self._setTreshold(0, "{{{{ .{s} }}}}".format(s=warnKey),"{{{{ .{s} }}}}".format(s=passKey))
        tile.setThreshold(threshold)
        tile.setName(passKey)

    def _setMetricKey(self, key, string, val, dash):
        s = key + string
        if not isinstance(val, int):
            dash.setDashYaml(s, str(val))
        else:
            dash.setDashYaml(s, str(val))
        return s

    def _setTreshold(self,x,y,z):
        threshold = {}
        threshold["rules"] = [
              {
                "value": x,
                "color": "#7dc540"
              },
              {
                "value": y,
                "color": "#f5d30f"
              },
              {
                "value": z,
                "color": "#dc172a"
              }
            ]
        return threshold
        
if __name__ == "__main__":
    logger.info("Starting 4-golden-signals-k8s CA dashboard")
    dash = Dashboard(owner, timeFrame, shared, preset)
    metrics = getFileJSON("etc/metrics.json")
    baseline = Baseline(warnP, passP, url, token)
    for metric in metrics:
        logger.info("working on {metric}".format(metric=metric["name"]))
        tile = Tile(metric["metricSelector"],metric["name"],metric["bounds"])
        logger.info("polling baseline")
        baseline.setBaseline(tile, dash)
        logger.info("adding metric+tile to dashboard")
        dash.addTileToDash(tile)
        logger.info("----------------")
    logger.info("***********************************")
    logger.info("Crating Monaco 4-golden-singals-k8s project")
    project = Project()
    project.createProject(dash)
    logger.info("***********************************")
    logger.info("Testing Auto Monaco")
    if not autoMonaco:
        logger.info("")
        prepareMonaco('k8s-4-golden-signals', logger)
    else:
        logger.info("")
        logger.info("Finished! Review ({projectDir}) and run:".format(projectDir='k8s-4-golden-signals'))
        logger.info(r'monaco deploy manifest.yaml --project {projectDir}'.format(projectDir='k8s-4-golden-signals'))
    logger.info("***********************************")