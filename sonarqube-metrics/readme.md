> **_Disclaimer:_** This script is not supported by Dynatrace. Please utilize github issues for any issues that arrise. We will try our best to get to your issues.

# Ingesting SonarQube metrics into Dynatrace

This script uses the SonarQube API to gather requested project data, reformats that data into proper ingestable strings as [documented here](https://www.dynatrace.com/support/help/extend-dynatrace/extend-metrics/reference/metric-ingestion-protocol#metadata) and sends them off to a Dynatrace insatnce to be ingested. 

## Prerequisites

To execute this script successfully you will need all of the following prerequisites.
* SonarQube user token for any user that has permission to the data desired. This can be a Global Analysis Token and it should be if this is being used in an automated scenario. 
> More info on generating this token can be found in the [SonarQube Token Documentation](https://docs.sonarqube.org/latest/user-guide/user-token/)
* Dynatrace access token with the Ingest metrics (```metrics.ingest```) scope
> More info on creating this token can be found in the [Dynatrace API Authentication Documentation](https://www.dynatrace.com/support/help/dynatrace-api/basics/dynatrace-api-authentication)
* Python installed on the machine with the [required dependencies](https://github.com/trv-dhecker/cloud-automation/blob/main/sonarqube-metrics/requirements.txt) available  
To ensure this run ```pip install -r cloud-automation/sonarqube-metrics/requirements.txt``` in the environemnet that will execute the script.

## Usage

### Arguments

#### Required:

    sonarqube-url (su) - SonarQube Base URL without trailing slash, Example: https://sonarqube.company.com 
    sonarqube-token (st) - SonarQube API Token
    sonarqube-component (c) - SonarQube Identifier for which project's data will be attained
    dynatrace-url (du) - Dynatrace Base URL without trailing slash, Example: https://dynatrace.company.com
    dynatrace-token (dt) - Dynatrace token
    
#### Optional:

    sonarqube-metrickeys (m) - List of values cooresponding to which metricKeys are desired from the SonarQube API, this will default to all available metrics if none are provided
    sonarqube-branch (b) - Branch name in SonarQube to pull data for
    additional-dimensions (d) - Optional additional dimensions in a comma separated list (Ex. component.line_of_business='IT',component.portfolio='')
    ignore-warnings (i) - Flag used to suppress warnings and allow for hitting servers without good certs, defaulted to False as this should never be set to true in a production environment
    logging (l) - Optional logging levels, default is INFO if nothing is specified
### Instructions

#### Using from command line

Use from command line is straight forward, call the script like you would any other python script. Be sure to privide all required arguments.  
Example:

```
> python ./ingest_sonarqube_metrics_into_dynatrace.py -su "https://sonarqube.company.com" -st ***** -c "My_Example_App" -b "main" -du "https://dynatrace.company.com" -dt ***** -d "component.line_of_business='IT',component.portfolio='My_Portfolio'"
[INFO] Querying SonarQube API for all available metrics
[INFO] Querying SonarQube API for component specific metrics
[INFO] Processing Data
[INFO] Processing Data
[INFO] Processing Data
[INFO] Sending Metrics to Dynatrace Endpoint
```

#### Using in an automated Pipeline

##### Use from a declarative Jenkins Pipeline

##### Use from a GitHub Action
