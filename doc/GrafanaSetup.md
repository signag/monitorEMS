# Setup of monitorEMS Dashboards for Grafana

[![Up](img/goup.gif)](../README.md)

The dashboards included in this package have been developed with [Grafana Open Source](https://grafana.com/oss/grafana/) (Grafana OSS 11.1).

If you are already using Grafana, you can add these dashboards to your existing instance.

## Docker Installation of Grafana

If you are new to Grafana, it is recommended to install the Docker image  of Grafana OSS:    
<https://grafana.com/grafana/download?pg=oss-graf&platform=docker&edition=oss>

Details of the setup are described in [Run Grafana Docker Image](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/).

Short version:

1. From a command prompt of the machine where Docker is running:<br>```docker run -d --name=grafana -p 3000:3000 grafana/grafana-oss```
2. From a browser on any client in the same network:<br>```http://<hostname>:3000```<br>where ```<hostname>```is the host name or IP address of the Docker machine
3. On the Login screen, enter "admin" for both, username and password
4. On request enter a new password

## Configuring the Data Source

1. Under *Connections*, choose *Add new connection* and select *InfluxDB*
2. On the configuration screen, set<br>**Query language**: Flux<br>**URL**: URL for the Influx DB<br>**Auth**: deselect all options<br>**InfluxDB Details/Organization**: Organization specified during Influx setup.<br>**InfluxDB Details/Token**: The token created in Influx.
3. Push *Save & test*

## Importing the Dashboards

You can download JSON exports of the monitorEMS dashboards from the [grafana](./../grafana/) folder of this repository.

To import these into an existing Grafana instance, proceed as follows:

1. Open the *Dashboards* overview
2. Push the *New* button and select *Import*
4. Navigate to one of the downloaded JSON files and push *Import*

