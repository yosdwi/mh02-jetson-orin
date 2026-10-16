# Update History
# Version 6.2
# 2024-06-18    JRP     Happy 21st years in PAMA ;)
#                       (1) Split Fatigue Detection and Behavior Detection
#                           to improve system performance.
#                       (2) Implement 0 kmph detection and alert mode.


import collections
import os
import time
import copy
# import datetime
import traceback

import gc
# import tensorflow as tf
from classes.Config import *
# from detectors.PoseDetector import *
# from detectors.SeatBeltDetector import *
# from detectors.FaceLandmarkDetector import *
# from detectors.FaceMaskDetector import *
# from detectors.EyeGlassDetector import *
# from detectors.PupilDetector import *
# from detectors.HandposeDetector import *
# from detectors.SmokingDetector import *
# from detectors.PhoningDetector import *
from detectors.OverspeedDetector import *
from detectors.MineAwarenessDetector import *

class ProcessorFrontOverspeed:
    def __init__(self, path):

        # os.environ["TF_ENABLE_ONEDNN_OPTS"] = "1"
        # os.environ["OMP_NUM_THREADS"] = "4" # Limit to 200% (or 20% CPU)
        # tf.config.threading.set_inter_op_parallelism_threads(1) 
        # tf.config.threading.set_intra_op_parallelism_threads(1)

        # Facemask
        # physical_devices = tf.config.experimental.list_physical_devices('GPU')
        # print("TF DIRECTML", physical_devices)
        # for physical_device in physical_devices:
        #     tf.config.experimental.set_memory_growth(physical_device, True)
    
        # Initiate config reader
        self.config = Config(path)
        self.modelpath = str(self.config.getValue("MODEL_PATH"))

        self.lastconfigreload = time.time()
        self.maxconfigidletime = 3
        self.updateConfig(0)

        # Detectors
        # self.seatbeltdetector = SeatBelt(int(self.seatbeltparams[0]),int(self.seatbeltparams[1]),
        #                                  int(self.seatbeltparams[2]),int(self.seatbeltparams[3]),
        #                                  int(self.seatbeltparams[4]),int(self.seatbeltparams[5]))                                         
        # self.poselandmark = PoseDetector(mp,self.posefaceroi)
        # self.facelandmark = FaceLandmarkDetector(mp,copy.copy(self.facelmkparams))
        # # self.facemask = FaceMaskDetector(0.9,self.modelpath)
        # self.eyeglass = EyeGlassDetector()
        # self.pupils = PupilDetector()
        # self.hands = HandposeDetector(mp)
        # self.smoking = SmokingDetector(self.smokingparams) #(1.4,4,8)
        # self.phoning = PhoningDetector(self.phoningparams)

        self.overspeed = OverspeedDetector(self.overspeedparams, self.numsatparams)
        self.mineawareness = MineAwarenessDetector(self.mineawarenessparams, self.numsatparams)
        # Load Default MaxSpeed
        self.configmaxspeed = Config("..\\..\\files\\configs\\mh02_default_maxspeed.json")
        self.configdevice = Config("..\\..\\files\\configs\\smartd.json")

        # Initiate Device Info
        self.getDeviceInfo()

    def getDeviceInfo(self):
        try:
            self.unit_no = self.configdevice.getValue("UNIT_NO")
            self.defaultmaxspeed = self.configmaxspeed.getValue(self.unit_no[:2])
        except:
            self.unit_no = None
            self.defaultmaxspeed = 40

    def parseData(self,dataparsed):
        self.timestamp = float(dataparsed[0])
        self.deviceid = dataparsed[1]
        self.unitno = dataparsed[2]
        self.speed = dataparsed[3]
        self.lat = dataparsed[4]
        self.lon = dataparsed[5]
        self.sta = dataparsed[6]
        self.segment = dataparsed[7]
        self.road = dataparsed[8]
        self.maxroadspeed = dataparsed[9]
        self.rpm = dataparsed[10]
        self.gear = dataparsed[11]
        self.numsat = dataparsed[12]
        self.speedcanbus = dataparsed[13]
        self.speedsource = dataparsed[14]
        self.restricted = dataparsed[15]
        self.highrisk = dataparsed[16]
        self.nrp = dataparsed[17] 
        self.start_shift = dataparsed[18] 
        self.end_shift = dataparsed[19] 
        self.is_authorized = dataparsed[20] 
        self.location_hr = dataparsed[21] 
        self.gpsdataloghearbeat = dataparsed[22]

    def updateConfig(self, mode):
        reloadparams = False

        if mode == 0: # Initial
            self.config.load()
            reloadparams = True
        elif int(time.time() - self.lastconfigreload)>=int(self.maxconfigidletime):
            self.config.load()
            reloadparams = True
            self.lastconfigreload = time.time()

        if reloadparams:
            self.overspeedparams = self.config.getValue("OVERSPEED_CONFIG").split(",")
            self.numsatparams = int(self.config.getValue("MIN_NUMSAT_CONFIG"))
            self.mineawarenessparams = self.config.getValue("MINEAWARENESS_CONFIG").split(",")

            # self.cabinroi = str(self.config.getValue("CABIN_ROI")).split(",")
            # self.checkseatbelt = int(self.config.getValue("SEATBELT_ACTIVE"))
            # # self.checkfacemask = int(self.config.getValue("FACEMASK_ACTIVE"))
            # self.checkeyeglass = int(self.config.getValue("EYEGLASS_ACTIVE"))
            # self.seatbeltparams = str(self.config.getValue("SEATBELT_CONFIG")).split(",") 
            # self.facelmkparams = str(self.config.getValue("FACE_CONFIG"))
            # # self.facemaskparams = str(self.config.getValue("FACEMASK_CONFIG"))
            # self.smokingparams = str(self.config.getValue("SMOKING_CONFIG")).split(",")
            # self.phoningparams = str(self.config.getValue("PHONING_CONFIG")).split(",")

            # # roixmin, roiymin, 
            # # roixmax, roiymax
            # self.posefaceroi = (int(self.cabinroi[0]),int(self.cabinroi[1]),
            #                     int(self.cabinroi[2]),int(self.cabinroi[3]))
            
            if mode != 0:
                self.updateDetectors()
            
    def updateDetectors(self):
        # Update Detectors
        # self.poselandmark.update(self.posefaceroi)
        # self.facelandmark.update(self.facelmkparams)
        # # self.facemask.update(float(self.facemaskparams))
        # self.smoking.update(self.smokingparams)
        # self.phoning.update(self.phoningparams)

        self.overspeed.update(self.overspeedparams, self.numsatparams)
        self.mineawareness.update(self.mineawarenessparams, self.numsatparams)   

    def resetDetectors(self):
        # Avoid invalid values that affect to detector's draw function
        # This function will be visited in every cycle
        # self.seatbeltdetector.reset()
        # self.poselandmark.reset()
        # self.facelandmark.reset()
        # self.eyeglass.reset()
        # self.pupils.reset()
        # self.hands.reset()
        # self.smoking.reset()
        # self.phoning.reset()

        self.overspeed.reset()
        self.mineawareness.reset()

    # def cropPoseRoi(self, frame):
    #     if frame is None:
    #         return None

    #     h,w,c = frame.shape
    #     roixmin, roiymin, roixmax, roiymax = self.posefaceroi

    #     if roixmax > w:
    #         roixmax = w

    #     if roiymax > h:
    #         roiymax = h

    #     img = frame.copy()
    #     crop = img[roiymin:roiymax,roixmin:roixmax]
    #     return crop
    
    # def clear_gpu_memory(self):
    #     tf.keras.backend.clear_session()

    #     try:
    #         physical_devices = tf.config.experimental.list_physical_devices('GPU')
    #         for device in physical_devices:
    #             tf.config.experimental.set_memory_growth(device,False)
    #             tf.config.experimental.VirtualDeviceConfiguration(memory_limit=0)                
    #     except Exception as ex:
    #         print("=============================== Error cleaning GPU:", ex)

    #     gc.collect()

    def process(self,systemmode,frame,dataparsed,detection_mode, unknownoverspeed):
        # 0: Ignore All on All Speed, 10: Active all only is moving, 11: Active All on All Speed, 2: Fatigue Only when current speed is not Moving

        # self.clear_gpu_memory()
        # Update Necessary Parameters/ Configs
        self.updateConfig(1)
        self.resetDetectors()
        self.parseData(dataparsed)

        self.current_time = time.strftime('%H:%M:%S')

        # Overspeed Policy
        # UNKNOWN_OVERSPEED_DT,UNKNOWN_OVERSPEED_LD,UNKNOWN_OVERSPEED_FT,UNKNOWN_OVERSPEED_PM,UNKNOWN_OVERSPEED_BUS, UNKNOWN_OVERSPEED_WT, UNKNOWN_OVERSPEED_LO, UNKNOWN_OVERSPEED_CT, UNKNOWN_OVERSPEED_DN, UNKNOWN_OVERSPEED_HM, UNKNOWN_OVERSPEED_LV = unknownoverspeed
        # print(unknownoverspeed,UNKNOWN_OVERSPEED_DT,UNKNOWN_OVERSPEED_LD,UNKNOWN_OVERSPEED_FT,UNKNOWN_OVERSPEED_PM,UNKNOWN_OVERSPEED_BUS, UNKNOWN_OVERSPEED_WT, UNKNOWN_OVERSPEED_LO, UNKNOWN_OVERSPEED_CT, UNKNOWN_OVERSPEED_DN, UNKNOWN_OVERSPEED_HM, UNKNOWN_OVERSPEED_LV)

        # Local Variables
        warnings = []
        iswarningoverspeed = False

        deviations = []
        # earleft,earright,mar,pitch,yaw,masked,glasses,pupils = -9,-9,-9,0,0,False,False,False
        # facestat = (earleft,earright,mar,pitch,yaw,masked,glasses)
        # seatbeltstatus = False
        # # facemaskstatus = False
        # eyeglassstatus = False
        # handsdetected = False
        # issmoking, ismouthclosed, pointsinroi = False, False, 0
        # isphoning = False
        frontstat = ("None","None")
        isoverspeed = False
        isrestricted = False
        ishighrisk = False
        isrestricted_alert = False
        ishighrisk_alert = False
        isrestricted_unauthorized = False
        ishighrisk_unauthorized = False
        isroster_warning = False

        # Frame for Detections
        frame.flags.writeable = False
        h,w,c = frame.shape

        drawingframe = frame

        # mpframe = frame.copy()
        # mpframe.flags.writeable = False
        # mpframe = cv2.cvtColor(mpframe, cv2.COLOR_BGR2RGB)

        # mpframeposeroi = self.cropPoseRoi(frame)
        # mpframeposeroi.flags.writeable = False
        # mpframeposeroi = cv2.cvtColor(mpframeposeroi, cv2.COLOR_BGR2RGB)

        # Overspeed Detection

        unitlist = unknownoverspeed

        # print(unitlist)

        if self.unit_no is None:
            # If failed load config, Use value from node-red
            if len(self.unitno) > 2:
                unittype = self.unitno[:2]
            else:
                unittype = "NA"
        else:
            # Use value from config
            unittype = self.unit_no[:2]

        if unittype == "PM":
            if len(self.unitno) < 6:
                unittype = "BU"
            else:
                pass
        else:
            pass

        try:
            if "UNKNOWN" in self.segment:
                if unitlist.getValue("UNKNOWN_OVERSPEED_" + unittype)==1:
                    isoverspeed, iswarningoverspeed = self.overspeed.detect(frame,float(self.speed), float(self.maxroadspeed), int(self.numsat), str(self.restricted), str(self.highrisk))
                elif unitlist.getValue("UNKNOWN_OVERSPEED_" + unittype)==0:
                    isoverspeed = False
                    iswarningoverspeed = False
                    isrestricted = False
                    ishighrisk = False
                else:
                    # Use default maxspeed
                    isoverspeed, iswarningoverspeed, isrestricted, ishighrisk = self.overspeed.detect(frame,float(self.speed), float(self.defaultmaxspeed), int(self.numsat), str(self.restricted), str(self.highrisk))
            else:
                print(self.speed, self.maxroadspeed)
                print("6")
                isoverspeed, iswarningoverspeed = self.overspeed.detect(frame,float(self.speed), float(self.maxroadspeed), int(self.numsat), str(self.restricted), str(self.highrisk))
            print("OVERSPEED STATUS:",isoverspeed, iswarningoverspeed,isrestricted,float(self.speed), float(self.maxroadspeed),float(self.speed)/float(self.maxroadspeed), int(self.numsat), str(self.restricted), str(self.highrisk))
            
            # Mine Awareness Detection
            print("7")
            isrestricted_alert, ishighrisk_alert, isrestricted_unauthorized, ishighrisk_unauthorized, isroster_warning = self.mineawareness.detect(frame, str(self.restricted), str(self.highrisk), int(self.numsat), str(self.is_authorized), str(self.nrp), str(self.start_shift), str(self.end_shift))
            print("MINE AWARENESS STATUS:", isrestricted_alert, ishighrisk_alert, isrestricted_unauthorized, ishighrisk_unauthorized, isroster_warning)
        except Exception as e:
            print("Detection Failed", e)

        if (int(detection_mode) == 0): 
            deviations = []
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [INFO] Deviations Ignored:", deviations, "systemmode:",systemmode, "detection_mode:", detection_mode )
        else:
            pass
        
        if isoverspeed:
            # Patch
            try:
                if float(self.lat)!=0 or float(self.lon) != 0:
                    if float(self.maxroadspeed) <= 0:
                        isoverspeed = False
                    else:
                        deviations.append("OVERSPEED")
            except:
                if float(self.maxroadspeed) <= 0:
                    isoverspeed = False
                else:
                    deviations.append("OVERSPEED")    
        elif iswarningoverspeed:
            warnings.append("OVERSPEEDWARNING")
        else:
            pass

        # Mine Awareness Alerts - Restricted area is always high risk
        if isrestricted_alert or isrestricted_unauthorized:
            # Patch
            try:
                if float(self.lat)!=0 or float(self.lon) != 0:
                    deviations.append("RESTRICTED")
            except:
                pass
            
            deviations.append("RESTRICTED")
        elif ishighrisk_alert or ishighrisk_unauthorized:
            # Patch
            try:
                if float(self.lat)!=0 or float(self.lon) != 0:
                    deviations.append("HIGHRISK")
            except:
                pass

        # Mine Awareness Roster Warnings 
        if isroster_warning:
            warnings.append("AUTHORIZEDWARNING")

        return drawingframe, deviations, warnings, frontstat
