> **_Disclaimer:_** This script is not supported by Dynatrace. Please utilize github issues for any issues that arrise. We will try our best to get to your issues.

# Ingesting SonarQube metrics into Dynatrace

This script uses the SonarQube API to gather requested project data, reformats that data into proper ingestable strings [documented here](https://www.dynatrace.com/support/help/extend-dynatrace/extend-metrics/reference/metric-ingestion-protocol#metadata) and sends them off to a Dynatrace insatnce to be ingested. 

## Prerequisites

To execute this script successfully you will need all of the following prereqs:
* SonarQube user token for any user that has permission to the data desired. This can be a Global Analysis Token and it should be if this is being used in an automated scenario. 
> More info on generating this token can be found in the [SonarQube Token Documentation](https://docs.sonarqube.org/latest/user-guide/user-token/)
* Dynatrace access token with the Ingest metrics (```metrics.ingest```) scope
> More info on creating this token can be found in the [Dynatrace API Tokens Docs](https://www.dynatrace.com/support/help/dynatrace-api/basics/dynatrace-api-authentication)
* Python installed on the machine with the [required dependencies](https://github.com/trv-dhecker/cloud-automation/blob/main/sonarqube-metrics/requirements.txt) available 

## Usage

screenshots of it being used and the outputs, etc. go here

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
  
