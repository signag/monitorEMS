""" Program to try OpenEMS REST-API calls

    Before usage, copy this file to $PARENTDIR/tests and name it according to your needs

    1. Set 'emsURL' to the URL of your system
    2. Set 'component' to one of the components shown in your OpenEMS configuration
    3. Adjust the name of the 'csvFile' to be produced
    4. Run the program in the virtual environment for monitorEMS.
       It will create the CSV file under an 'emsOutput' subdirectory.
    5. From the CSV file, select the data points to be monitored
    6. Adjust the regular expression in 'channel' to a more restrictive variant
    7. Use the resulting output to set up an 'emsData' entry in 'monitorEMS.json'
"""

import requests
import json
import os

# === Adjust here ==============
emsUrl = "http://<emsName|IP>:80"
component = "_sum"
channel = ".*"
csvFile = "ems__sum.csv"
# ==============================

fd = "emsOutput"
fp = fd + "/" + csvFile

url = emsUrl + "/rest/channel/" + component + "/" + channel

user = "x"
password = "user"

session = requests.Session()
session.auth = (user, password)

response = session.get(url)
response.raise_for_status()

resp = json.loads(response.text)

f = None
os.makedirs(fd, exist_ok=True)
f = open(fp, "w", encoding="utf-8")
title = "address;type;accessMode;text;unit;value\n"
f.write(title)
for el in resp:
    data = f'{el["address"]};{el["type"]};{el["accessMode"]};{el["text"]};{el["unit"]};{el["value"]}\n'
    f.write(data)
f.close()
