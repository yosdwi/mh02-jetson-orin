# Update History
# Version 6.1
# 2024-04-16    JRP     Add Overspeed policy.
#                       Add improvements to avoid/reduce possibility of run time errors

import collections
import os
import time
import copy

from classes.Config import *
# from detectors.OverspeedDetector import *
from detectors.CollisionDetector import *

class ProcessorFront:
    def __init__(self, path):

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
        # self.overspeed = OverspeedDetector(self.overspeedparams)
        self.collision = CollisionDetector(path)

    def parseData(self,dataparsed):
        print("FRONT DATA:", dataparsed)
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
            self.collisionparams = self.config.getValue("COLLISION_CONFIG").split(",")
            # self.overspeedparams = self.config.getValue("OVERSPEED_CONFIG").split(",")
            if mode != 0:
                self.updateDetectors()
            
    def updateDetectors(self):
        # Update Detectors
        self.collision.update(self.collisionparams)  
        # self.overspeed.update(self.overspeedparams)      

    def resetDetectors(self):
        # Aoid invalid values that affect to detector's draw function
        # This function will be visited in every cycle
        # self.overspeed.reset()
        pass

    def process(self,systemmode,frame,dataparsed,unknownoverspeed):
        # Update Necessary Parameters/ Configs
        self.updateConfig(1)
        self.resetDetectors()
        self.parseData(dataparsed)

        # Overspeed Policy
        # UNKNOWN_OVERSPEED_DT,UNKNOWN_OVERSPEED_LD,UNKNOWN_OVERSPEED_FT,UNKNOWN_OVERSPEED_PM,UNKNOWN_OVERSPEED_BUS = unknownoverspeed
        # print(unknownoverspeed,UNKNOWN_OVERSPEED_DT,UNKNOWN_OVERSPEED_LD,UNKNOWN_OVERSPEED_FT,UNKNOWN_OVERSPEED_PM,UNKNOWN_OVERSPEED_BUS)
        # Local Variables
        warnings = []
        deviations = []
        frontstat = ("None","None")
        # isoverspeed = False
        # iswarningoverspeed = False
        is_collision_object, is_collision_pedestrian = False, False        

        # Check System Mode
        if int(systemmode)==3: # 1: Operational, 2: Testing/ Simulation, 3: Inactive Detection
            return frame, deviations, frontstat

        # Detections
        drawingframe = frame.copy()
        frame.flags.writeable = False
        h,w,c = frame.shape

        is_collision_object,  is_collision_pedestrian = self.collision.detect(frame,float(self.speed))
        if is_collision_object:
            deviations.append("COLLISION")
            drawingframe = self.collision.draw(drawingframe)
        if is_collision_pedestrian:
            deviations.append("PEDESTRIAN")
            drawingframe = self.collision.draw(drawingframe)

        frame.flags.writeable = True
        # return frame, deviations, warnings, frontstat
        return drawingframe, deviations, warnings, frontstat