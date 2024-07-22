#!/usr/bin/python3
"""
Module monitorFems

This module periodically reads data from Fenecon FEMS
and stores data in an InfluxDB or a CSV file
"""

import time
import datetime
import math
import os
import os.path
import json
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
import requests
from requests import codes

# Set up logging
import logging
from logging.config import dictConfig
import logging_plus

logger = logging_plus.getLogger("main")

testRun = False
servRun = False

class FemsAccessError(Exception):
    pass

# Configuration defaults
cfgFile = ""
cfg = {
    "measurementInterval": 120,
    "femsURL": None,
    "femsUsername": None,
    "femsPassword": None,
    "InfluxOutput": False,
    "InfluxURL": None,
    "InfluxOrg": None,
    "InfluxToken": None,
    "InfluxBucket": None,
    "csvOutput": False,
    "csvFile": "",
    "femsData": [],
}

# Constants
CFGFILENAME = "monitorFems.json"


def getCl():
    """
    getCL: Get and process command line parameters
    """

    import argparse
    import os.path

    global logger
    global testRun
    global servRun
    global cfgFile

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
    This program periodically reads data from a FEMS system
    and stores these as measurements in an InfluxDB database.

    If not otherwises specified on the command line, a configuration file
       monitorFems.json
    will be searched sequentially under ./tests/data, $HOME/.config or /etc.

    This configuration file specifies credentials for FEMS access,
    the data to read, the connection to the InfluxDB and other runtime parameters.
    """,
    )
    parser.add_argument(
        "-t", "--test", action="store_true", help="Test run - single cycle - no wait"
    )
    parser.add_argument(
        "-s", "--service", action="store_true", help="Run as service - special logging"
    )
    parser.add_argument(
        "-l", "--log", action="store_true", help="Shallow (module) logging"
    )
    parser.add_argument("-L", "--Log", action="store_true", help="Deep logging")
    parser.add_argument("-F", "--Full", action="store_true", help="Full logging")
    parser.add_argument("-p", "--logfile", help="path to log file")
    parser.add_argument(
        "-f", "--file", help="Logging configuration from specified JSON dictionary file"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose - log INFO level"
    )
    parser.add_argument("-c", "--config", help="Path to config file to be used")

    args = parser.parse_args()

    # Disable logging
    logger = logging_plus.getLogger("main")
    logger.addHandler(logging.NullHandler())
    rLogger = logging_plus.getLogger()
    rLogger.addHandler(logging.NullHandler())

    # Set handler and formatter to be used
    handler = logging.StreamHandler()
    if args.logfile:
        handler = logging.FileHandler(args.logfile)
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
    formatter2 = logging.Formatter(
        "%(asctime)s %(name)-33s %(levelname)-8s %(message)s"
    )
    handler.setFormatter(formatter)

    if args.log:
        # Shallow logging
        handler.setFormatter(formatter2)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    if args.Log:
        # Deep logging
        handler.setFormatter(formatter2)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    if args.Full:
        # Full logging
        handler.setFormatter(formatter2)
        rLogger.addHandler(handler)
        rLogger.setLevel(logging.DEBUG)
        # Activate logging of function entry and exit
        logging_plus.registerAutoLogEntryExit()

    if args.file:
        # Logging configuration from file
        logDictFile = args.file
        if not os.path.exists(logDictFile):
            raise ValueError(
                "Logging dictionary file from command line does not exist: "
                + logDictFile
            )

        # Load dictionary
        with open(logDictFile, "r") as f:
            logDict = json.load(f)

        # Set config file for logging
        dictConfig(logDict)
        logger = logging.getLogger()
        # Activate logging of function entry and exit
        # logging_plus.registerAutoLogEntryExit()

    # Explicitly log entry
    if args.Log or args.Full:
        logger.logEntry("getCL")
    if args.log:
        logger.debug("Shallow logging (main only)")
    if args.Log:
        logger.debug("Deep logging")
    if args.file:
        logger.debug("Logging dictionary from %s", logDictFile)

    if args.verbose or args.service:
        if not args.log and not args.Log and not args.Full:
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

    if args.test:
        testRun = True

    if args.service:
        servRun = True

    if testRun:
        logger.debug("Test run mode activated")
    else:
        logger.debug("Test run mode deactivated")

    if servRun:
        logger.debug("Service run mode activated")
    else:
        logger.debug("Service run mode deactivated")

    if args.config:
        cfgFile = args.config
        logger.debug("Config file: %s", cfgFile)
    else:
        logger.debug("No Config file specified on command line")

    if args.Log or args.Full:
        logger.logExit("getCL")


def getConfig():
    """
    Get configuration for fritzToInfluxHA
    """
    global cfgFile
    global cfg
    global logger

    # Check config file from command line
    if cfgFile != "":
        if not os.path.exists(cfgFile):
            raise ValueError(
                "Configuration file from command line does not exist: ", cfgFile
            )
        logger.info("Using cfgFile from command line: %s", cfgFile)

    if cfgFile == "":
        # Check for config file in ./tests/data directory
        curDir = os.path.dirname(os.path.realpath(__file__))
        curDir = os.path.dirname(curDir)
        cfgFile = curDir + "/tests/data/" + CFGFILENAME
        if not os.path.exists(cfgFile):
            # Check for config file in /etc directory
            logger.info("Config file not found: %s", cfgFile)
            cfgFile = ""

    if cfgFile == "":
        # Check for config file in ./config directory
        curDir = os.path.dirname(os.path.realpath(__file__))
        curDir = os.path.dirname(curDir)
        cfgFile = curDir + "/config/" + CFGFILENAME
        if not os.path.exists(cfgFile):
            # Check for config file in ./config directory
            logger.info("Config file not found: %s", cfgFile)
            cfgFile = ""

    if cfgFile == "":
        # Check for config file in $HOME/.config directory
        homeDir = os.environ["HOME"]
        cfgFile = homeDir + "/.config/" + CFGFILENAME
        if not os.path.exists(cfgFile):
            logger.info("Config file not found: %s", cfgFile)
            # Check for config file in etc directory
            cfgFile = "/etc/" + CFGFILENAME
            if not os.path.exists(cfgFile):
                logger.info("Config file not found: %s", cfgFile)
                cfgFile = ""

    if cfgFile == "":
        # No cfg available
        logger.info("No config file available. Using default configuration")
    else:
        logger.info("Using cfgFile: %s", cfgFile)
        with open(cfgFile, "r") as f:
            conf = json.load(f)
            if "measurementInterval" in conf:
                cfg["measurementInterval"] = conf["measurementInterval"]
            if "femsURL" in conf:
                cfg["femsURL"] = conf["femsURL"]
            if "femsUsername" in conf:
                cfg["femsUsername"] = conf["femsUsername"]
            if "femsPassword" in conf:
                cfg["femsPassword"] = conf["femsPassword"]
            if "InfluxOutput" in conf:
                cfg["InfluxOutput"] = conf["InfluxOutput"]
            if "InfluxURL" in conf:
                cfg["InfluxURL"] = conf["InfluxURL"]
            if "InfluxOrg" in conf:
                cfg["InfluxOrg"] = conf["InfluxOrg"]
            if "InfluxToken" in conf:
                cfg["InfluxToken"] = conf["InfluxToken"]
            if "InfluxBucket" in conf:
                cfg["InfluxBucket"] = conf["InfluxBucket"]
            if "csvOutput" in conf:
                cfg["csvOutput"] = conf["csvOutput"]
            if "csvDir" in conf:
                cfg["csvDir"] = conf["csvDir"]
            if cfg["csvDir"] == "":
                cfg["csvOutput"] = False
            if "femsData" in conf:
                cfg["femsData"] = conf["femsData"]

    # Check FEMS credentials
    if not cfg["femsUsername"]:
        raise ValueError("femsUsername not specified")
    if not cfg["femsPassword"]:
        raise ValueError("femsPassword not specified")

    logger.info("Configuration:")
    logger.info("    measurementInterval:%s", cfg["measurementInterval"])
    logger.info("    femsUsername:%s", cfg["femsUsername"])
    logger.info("    femsPassword:%s", cfg["femsPassword"])
    logger.info("    InfluxOutput:%s", cfg["InfluxOutput"])
    logger.info("    InfluxURL:%s", cfg["InfluxURL"])
    logger.info("    InfluxOrg:%s", cfg["InfluxOrg"])
    logger.info("    InfluxToken:%s", cfg["InfluxToken"])
    logger.info("    InfluxBucket:%s", cfg["InfluxBucket"])
    logger.info("    csvOutput:%s", cfg["csvOutput"])
    logger.info("    csvFile:%s", cfg["csvFile"])
    logger.info("    femsData:%s", len(cfg["femsData"]))


def waitForNextCycle(waitUntilMidnight: bool = False):
    """
    Wait for next measurement cycle.

    This function assures that measurements are done at specific times depending on the specified interval
    In case that measurementInterval is an integer multiple of 60, the waiting time is calculated in a way,
    that one measurement is done every full hour.
    """
    global cfg

    if waitUntilMidnight:
        tNow = datetime.datetime.now()
        waitTimeSec = 24 * 60 * 60 - (
            3600 * tNow.hour + 60 * tNow.minute + tNow.second + tNow.microsecond / 1000000
        ) + 1
        time.sleep(waitTimeSec)

    elif (
        (cfg["measurementInterval"] % 60 == 0)
        or (cfg["measurementInterval"] % 120 == 0)
        or (cfg["measurementInterval"] % 240 == 0)
        or (cfg["measurementInterval"] % 300 == 0)
        or (cfg["measurementInterval"] % 360 == 0)
        or (cfg["measurementInterval"] % 600 == 0)
        or (cfg["measurementInterval"] % 720 == 0)
        or (cfg["measurementInterval"] % 900 == 0)
        or (cfg["measurementInterval"] % 1200 == 0)
        or (cfg["measurementInterval"] % 1800 == 0)
    ):
        tNow = datetime.datetime.now()
        seconds = 60 * tNow.minute
        period = math.floor(seconds / cfg["measurementInterval"])
        waitTimeSec = (period + 1) * cfg["measurementInterval"] - (
            60 * tNow.minute + tNow.second + tNow.microsecond / 1000000
        )
        logger.debug(
            "At %s waiting for %s sec.",
            datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S,"),
            waitTimeSec,
        )
        time.sleep(waitTimeSec)
    elif (
        (cfg["measurementInterval"] % 2 == 0)
        or (cfg["measurementInterval"] % 4 == 0)
        or (cfg["measurementInterval"] % 5 == 0)
        or (cfg["measurementInterval"] % 6 == 0)
        or (cfg["measurementInterval"] % 10 == 0)
        or (cfg["measurementInterval"] % 12 == 0)
        or (cfg["measurementInterval"] % 15 == 0)
        or (cfg["measurementInterval"] % 20 == 0)
        or (cfg["measurementInterval"] % 30 == 0)
    ):
        tNow = datetime.datetime.now()
        seconds = 60 * tNow.minute + tNow.second
        period = math.floor(seconds / cfg["measurementInterval"])
        waitTimeSec = (period + 1) * cfg["measurementInterval"] - seconds
        logger.debug(
            "At %s waiting for %s sec.",
            datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S,"),
            waitTimeSec,
        )
        time.sleep(waitTimeSec)
    else:
        waitTimeSec = cfg["measurementInterval"]
        logger.debug(
            "At %s waiting for %s sec.",
            datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S,"),
            waitTimeSec,
        )
        time.sleep(waitTimeSec)
        
def getFemsSession() -> requests.session:
    """
    Log into FEMS and return the session
    """
    session = requests.Session()
    session.auth = (cfg["femsUsername"], cfg["femsPassword"])
    return session    

def getFemsData(session, femsd: dict) -> dict:
    url = cfg["femsURL"] + femsd["query"]
    try:
        response = session.get(url)
        response.raise_for_status()
        respDict = json.loads(response.text)
    except requests.exceptions.HTTPError as e:
        logger.error("Error getting _sum data: %s", e)
        raise FemsAccessError
    except requests.exceptions.RequestException as e:
        logger.error("Error getting _sum data: %s", e)
        raise FemsAccessError
    except Exception as e:
        logger.error("Error getting _sum data: %s", e)
        raise FemsAccessError
    return respDict

def getTagsFromKey(key: str, tpl: str, tags: dict) -> dict:
    """Analyze a key and add found tags to the given tags dict
    
    params:
    key:    key in the form "xxxxx0", "xxxxx0yyyy1", "xxxxx0yyyy1zzz123"
    tpl:    tpl in the form "xxxxx?", "xxxxx?yyyy?", "xxxxx?yyyy?zzz???"
    tags:   a dict of tags to which new tags will be added
    return: augmented dict of tags
            xxxxx, yyyy, zzz are tag names
            substrings at ? are tag values
    """
    keyRem = key
    tplRem = tpl
    if len(keyRem) < len(tplRem):
        raise ValueError("Key shorter than template:" + keyRem + ", " + tplRem)

    allDone = False
    while not allDone and len(keyRem) > 0:
        p1 = tplRem.find("?")
        if p1 >= 0:
            p2 = p1 + 1
            done = False
            while not done and p2 <= len(tplRem):
                if tplRem[p2-1:p2] != "?":
                    done = True
                else:
                    if p2 == len(tplRem):
                        done = True
                    elif tplRem[p2:p2 + 1] != "?":
                        done = True
                    else:
                        p2 += 1
            tagName = keyRem[0:p1]
            tagValue = keyRem[p1:p2]
            tags[tagName] = tagValue
            if p2 < len(keyRem):
                keyRem = keyRem[p2:]
                tplRem = tplRem[p2:]
            else:
                allDone = True
        else:
            allDone = True
    return tags

def storeFemsData(influxWriteAPI, frd: dict, femsd: dict):
    """
    Store FEMS _sum data in InfluxDB or file

    """
    csvFile = cfg["csvDir"] + femsd["csvFile"]
    sep = ";"

    if "tag_datapoints" in femsd:
        tagDp = femsd["tag_datapoints"]
    else:
        tagDp = {}
    nrTagDp = len(tagDp)
    fieldDp = femsd["field_datapoints"]
    nrFieldDp = len(fieldDp)
    dpStart = len(femsd["channel_root"]) - 1
    
    pointDict = {}
    
    for el in frd:
        addr = el["address"]
        p = addr.find("/")
        comp = addr[0:p]
        chan = addr[p+1:]
        type = el["type"]
        unit = el["unit"]
        value = el["value"]
        
        dpName = chan[dpStart:]

        #Get tags from component
        tags = {}
        tags = getTagsFromKey(comp, femsd["component"][1:], tags)
        
        #Get tags from channel
        tags = getTagsFromKey(chan, femsd["channel_root"][1:], tags)
            
        #Datapoint key is a unique set of tags from FEMS datapoint keys
        pointKey = ""
        for tagKey, tagValue in tags.items():
            pointKey += str(tagValue)
        if pointKey == "":
            pointKey = "#EMPTY#"
            
        if pointKey in pointDict:
            point = pointDict[pointKey]
        else:
            point = {}
            point["measurement"] = femsd["measurement"]
            point["time"] = mTS
            point["tags"] = tags
            point["fields"] = {}
            pointDict[pointKey] = point
        
        #Get tag from datapoint
        for i in range(nrTagDp):
            dp = tagDp[i]
            if dp == dpName:
                point["tags"][dp] = value
                break
        
        for i in range(nrFieldDp):
            dp = fieldDp[i]
            if dp == dpName:
                if type == "INTEGER":
                    val = int(value)
                elif type == "LONG":
                    val = int(value)
                elif type == "DOUBLE":
                    val = float(value)
                elif type == "BOOLEAN":
                    if value == 1:
                        val = True
                    else:
                        val = False
                else:
                    val = value
                point["fields"][dp] = val
                break

    for pointKey, point in pointDict.items():
        if len(point["fields"]) > 0:
            if cfg["InfluxOutput"] == True:
                influxWriteAPI.write(cfg["InfluxBucket"], cfg["InfluxOrg"], point)
                logger.debug("FEMS data written to Influx DB for key %s", pointKey)
            if cfg["csvOutput"] == True:
                title = "_measureemnt" + sep + "_time"
                if len(point["tags"]) > 0:
                    for key, value in point["tags"].items():
                        title = title + sep + key
                for i in range(nrFieldDp):
                    title = title + sep + fieldDp[i]
                title = title + "\n"
                data = point["measurement"] + sep + point["time"]
                if len(point["tags"]) > 0:
                    for key, value in point["tags"].items():
                        data = data + sep + value
                for i in range(nrFieldDp):
                    data = data + sep + str(point["fields"][fieldDp[i]])
                data = data + "\n"
                writeCsv(csvFile, title, data)
                logger.debug("FEMS data written to csv file for key %s", pointKey)


def writeCsv(fp, title, data):
    """
    Write data to CSV file
    """
    f = None
    newFile = True
    if os.path.exists(fp):
        newFile = False
    if newFile:
        os.makedirs(cfg["csvDir"], exist_ok=True)
        f = open(fp, "w")
    else:
        f = open(fp, "a")
    logger.debug("File opened: %s", fp)

    if newFile:
        f.write(title)
    f.write(data)
    f.close()


# ============================================================================================
# Start __main__
# ============================================================================================
#
# Get Command line options
getCl()

logger.info("=============================================================")
logger.info("monitorFems started")
logger.info("=============================================================")

# Get configuration
getConfig()

fb = None
influxClient = None
influxWriteAPI = None

try:
    # Instatntiate InfluxDB access
    if cfg["InfluxOutput"]:
        influxClient = influxdb_client.InfluxDBClient(
            url=cfg["InfluxURL"], token=cfg["InfluxToken"], org=cfg["InfluxOrg"]
        )
        influxWriteAPI = influxClient.write_api(write_options=SYNCHRONOUS)
        logger.debug("Influx interface instantiated")

except Exception as error:
    logger.critical("Unexpected Exception (%s): %s", error.__class__, error.__cause__)
    logger.critical("Unexpected Exception: %s", error.message)
    logger.critical("Could not get InfluxDB access")
    stop = True
    influxClient = None
    influxWriteAPI = None


noWait = False
waitUntilMidnight = False
stop = False
failcount = 0
loggedIn = False
vwc = None
newLoginMax = math.floor(3599 / cfg["measurementInterval"])
newLoginCount = 0

while not stop:
    try:
        # Wait unless noWait is set in case of VWError.
        # Skip waiting for test run
        if not noWait and not testRun:
            waitForNextCycle(waitUntilMidnight)
        noWait = False
        waitUntilMidnight = False

        logger.info("monitorFems - cycle started")
        local_datetime = datetime.datetime.now()
        local_datetime_timestamp = round(local_datetime.timestamp())
        UTC_datetime_converted = datetime.datetime.utcfromtimestamp(
            local_datetime_timestamp
        )
        mTS = UTC_datetime_converted.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")

        session = getFemsSession()

        if "femsData" in cfg:
            fd = cfg["femsData"]
            for fde in fd:
                fmsd = getFemsData(session, fde)
                storeFemsData(influxWriteAPI, fmsd, fde)

        logger.info("monitorFems - cycle completed")

        if testRun:
            # Stop in case of test run
            stop = True

    except FemsAccessError:
        logger.info("No access to FEMS")
        stop = False
        noWait = False

    except Exception as error:
        stop = True
        logger.critical("Unexpected Exception: %s", error)
        if vwc:
            del vwc
        if influxClient:
            del influxClient
        if influxWriteAPI:
            del influxWriteAPI
        raise error

    except KeyboardInterrupt:
        stop = True
        logger.debug("KeyboardInterrupt")
        if influxClient:
            del influxClient
        if influxWriteAPI:
            del influxWriteAPI
if influxClient:
    del influxClient
if influxWriteAPI:
    del influxWriteAPI
logger.info("=============================================================")
logger.info("monitorFems terminated")
logger.info("=============================================================")
