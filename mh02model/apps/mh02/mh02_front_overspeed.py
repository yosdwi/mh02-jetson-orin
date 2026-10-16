# Update History
# Version 6.2
# 2024-06-18    JRP     Happy 21st years in PAMA ;)
#                       (1) Split Fatigue Detection and Behavior Detection
#                           to improve system performance.
#                       (2) Implement 0 kmph detection and alert mode.

import uuid
import os
import time
import traceback
import collections
import gc
# import tensorflow as tf
from classes.Config import *
from classes.RedisManager import *
# from classes.MMFServer import *
from classes.Camera import *
from classes.VisualizerFrontOverspeed import *
# from classes.ColorAdjuster import *
# from classes.VisualizerCabinBehavior import *
import numpy as np

import json


# Initiate config reader
try:
    os.system("wmic bios get serialnumber > D:\\smartd\\script\\sn\\sn.txt")
except:
    pass

deviceconfig = Config("D:\\smartd\\script\\mh02model\\files\\configs\\smartd.json")
config = Config("D:\\smartd\\script\\mh02model\\files\\configs\\mh02_front.json")

# configmaxspeed = Config("D:\\smartd\\script\\mh02model\\files\\configs\\mh02_default_maxspeed.json")

# try:
#     unit_no = deviceconfig.getValue("UNIT_NO")
#     defaultmaxspeed = configmaxspeed.getValue(unit_no[:2])
# except:
#     unit_no = None
#     defaultmaxspeed = 40


GLOBAL_MODEL_IDLE_COUNTER, GLOBAL_MODEL_IDLE_COUNTER_MAX = -1, 100
GLOBAL_STOP_FLAG = False

global_visualizer = None

# <************************* UDP *************************
DEVICE_ID = deviceconfig.getValue("DEVICE_ID")
UNIT_NO = deviceconfig.getValue("UNIT_NO")

UDP_LOCAL_PORT = config.getValue("UDP_LOCAL_PORT_OVERSPEED")
UDP_BUFFER_SIZE = config.getValue("UDP_BUFFER_SIZE")

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
        
        if redis_data and redis_manager.DetectUnchanges(5):
            global_dataparsed = (int(time.time()), DEVICE_ID, UNIT_NO, "-6666", "-6666", "-6666", "STA", "UNKNOWN", "UNKNOWN", "0", "0", "0", "0", "-9999", "GPS", "0", "0", "NA", time.strftime('%Y%m%d'), time.strftime('%Y%m%d'), "0", "0", int(time.time()))
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [WARNING] #REDIS: Data unchanged > 5s. Data reset to invalid state.")
        elif parsed_data is not None:
            global_dataparsed = parsed_data
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #REDIS: New Redis data received. Using New Data:", global_dataparsed)
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [WARNING] #REDIS: No Redis data received. Using Last Data:", global_dataparsed)

        time.sleep(0.2)

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #REDIS: Redis Service is Stopped.")

threading.Thread(target=redis_service, args=(1,)).start()
# ************************* REDIS *************************>

# <************************* CAMERA *************************

def resizeFrame(_frame, _w, _h):
    return cv2.resize(_frame,(_w,_h))

CAM_URL = config.getValue("CAM_URL")
global_camera_frame = collections.deque(maxlen=1)

FRAME_FRONT_SIZE_OVERSPEED = config.getValue("FRAME_FRONT_SIZE_OVERSPEED")
SYSTEM_CAMERA_MODE = config.getValue("SYSTEM_CAMERA_MODE")
if SYSTEM_CAMERA_MODE is None:
    SYSTEM_CAMERA_MODE = 1 

if FRAME_FRONT_SIZE_OVERSPEED is not None:
    _cw, _ch = int(FRAME_FRONT_SIZE_OVERSPEED.split(",")[0]), int(FRAME_FRONT_SIZE_OVERSPEED.split(",")[1])
    dummy_frame = np.zeros((_ch, _cw, 3), dtype=np.uint8)
else:
    dummy_frame = np.zeros((16, 16, 3), dtype=np.uint8)

