# SLO Automation

This is a cloud automation project that automates the creation of SLOs for Application, Key User Action, Service, Service Method entity types. It's possible to create both performance and availability based SLOs.

## Pre-requisites 

1. Installing monaco

```bash
https://dynatrace-oss.github.io/dynatrace-monitoring-as-code/Get-started/installation
```

2. Create an API-Token with the following permissions
```
API v2 scopes
- Read entities
- Write entities
- Read settings
- Write settings
- Read SLO
- Write SLO

API v1 scopes
- Read configuration
- Write configuration
```

3. Set Environment Variables
```bash
 export API_TOKEN="API_TOKEN"
```
4. Edit environments.yaml

Replace the env-token-name with your env token name
```bash
- env-token-name: "example_token"
```

## Usage
Each sub-directory correlates to an entity, and contains the monaco configs to create either performance or availability SLOs.
- _application = Application
- kua = Key User Action (requires that user actions are marked at KEY)
- service = Service
- ksm = Key Service Method (requires that service methods are marked at KEY)

Performance SlOs configs are in the perf directory for each entity.

Availability SLOs configs are in the avail directory for each entity.

#### Service Performance SLO via Monaco Example
1. Edit the /service/perf/csm/calculated-metrics-service/_calc.yaml file. 

Replace the placeholders defined by {...}
```yaml
config:
  - demo_calc: "_calc.json"

demo_calc:
  - name: "calc:service.{ENV}.{APPNAME}.{SERVICENAME}.perf"
  - responseTime: "{TIME}"
  - tagKey: "{TAG KEY}"
  - tagValue: "{TAG VALUE}"
```

2. Edit the /service/perf/_slo/slo/_slo.yaml file.

Replace the placeholders defined by {...}
```yaml
config:
  - demo_slo: "_slo.json"

demo_slo:
  - name: "{EMV} - {APPNAME} - {SERVICE NAME} - perf"
  - serviceId: "SERVICE-{ID}"
  - calcMetric: "service/perf/csm/calculated-metrics-service/demo_calc.name"
  - target: "95.0"
  - warning: "97.5"
  - timeFrame: now-1d
```
3. Run the monaco command in the /project directory
```bash
monaco --environments=environments.yaml -p="perf/_slo, perf/csm" service/
```

## SLO Monaco Commands
#### Application Availability SLO
```bash
monaco --environments=environments.yaml -p="avail/" _application/
```
#### Application Performance SLO
```bash
monaco --environments=environments.yaml -p="perf/_slo, perf/cmaw" _application/
```
#### Key User Action Availability SLO
```bash
monaco --environments=environments.yaml -p="avail/_slo, avail/cmaw" kua/
```
#### Key User Action Performance SLO
```bash
monaco --environments=environments.yaml -p="perf/_slo, perf/cmaw" kua/
```
#### Service Availability SLO
```bash
monaco --environments=environments.yaml -p="avail/" service/
```
#### Service Performance SLO
```bash
monaco --environments=environments.yaml -p="perf/_slo, perf/csm" service/
```
#### Key Service Method Availability SLO
```bash
monaco --environments=environments.yaml -p="avail/_slo, avail/csm" ksm/
```
#### Key Service Method Performance SLO
```bash
monaco --environments=environments.yaml -p="perf/_slo, perf/csm" ksm/
```
## Troubleshooting
### 1. Running an SLO that requires a calculated metric fails on the first go.
#### This will happen because the SLO is generated at the same time as the calculated metric. The Dynatrace SLO API may not have registered the calculated metric. 
#### Solution : Run the same monaco command again. 