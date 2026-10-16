# Update History
# Version 6.1
# 2024-04-16    JRP     Fatigue detection on 0 kmph. Requested by BC.
#                       Add improvements to avoid/reduce possibility of run time errors

import uuid
import os
import time

import traceback
from classes.Config import *
from classes.RedisManager import *
# from classes.MMFServer import *
from classes.Camera import *
from classes.VisualizerFront import *

import json

# def parseUDP(message):
#     # times|deviceid|unitno|speed|lat|lon|sta|segment|road|maxroadspeed|
#     arrmsg = None
#     if message is None:
#         return None
#     try:
#         arrmsg = message.popleft().split("|")
#         if len(arrmsg)<1:
#             return None
#         else:
#             return arrmsg
#     except:
#         return None
    # print(arrmsg)


def parseUDP(message):

    if not message or len(message) == 0:
        return None

    # Check if writer is dead
    if message == "DEAD":
        return "RESET"

    try:
        raw = message.popleft()

        data = json.loads(raw)

        timestamp       = int(data.get("timestamp", int(time.time())))
        device_id       = data.get("device_id", "NA")
        unit_no         = data.get("unit_no", "NA")
        speed           = str(data.get("speed", "-9999"))
        latitude        = data.get("latitude", "-6666")
        longitude       = data.get("longitude", "-6666")
        sta             = data.get("sta", "UNKNOWN")
        segment         = data.get("segment", "UNKNOWN")
        road            = data.get("road", "UNKNOWN")
        max_speed       = data.get("max_speed", "40")
        rpm             = str(data.get("rpm", "-6666"))
        gear            = str(data.get("gear", "-6666"))
        numsat          = data.get("numsat", "-6666")
        gpsdatalogheartbeat       = int(data.get("timestamp", int(time.time())))

        return (
            timestamp,
            device_id,
            unit_no,
            speed,
            latitude,
            longitude,
            sta,
            segment,
            road,
            max_speed,
            rpm,
            gear,
            numsat,
            gpsdatalogheartbeat
        )
    except Exception as e:
        print("Parse error:", e)
        return None
    
# Initiate config reader
deviceconfig = Config("D:\\smartd\\script\\mh02model\\files\\configs\\smartd.json")
DEVICE_ID = deviceconfig.getValue("DEVICE_ID")
UNIT_NO = deviceconfig.getValue("UNIT_NO")

config = Config("D:\\smartd\\script\\mh02model\\files\\configs\\mh02_front.json")
CAM_URL = config.getValue("CAM_URL")
UDP_LOCAL_PORT = config.getValue("UDP_LOCAL_PORT")
UDP_BUFFER_SIZE = config.getValue("UDP_BUFFER_SIZE")
RECORDING_FPS = config.getValue("RECORDING_FPS")
MAX_PRE_FRAMES = config.getValue("MAX_PRE_FRAMES")
MAX_POST_FRAMES = config.getValue("MAX_POST_FRAMES")

overspeedconfig = Config("D:\\smartd\\script\\mh02model\\files\\configs\\mh02_front_overspeed.json")
UNKNOWN_OVERSPEED_DT = overspeedconfig.getValue("UNKNOWN_OVERSPEED_DT")
UNKNOWN_OVERSPEED_LD = overspeedconfig.getValue("UNKNOWN_OVERSPEED_LD")
UNKNOWN_OVERSPEED_FT = overspeedconfig.getValue("UNKNOWN_OVERSPEED_FT")
UNKNOWN_OVERSPEED_PM = overspeedconfig.getValue("UNKNOWN_OVERSPEED_PM")
UNKNOWN_OVERSPEED_BUS = overspeedconfig.getValue("UNKNOWN_OVERSPEED_BUS")
UNKNOWN_OVERSPEED = (UNKNOWN_OVERSPEED_DT,UNKNOWN_OVERSPEED_LD,UNKNOWN_OVERSPEED_FT,UNKNOWN_OVERSPEED_PM,UNKNOWN_OVERSPEED_BUS)

