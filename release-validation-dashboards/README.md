# Dynatrace Release Validation Dashboard

This is a Cloud Automation project that automates the creation of Dynatrace Cloud Automation - Release Validation Dashoards for different base technologies including automated thresholds based on a reference timeframe.

This project creates a Dynatrace Monaco based dashboard configuration that you can use to create a dashboard as shown below which includes:
1. Best practice indicators for the selected technology
2. Automatic thresholds based on a reference timeframe

![](./image/dashboard.png)

This dashboard can then be used to automate your release validation!

## Credit goes to Arijan Zenuni

All credit for this project goes to [Arijan Zenuni](https://github.com/ajzenuni) who took the lead of implementing the initial working version of this project. Thank you very much for stepping up and building this!

## Pre-requisites 
1. Installing Dynatrace Monaco

```bash
https://dynatrace-oss.github.io/dynatrace-monitoring-as-code/Get-started/installation
```

2. Create a Dynatrace API-Token with the following permissions

To learn more about API Tokens check out [Dynatrace API Tokens](https://www.dynatrace.com/support/help/dynatrace-api/basics/dynatrace-api-authentication)

```
API v2 scopes
- Read entities
- Write entities
- Read settings
- Write settings
- Read metrics

API v1 scopes
- Read configuration
- Write configuration
```
## Pre-requisites (Python)

1. Installing Python Version 3

```bash
https://www.python.org/download/releases/3.0/
```

2. Installing Python Libaries
```bash
pip install -r requirements.txt
```

## Usage to create release validation dashboard
1. Edit the _environments.yaml:
Create a copy of _environments.yaml.
```bash
cp _environments.yaml environments.yaml
```
- Replace ENVNAME with your environment name

2. Edit the _config.yaml:
Create a copy of _config.yaml
```bash
cp _config.yaml config.yaml
```

The config.yaml contains the configurations of each mz you want to create a cloud automation dashboard. 
The config.yaml contains a setion for the mzs, dashoard and baseline configurations.
###### &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Required:
- mzName : Replace MZNAME with your management zone name
- dash - owner : Replace OWNER with your user in Dynatrace
- ca - project : Replace PROJECT with your cloud automation project
- ca - stage : Replace STAGE with your cloud automation stage
- ca - service : Replace SERVICE with your cloud automation service
###### &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Optional:
- total_pass : Set your total pass used by Cloud Automation SLI evaluation
- total_warn : Set your total warn used by Cloud Automation SLI evaluation
- technology : Select your technology (currently supported - generic,java,nodejs,dotnet, go)
- dash - timeFrame, shared, preset : Set the evaluation timeFrame, shared ('true' or 'false'), preset ('true' or 'false')
- baseline - app_pass,app_warn,service_pass,service_warn,infra_pass,infra_warn: Set your pass conditions for Service,Application,Infrastrucutre (percentage)
- weight - app, service, infra: Set your weight for Service,Application,Infrastructure (Whole Number >= 1)
- keySli - app, service, infra: Set your topSli for Service,Application,Infrastructure ('true' or 'false')

3. Execute the Cloud Automation Dashboard script
###### &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Supported Args:
###### &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Required:
- -caTenant, --cloud-automation-tenant ---------- CloudAutomation Tenant
- -caToken, --cloud-automation-token ------------ CloudAutomation Token
- -dtUrl, --dynatrace-url DTURL ------------------- Dynatrace URL (https://*.live.com)
- -dtToken, --dynatrace-api-token DTTOKEN ---- Dynatrace API Token
###### &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Optional:
- -v, --verify ------------------------------------------- Verify SSL Cert. (missing = true)
- -am, --auto-monaco -------------------------------- Use this to automatically execute monaco to deploy dashboards. (missing = false)
- -aca, --auto-cloud-automation -------------------- Use this to automatically setup a CloudAutomation Project (missing = false)

### PYTHON
```bash
python caDashboard.py -caTenant CLOUDAUTOMATIONTENANT -caToken CLOUDAUTOMATIONTOKEN -dtURL https://*.live.com -dtToken DTAPITOKEN
```

This will generate a new directory for the Relase Validation Dashboard.
This is a monaco project that will contain a dashboard.json and a dashboard.yaml. The dashboard.yaml contains all the pass/warn values generated from the baseline

4. Review the dashboard.yaml

The dashboard.yaml contains all metric thresholds based on the reference timeframe. Feel free to adjust the thresholds before applying the dashboard configuration through monaco!

5. Execute Monaco (optional if you didn't use -am to automatically run monaco)
Clone the Cloud Automation GitHub Repo locally. Set the branch to the correct branch as the one in Cloud Automation.
```bash
	monaco --environments=environments.yaml -p="{PROJECT}-{STAGE}-{SERVICE}/"
```

## Use the dashboard with Cloud Automation

To leverage the dashboard for automated validation simply use a Cloud Automation project that has a matching stage and service to your dashboard. Also make sure that this Cloud Automation project uses a dynatrace.conf.yaml that enables the dashboard query capability. Once that is done every evaluation done by your cloud automation project will use your created dashboard as quality gate definition.
```bash
keptn trigger evaluation --project={PROJECT} --stage={STAGE} --service={SERVICE} --start=2022-04-10T19:40:00 --end=2022-04-11T19:40:00
```
![](./image/evaluationheatmap.png)
