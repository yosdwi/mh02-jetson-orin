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
import tensorflow as tf
from classes.Config import *
from classes.RedisManager import *
from classes.CameraCV2 import *
from classes.VisualizerCabinFatigue import *
from classes.ColorAdjuster import *
import json

# Initiate config reader
try:
    os.system("wmic bios get serialnumber > D:\\smartd\\script\\sn\\sn.txt")
except:
    pass

print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] Setting GPU.")
_gpus = tf.config.experimental.list_physical_devices('GPU')
if _gpus:
    try:
        tf.config.experimental.set_virtual_device_configuration(
            _gpus[0],
            [tf.config.experimental.VirtualDeviceConfiguration(memory_limit=1024)])        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] Setting GPU success.")
    except RuntimeError as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] Setting GPU failed.")
        print(e)

deviceconfig = Config("D:\\smartd\\script\\mh02model\\files\\configs\\smartd.json")
config = Config("D:\\smartd\\script\\mh02model\\files\\configs\\mh02_cabin_old.json")

GLOBAL_MODEL_IDLE_COUNTER, GLOBAL_MODEL_IDLE_COUNTER_MAX = -1, 100
GLOBAL_STOP_FLAG = False

global_visualizer = None

# <************************* UDP *************************
DEVICE_ID = deviceconfig.getValue("DEVICE_ID")
UNIT_NO = deviceconfig.getValue("UNIT_NO")

UDP_LOCAL_PORT = config.getValue("UDP_LOCAL_PORT")
UDP_BUFFER_SIZE = config.getValue("UDP_BUFFER_SIZE")

global_dataparsed = (int(time.time()),DEVICE_ID,UNIT_NO,"-9999","-8888","-8888","STA","UNKNOWN","UNKNOWN","0","0","0","0",None,None,None,None,None,None,False,False)

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
        gpsdatalogheartbeat   = int(data.get("heartbeat"))
        
        return (
            heartbeat, deviceid, unitno, speed, latitude, longitude, sta, segment, road, max_speed, rpm, gear, numsat, gpsdatalogheartbeat, ""
        
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
            global_dataparsed = (int(time.time()), DEVICE_ID, UNIT_NO, "-6666", "-6666", "-6666", "STA", "UNKNOWN", "UNKNOWN", "0", "0", "0", "0", None, None, None, None, None, None, False, False)
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

# def udp_service(mode):
#     global global_dataparsed, UDP_LOCAL_PORT, UDP_BUFFER_SIZE, GLOBAL_STOP_FLAG
#     global GLOBAL_MODEL_IDLE_COUNTER, GLOBAL_MODEL_IDLE_COUNTER_MAX 

#     # Start UDP server to receive realtime data from Node-Red
#     _udp = None
#     _udpstat = False
#     _udpparsed = None

#     try:
#         _udp = UDPServer("127.0.0.1",UDP_LOCAL_PORT,UDP_BUFFER_SIZE)
#         # _udp = MMFServer()    
#     except Exception as e:
#         print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #UDP: Fail to run UDP Server.")
#         print(traceback.format_exc())
#         GLOBAL_STOP_FLAG = True        

#     while True:

#         if GLOBAL_STOP_FLAG :
#             break        

#         if GLOBAL_MODEL_IDLE_COUNTER > -1:
#             GLOBAL_MODEL_IDLE_COUNTER = GLOBAL_MODEL_IDLE_COUNTER + 1
#             if GLOBAL_MODEL_IDLE_COUNTER > GLOBAL_MODEL_IDLE_COUNTER_MAX:
#                 print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] #UDP: Model inactive. Request to restart system....")
#                 GLOBAL_STOP_FLAG = True
#             print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #UDP: Inactive counter:",GLOBAL_MODEL_IDLE_COUNTER)

#         _udpstat, _udpmessage = _udp.getMessage()
#         _udpparsed = parseUDP(_udpmessage)
#         if _udpparsed == "RESET":
#             # MMF writer is dead, reset to invalid state
#             global_dataparsed = (int(time.time()),DEVICE_ID,UNIT_NO,"-6666","-6666","-6666","STA","UNKNOWN","UNKNOWN","0","0","0","0",None,None,None,None,None,None,False,False)
#             print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [WARNING] #UDP: MMF writer is dead. Data reset to invalid state.")
#         if _udpparsed is not None:
#             global_dataparsed = _udpparsed
#             print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #UDP: New UDP data is received. Using New Data:", global_dataparsed)
#         else:
#             # dataparsed = (int(time.time()),DEVICE_ID,UNIT_NO,"-9999","-8888","-8888","STA","UNKNOWN","UNKNOWN","0","0","0",None,None,None,None,None,None,False,False)
#             print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [WARNING] #UDP: No UDP data is received. Using Last Data:", global_dataparsed)

#         time.sleep(0.2)
    
#     _udp.stop(1)

#     print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #UDP: UDP Service is Stopped.") 

# threading.Thread(target=udp_service, args=(1,)).start()
# ************************* UDP *************************>

# <************************* CAMERA *************************
def resizeFrame(_frame, _w, _h, _fh, _fw):
    if _fw >= _w:
        _xmin = int((_fw - _w)/2)
    else:
        _xmin = 0
    
    _xmax = _xmin + _w

    if _fh >= _h:
        _ymin = int((_fh - _h)/2)
    else:
        _ymin = 0

    _ymax = _ymin + _h

    _frame = _frame[_ymin:_ymax, _xmin:_xmax]

    # return cv2.resize(_frame,(_w,_h))
    return _frame

CAM_URL = config.getValue("CAM_URL")
global_camera_frame = collections.deque(maxlen=1)

FRAME_CABIN_SIZE = config.getValue("FRAME_CABIN_SIZE")

def cabin_camera(countermax):
    global config
    global GLOBAL_STOP_FLAG
    global global_camera_frame, CAM_URL
        
    _cap = CameraCV2(CAM_URL,2)
    _noframecounter = 0
    _noframecountermax = countermax

    _needtoreconnect = False
    _framecapisempty = True

    # Camera & Color Adjuster
    _config_reload_counter, _config_reload_counter_max = 100,100
    _colorAdjuster = ColorAdjuster()

    while True:
        if GLOBAL_STOP_FLAG:
            break        

        # Check for config reload counter
        _config_reload_counter = _config_reload_counter + 1
        if _config_reload_counter >= _config_reload_counter_max:
            _config_reload_counter = 0
            config.load()
            _frame_gamma = float(config.getValue("FRAME_CABIN_GAMMA"))
            _frame_color_adjuster_active = int(config.getValue("FRAME_CABIN_COLOR_ADJUSTER"))

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
                if FRAME_CABIN_SIZE is not None:
                    _cw, _ch = int(FRAME_CABIN_SIZE.split(",")[0]), int(FRAME_CABIN_SIZE.split(",")[1])
                    _fh, _fw, _ = _curr_frame.shape
                    if _fh > _ch:
                        _curr_frame = resizeFrame(_curr_frame, _cw, _ch, _fh, _fw)

                # Apply color adjuster
                if _frame_color_adjuster_active:
                    _fatigue_frame_LAB = _colorAdjuster.adjust_LAB(_curr_frame.copy())
                    _fatigue_frame_LAB_gamma = _colorAdjuster.adjust_Gamma(_fatigue_frame_LAB.copy(),_frame_gamma)
                    _curr_frame = _fatigue_frame_LAB_gamma

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

            _cap = CameraCV2(CAM_URL,2)
        
        time.sleep(1/100)
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] Fatigue Camera is Stopped.") 