GLOBAL_MODEL_IDLE_COUNTER, GLOBAL_MODEL_IDLE_COUNTER_MAX = -1, 100
GLOBAL_STOP_FLAG = False

global_dataparsed = (int(time.time()),DEVICE_ID,UNIT_NO,"-9999","-8888","-8888","STA","UNKNOWN","UNKNOWN","0","0","0","0","-9999","GPS","0","0","NA",time.strftime('%Y%m%d'),time.strftime('%Y%m%d'),"0","0",int(time.time()))

def parseRedisData(data):
    
    if not data:
        return None
    
    try:
        heartbeat       = int(data.get("heartbeat", int(time.time())))
        deviceid       = data.get("deviceid", "NA")
        unitno         = data.get("unitno", "NA")
        speed           = str(data.get("VehicleSpeed", "-9999"))
        latitude        = data.get("gpslat", "-6666")
        longitude       = data.get("gpslong", "-6666")
        sta             = data.get("geosta", "UNKNOWN")
        segment         = data.get("geosegment", "UNKNOWN")
        road            = data.get("georoad", "UNKNOWN")
        max_speed       = data.get("geomaxspeed", "40")
        rpm             = str(data.get("RPM", "-6666"))
        gear            = str(data.get("CurrentGear", "-6666"))
        numsat          = data.get("gpsnumsat", "-6666")
        speedcanbus     = str(data.get("plm_speed_can", "-9999"))
        speedsource     = data.get("speedsource", "GPS")
        restricted      = data.get("restricted", "0")
        highrisk        = data.get("highrisk", "0")
        nrp             = data.get("nrp", "NA")
        start_shift     = data.get("start_shift", time.strftime('%Y%m%d'))
        end_shift       = data.get("end_shift", time.strftime('%Y%m%d'))
        is_authorized   = data.get("is_authorized", "0")
        location_hr     = data.get("location_hr", "0")
        gpsdatalogheartbeat   = int(data.get("heartbeat"))
        
        return (
            heartbeat, deviceid, unitno, speed, latitude, longitude, sta, segment, road, max_speed, rpm, gear, numsat, speedcanbus, speedsource, restricted, highrisk, nrp, start_shift, end_shift, is_authorized, location_hr, gpsdatalogheartbeat
        )

    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #REDIS: Parse data failed: {e}")
        return None

def redis_service(mode):
    global global_dataparsed, GLOBAL_STOP_FLAG
    global GLOBAL_MODEL_IDLE_COUNTER, GLOBAL_MODEL_IDLE_COUNTER_MAX 

    redis_manager = None
    
    try:
        redis_manager = RedisManager()
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #REDIS: Fail to connect Redis.")
        print(e)
        GLOBAL_STOP_FLAG = True        

    while True:
        if GLOBAL_STOP_FLAG:
            break        

        if GLOBAL_MODEL_IDLE_COUNTER > -1:
            GLOBAL_MODEL_IDLE_COUNTER = GLOBAL_MODEL_IDLE_COUNTER + 1
            if GLOBAL_MODEL_IDLE_COUNTER > GLOBAL_MODEL_IDLE_COUNTER_MAX:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #REDIS: Model inactive. Request to restart system....")
                GLOBAL_STOP_FLAG = True
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #REDIS: Inactive counter:", GLOBAL_MODEL_IDLE_COUNTER)

        # Get data from Redis
        redis_data = redis_manager.Get("ROW_DATA:data")
        parsed_data = parseRedisData(redis_data)
        
        # Check if data is stale (unchanged > 5 seconds)
        if redis_data and redis_manager.DetectUnchanges(5):
            # Reset to invalid state (equivalent to UDP "RESET")
            global_dataparsed = (int(time.time()), DEVICE_ID, UNIT_NO, "-6666", "-6666", "-6666", "STA", "UNKNOWN", "UNKNOWN", "0", "0", "0", "0", "-9999", "GPS", "0", "0", "NA", time.strftime('%Y%m%d'), time.strftime('%Y%m%d'), "0", "0", int(time.time()))
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [WARNING] #REDIS: Data unchanged > 5s. Data reset to invalid state.")
        elif parsed_data is not None:
            global_dataparsed = parsed_data
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #REDIS: New Redis data received. Using New Data:", global_dataparsed)
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [WARNING] #REDIS: No Redis data received. Using Last Data:", global_dataparsed)

        time.sleep(0.2)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #REDIS: Redis Service is Stopped.")