def cabin_camera(countermax):
    global config
    global GLOBAL_STOP_FLAG
    global global_camera_frame, CAM_URL

    if SYSTEM_CAMERA_MODE == 0:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #CAM: Camera bypass mode enabled. Using dummy frames.")

        while True:
            if GLOBAL_STOP_FLAG:
                break

            if len(global_camera_frame) == 0:
                global_camera_frame.append(dummy_frame)

            if global_visualizer is not None and len(global_visualizer.camstream) == 0:
                global_visualizer.camstream.append(dummy_frame)
            
            time.sleep(1/30)  
            # time.sleep(1/100)
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] Camera bypass mode stopped.")
        return
        
    _cap = Camera(CAM_URL,2)
    _noframecounter = 0
    _noframecountermax = countermax

    _needtoreconnect = False
    _framecapisempty = True

    # Camera & Color Adjuster
    _config_reload_counter, _config_reload_counter_max = 100,100
    # _colorAdjuster = ColorAdjuster()

    while True:
        if GLOBAL_STOP_FLAG:
            break        

        # Check for config reload counter
        _config_reload_counter = _config_reload_counter + 1
        if _config_reload_counter >= _config_reload_counter_max:
            _config_reload_counter = 0
            config.load()
            # _frame_gamma = float(config.getValue("FRAME_CABIN_GAMMA"))
            # _frame_color_adjuster_active = int(config.getValue("FRAME_CABIN_COLOR_ADJUSTER"))

        _framestat, _framecap = _cap.read()

        if _framestat:
            # Camera is connected

            if (_framecap is None):
                _framecapisempty = True
            else:
                if len(_framecap) < 1:
                    _framecapisempty = True
                else:
                    _framecapisempty = False

            if _framecapisempty:  
                # Camera is connected but Frame is empty
                _noframecounter = _noframecounter + 1
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [WARNING] #CAM: Frame camera is empty. Waiting for new frame...",_noframecounter,_noframecountermax)
                if (_noframecounter >= _noframecountermax):
                    _noframecounter = 0
                    _needtoreconnect = True
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR]  #CAM: Request to connect camera.")
            else: 
                # Camera is connected and Frame is OK 
                _curr_frame = _framecap.popleft().copy()

                # Resize Camera
                if FRAME_FRONT_SIZE_OVERSPEED is not None:
                    # _cw, _ch = int(FRAME_FRONT_SIZE.split(",")[0]), int(FRAME_FRONT_SIZE.split(",")[1])
                    # _fh, _fw, _ = _curr_frame.shape
                    # if _fh > _ch:
                    #     _curr_frame = resizeFrame(_curr_frame, _cw, _ch, _fh, _fw)
                    
                    # if FRAME_FRONT_SIZE is not None:
                    _cw, _ch = int(FRAME_FRONT_SIZE_OVERSPEED.split(",")[0]), int(FRAME_FRONT_SIZE_OVERSPEED.split(",")[1])
                    _fh, _fw, _ = _curr_frame.shape
                    if _fh > _ch:
                        _curr_frame = resizeFrame(_curr_frame, _cw, _ch)

                # Apply color adjuster
                # if _frame_color_adjuster_active:
                #     _fatigue_frame_LAB = _colorAdjuster.adjust_LAB(_curr_frame.copy())
                #     _fatigue_frame_LAB_gamma = _colorAdjuster.adjust_Gamma(_fatigue_frame_LAB.copy(),_frame_gamma)
                #     _curr_frame = _fatigue_frame_LAB_gamma

                # Refill global camera variable
                global_camera_frame.append(_curr_frame)
                # Refill global visualizer frame
                
                if global_visualizer is not None:
                    global_visualizer.camstream.append(_curr_frame)

                _noframecounter = 0
                _needtoreconnect = False
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO]  #CAM: Frame camera is OK.",_noframecounter,_noframecountermax)        
        else:
            # Camera is disconected
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #CAM: Request to connect camera.")
            _needtoreconnect = True

        if _needtoreconnect:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #CAM: Camera is disconnected. Reconnecting camera...")
            _noframecounter = 0
            _needtoreconnect = False
            _cap.stop(1)

            time.sleep(5)

            _cap = Camera(CAM_URL,2)
        
        time.sleep(1/100)
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] Front Overspeed Camera is Stopped.") 

threading.Thread(target=cabin_camera, args=(600,)).start()
# ************************* CAMERA *************************>


# <************************* CABIN FATIGUE DETECTION *************************

MAX_PRE_FRAMES_FATIGUE = config.getValue("MAX_PRE_FRAMES_OVERSPEED")
MAX_POST_FRAMES_FATIGUE = config.getValue("MAX_POST_FRAMES_OVERSPEED")
RECORDING_FPS_FATIGUE = config.getValue("RECORDING_FPS_OVERSPEED")