threading.Thread(target=cabin_camera, args=(600,)).start()
# ************************* CAMERA *************************>


# <************************* CABIN FATIGUE DETECTION *************************

MAX_PRE_FRAMES_FATIGUE = config.getValue("MAX_PRE_FRAMES_FATIGUE")
MAX_POST_FRAMES_FATIGUE = config.getValue("MAX_POST_FRAMES_FATIGUE")
RECORDING_FPS_FATIGUE = config.getValue("RECORDING_FPS_FATIGUE")

def cabin_fatigue(mode):
    global config, GLOBAL_STOP_FLAG, global_camera_frame, MAX_PRE_FRAMES_FATIGUE, MAX_POST_FRAMES_FATIGUE, DEVICE_ID, UNIT_NO, RECORDING_FPS_FATIGUE, FRAME_CABIN_SIZE
    global global_dataparsed, global_visualizer
    global GLOBAL_MODEL_IDLE_COUNTER
    
    _fatiguenoframecounter = 0
    _fatiguenoframecountermax = 600

    global_visualizer = VisualizerCabinFatigue(config.path,5,MAX_PRE_FRAMES_FATIGUE,MAX_POST_FRAMES_FATIGUE,(DEVICE_ID,UNIT_NO),RECORDING_FPS_FATIGUE)

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
                processedframe,_deviationtags,_dataid,_dataiddataparsed = global_visualizer.process(_fatigue_frame,_dataid,global_dataparsed, (DEVICE_ID,UNIT_NO))    
                
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

        _cntGbg, _, _ = gc.get_count()
        if _cntGbg >= 1000:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] #Fatigue: GC is cleaning...")
            gc.collect()

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
        if os.path.exists("D:\\smartd\\script\\mh02model\\files\\configs\\restart_fatigue.pid"):
            os.remove("D:\\smartd\\script\\mh02model\\files\\configs\\restart_fatigue.pid")
            return True
        else:
            return False
    except:
        return False


if cabin_fatigue(0):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] All system is Stopped.") 
    os._exit(0)
    