import threading
threading.Thread(target=redis_service, args=(1,)).start()

def resizeFrame(_frame, _w, _h):
    return cv2.resize(_frame,(_w,_h))

# Connect to Camera
cap = Camera(CAM_URL,2)

# Start visualizer
dataid = str(uuid.uuid4())
visualizer = VisualizerFront(config.path,5,MAX_PRE_FRAMES,MAX_POST_FRAMES,(DEVICE_ID,UNIT_NO),RECORDING_FPS)

if GLOBAL_MODEL_IDLE_COUNTER < 0:
    GLOBAL_MODEL_IDLE_COUNTER = 0

noframecounter = 0
noframecountermax = 600

while True:

    print("===========TIME:", time.strftime("%Y-%m-%d %H:%M:%S"),"===========")
    
    if GLOBAL_STOP_FLAG:
        break

    # Use global_dataparsed from Redis service
    dataid = str(uuid.uuid4())
    dataparsed = global_dataparsed

    # Grab new frame from Camera
    framestat, framecap = cap.read()
    if framestat and (framecap is not None):
        noframecounter = 0
        visualizer.recover()

        _curr_frame = framecap.popleft()
        try:
            FRAME_FRONT_SIZE = config.getValue("FRAME_FRONT_SIZE")
            if FRAME_FRONT_SIZE is not None:
                _cw, _ch = int(FRAME_FRONT_SIZE.split(",")[0]), int(FRAME_FRONT_SIZE.split(",")[1])
                _fh, _fw, _ = _curr_frame.shape
                # if _fh > _ch:
                #     _curr_frame = resizeFrame(_curr_frame, _cw, _ch)

            # If Camera is connected and frame is not empty send frame, dataid and dataparsed to Visualizer
            frame,_deviationtags,_resdataid,_dataparsed = None, None, None, None
            frame,_deviationtags,_resdataid,_dataparsed = visualizer.process(_curr_frame,dataid,dataparsed, (DEVICE_ID,UNIT_NO), UNKNOWN_OVERSPEED)
            # cv2.imshow('Front', frame)
            # if cv2.waitKey(1) == 27:
            #     break
        except:
            print("Something error executing visualizer. Parameters:",frame,_deviationtags,_resdataid,_dataparsed)
            print(traceback.format_exc())
            visualizer.reset()

    elif framestat == False:
        # If Camera is disconnected, reconnect the Camera and 
        print("Reconnecting (camera is disconnected)")
        cap.stop(1)
        cap = Camera(CAM_URL,2)
        # Ask Visualizer to reset all data and statistics
        # Remain temporary deviations will be saved and sent to Node-red
        print("*************** visualizer reset ******************")
        visualizer.reset()    
    else:
        print("noframecounter ",noframecounter)
        noframecounter = noframecounter + 1
        if noframecounter > noframecountermax:
            noframecounter = 0
            visualizer.sendStatus([],(-11,-11,-11,0,0,False,False))
            # print(framestat, framecap)
            print("Reconnecting (frame camera is empty): ",framestat, framecap)
            # cap.release()
            cap.stop(1)
            cap = Camera(CAM_URL,2)
            # Ask Visualizer to reset all data and statistics
            # Remain temporary deviations will be saved and sent to Node-red
            print("*************** visualizer reset 2 ******************")
            visualizer.reset()
        time.sleep(0.01)

# Stop all threads
GLOBAL_STOP_FLAG = True
cap.stop(1)
visualizer.stop()

cv2.destroyAllWindows()
exit(-1)