overspeedconfig = Config("D:\\smartd\\script\\mh02model\\files\\configs\\mh02_front_overspeed.json")
# UNKNOWN_OVERSPEED_DT = overspeedconfig.getValue("UNKNOWN_OVERSPEED_DT")
# UNKNOWN_OVERSPEED_LD = overspeedconfig.getValue("UNKNOWN_OVERSPEED_LD")
# UNKNOWN_OVERSPEED_FT = overspeedconfig.getValue("UNKNOWN_OVERSPEED_FT")
# UNKNOWN_OVERSPEED_PM = overspeedconfig.getValue("UNKNOWN_OVERSPEED_PM")
# UNKNOWN_OVERSPEED_BUS = overspeedconfig.getValue("UNKNOWN_OVERSPEED_BUS")
# UNKNOWN_OVERSPEED_WT = overspeedconfig.getValue("UNKNOWN_OVERSPEED_WT")
# UNKNOWN_OVERSPEED_LO = overspeedconfig.getValue("UNKNOWN_OVERSPEED_LO")
# UNKNOWN_OVERSPEED_CT = overspeedconfig.getValue("UNKNOWN_OVERSPEED_CT")
# UNKNOWN_OVERSPEED_DN = overspeedconfig.getValue("UNKNOWN_OVERSPEED_DN")
# UNKNOWN_OVERSPEED_HM = overspeedconfig.getValue("UNKNOWN_OVERSPEED_HM")
# UNKNOWN_OVERSPEED_LV = overspeedconfig.getValue("UNKNOWN_OVERSPEED_LV")
# UNKNOWN_OVERSPEED = (UNKNOWN_OVERSPEED_DT,UNKNOWN_OVERSPEED_LD,UNKNOWN_OVERSPEED_FT,UNKNOWN_OVERSPEED_PM,UNKNOWN_OVERSPEED_BUS,UNKNOWN_OVERSPEED_WT,UNKNOWN_OVERSPEED_LO,UNKNOWN_OVERSPEED_CT,UNKNOWN_OVERSPEED_DN,UNKNOWN_OVERSPEED_HM,UNKNOWN_OVERSPEED_LV)\

UNKNOWN_OVERSPEED = overspeedconfig


def front_overspeed(mode):
    global config, GLOBAL_STOP_FLAG, global_camera_frame, MAX_PRE_FRAMES_FATIGUE, MAX_POST_FRAMES_FATIGUE, DEVICE_ID, UNIT_NO, RECORDING_FPS_FATIGUE, FRAME_FRONT_SIZE
    global global_dataparsed, global_visualizer
    global GLOBAL_MODEL_IDLE_COUNTER
    
    _fatiguenoframecounter = 0
    _fatiguenoframecountermax = 600

    global_visualizer = VisualizerFrontOverspeed(config.path,5,MAX_PRE_FRAMES_FATIGUE,MAX_POST_FRAMES_FATIGUE,(DEVICE_ID,UNIT_NO),RECORDING_FPS_FATIGUE)

    if GLOBAL_MODEL_IDLE_COUNTER < 0:
        GLOBAL_MODEL_IDLE_COUNTER = 0

    while True:
        if GLOBAL_STOP_FLAG:
            break

        _dataid = str(uuid.uuid4())

        if len(global_camera_frame) > 0:
            # Global frame is refilled.
            _fatiguenoframecounter = 0
            _fatigue_frame = global_camera_frame.popleft().copy()

            try: 

                processedframe,_deviationtags,_dataid,_dataiddataparsed = global_visualizer.process(_fatigue_frame,_dataid,global_dataparsed, (DEVICE_ID,UNIT_NO), UNKNOWN_OVERSPEED)    
                
                GLOBAL_MODEL_IDLE_COUNTER = 0

                # cv2.imshow('Cabin Fatigue', processedframe)
                # # if cv2.waitKey(1) == 27:
                # #     GLOBAL_STOP_FLAG = True
            except Exception as ex:
                global_visualizer.sendStatus([],(-11,-11,-11,0,0,False,False))
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #Fatigue: Processing cabin (fatigue) frame is error. Reason", ex)
                print(traceback.format_exc())
                global_visualizer.recover()
        else: 
            # Global frame is empty.                       
            _fatiguenoframecounter = _fatiguenoframecounter + 1
            if _fatiguenoframecounter >= _fatiguenoframecountermax:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #Fatigue: Waiting time for frame excedeed.", _fatiguenoframecounter, _fatiguenoframecountermax)
                _fatiguenoframecounter = 0
                global_visualizer.sendStatus([],(-11,-11,-11,0,0,False,False))
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #Fatigue: Waiting time for frame reset.", _fatiguenoframecounter, _fatiguenoframecountermax)


        if checkRestartFlag():
            GLOBAL_STOP_FLAG = True
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #Fatigue: Restart flag found. Stopping system.")            

        time.sleep(0.01)
    
    global_visualizer.stop()
    cv2.destroyAllWindows()
    time.sleep(5)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #Fatigue: Fatigue System is Stopped.")  
    return True



# ************************* CABIN FATIGUE DETECTION *************************>

def checkRestartFlag():
    try:  
        if os.path.exists("D:\\smartd\\script\\mh02model\\files\\configs\\restart_overspeed.pid"):
            os.remove("D:\\smartd\\script\\mh02model\\files\\configs\\restart_overspeed.pid")
            return True
        else:
            return False
    except:
        return False


if front_overspeed(0):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] All system is Stopped.") 
    os._exit(0)
    

