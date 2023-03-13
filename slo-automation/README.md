> **_Disclaimer:_** This script is not supported by Dynatrace. Please utilize github issues for any issues that arrise. We will try our best to get to your issues.

# SLO Automation

This is a cloud automation project that automates the creation of SLOs for Application, Key User Action, Service, Service Method entity types. It's possible to create both performance and availability based SLOs.

## Pre-requisites 

1. Installing monaco

```bash
https://www.dynatrace.com/support/help/shortlink/configuration-as-code-installation
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
4. Edit manifest.yaml

Replace the placeholders in the environmentGroups:

> ENV_NAME
> ENV_ID
> API_TOKEN

```bash
environmentGroups:
- name: default
  environments:
  - name: ENV_NAME
    url:
      value: https://ENV_ID.live.dynatrace.com
    token:
      name: API_TOKEN
```

## Usage
The slo folder contains the config.yaml and object.json.
You'll need to add any additional slos to the config.yaml.

#### Example - Service Performance SLO
1. Edit the slo/config.yaml file. 

Replace the parameter values with your own values. 
```yaml
      parameters:
        enabled: true
        sli: perf
        entity: service
        filter:
          type: value
          value:
          - tag: project:easytravel
          - name: BookingService
        threshold: 2500
        percentile: 95
        target: 99
        warning: 99.98
        timeFrame: now-1d
        burnRate:
          type: value
          value:
            enabled: true
            fastBurnThreshold: 10
```
> Most Monaco v2 projects contain a "default" parameter. Which returns the setting/configuration back to defaults if set to true.

3. Run the monaco command in the /project directory
```bash
monaco deploy manifest.yaml --project slo -e ENV_NAME
```