# Update History
# Version 6.1
# 2024-04-16    JRP     Add Overspeed policy.
#                       Add improvements to avoid/reduce possibility of run time errors

import cv2
import collections
import time
# import datetime
import threading
import os
import copy
# import winsound  # Windows-only, commented for Linux compatibility
import socket

from classes.Config import *
from classes.ProcessorFront import *
from classes.AlertPlayerFront import *
from classes.AlertLogger import *
from classes.DeviationCounter import *
from classes.FrontDeviationRecord import *
from classes.FrontDeviationRecorder import *
# from classes.WarningCounter import *

class VisualizerFront:

    def __init__(self,path,maxiddle,maxpreframes,maxpostframes,deviceinfo,recording_fps):
        # Camera stream frame
        self.thumbnailframe = None
        # Initiate config reader
        self.path = path
        self.config = Config(path)
        self.camside = str(self.config.getValue("CAMSIDE"))
        self.systemmode = int(self.config.getValue("SYSTEM_MODE_FRONT"))
        self.systemmodealert = int(self.config.getValue("ALERT_MODE_FRONT"))
        self.deviceinfo = deviceinfo
        self.recording_fps = recording_fps

        # UDP Client
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpserverip = str(self.config.getValue("UDP_SERVER_IP"))
        self.udpserverport = int(self.config.getValue("UDP_STATUS_SERVER_PORT"))

        # Initiate frame processor
        self.processor = ProcessorFront(path)

        # Initiate Flags
        self.stopflag = collections.deque(maxlen=1)
        self.resetflag = collections.deque(maxlen=1)
        self.deviationflags = ""

        # Initiate Key Variables
        if maxpreframes is None:
            maxpreframes = 75
        if maxpostframes is None:
            maxpostframes = 75
        
        self.maxpreframes = int(maxpreframes)
        self.maxpostframes = int(maxpostframes)

        self.maxiddle = maxiddle
        self.lastconfigcheck = time.time()
        self.maxconfigiddle = 5
        self.lastdataid = 'NONE'
        self.lastdatareceived = time.time()
        
        # Initiate Functional Variables
        self.initVars()
        self.alertplayer = AlertPlayerFront(self.path) 
        self.alertlogger = AlertLogger()  # Only handles logging

        # Initiate Counters
        self.initCounters()

    def playAlert(self, sound_text, alert_type="UNKNOWN"):
       
        if self.systemmode == 1:
            self.alertplayer.add(sound_text, alert_type)
        
        tags = [alert_type] if alert_type != "UNKNOWN" else ["UNKNOWN"]
        
        self.alertlogger.log_alert(
            sound_text=sound_text,
            device_id=self.deviceid,
            unit_no=self.unitno,
            alert_tags=tags,
            speed=self.speed,
            segment=self.segment,
            road=self.road,
            lat=self.lat,
            lon=self.lon,
            maxroadspeed=self.maxroadspeed,
            numsat=self.numsat,
            speedcanbus=self.speedcanbus,
            speedsource=self.speedsource,
            restricted=self.restricted,
            highrisk=self.highrisk,
            nrp=self.nrp,
            start_shift=self.start_shift,
            end_shift=self.end_shift,
            is_authorized=self.is_authorized,
            location_hr=self.location_hr,
            gpsdataloghearbeat=self.gpsdataloghearbeat
        )
    
    def checkConfig(self):
        if int((time.time() - self.lastconfigcheck)) >= self.maxconfigiddle:
            self.config.load()
            self.lastconfigcheck = time.time()
            # Update Visualizer Parameters
            self.systemmode = int(self.config.getValue("SYSTEM_MODE_FRONT"))

            #Update Counter Parameters
            for cnt in self.counters:
                cnt.updateParams()

            #Update Alert Player
            self.alertplayer.update()
        
    def initVars(self):
        self.timestamp = int(time.time()) #No timestamp from server so use system time
        self.deviceid, self.unitno = self.deviceinfo
        self.speed = None
        self.lat = None
        self.lon = None
        self.sta = None
        self.segment = None
        self.road = None
        self.maxroadspeed = None
        self.rpm = None
        self.gear = None
        self.numsat = None
        self.speedcanbus = 0
        self.speedsource = ""
        self.restricted = ""
        self.highrisk = ""
        self.nrp = ""
        self.start_shift = ""
        self.end_shift = ""
        self.is_authorized = ""
        self.location_hr = ""
        self.gpsdataloghearbeat = ""

        self.minimumspeed = self.config.getValue("MINIMUM_SPEED_FRONT")

    def isDataValid(self,dataparsed):
        # Expected data is array of:
        # deviceid|unitno|speed|lat|lon|sta|segment|road|maxroadspeed|
        # Expected minimum array size: 9
        # if dataparsed is None, return as unvalid data
        if dataparsed is None:
            return False
        # If data length (array) less than expected, return as unvalid data
        if len(dataparsed)<23:
            return False

        # Otherwise return as a valid data
        return True
    
    def generateDefaultData(self):
        _deviceid, _unitno = self.deviceid, self.unitno
        dataparsed = (int(time.time()),_deviceid,_unitno,"-9999","-8888","-8888","STA","UNKNOWN","UNKNOWN","0","0","0","0","0","0","0",None,None,None,None,None,None,False,False)
        return dataparsed    
    
    def parseData(self,dataid,dataparsed):
        # Update lastdatareceived
        self.lastdatareceived = time.time()

        self.lastdataid = dataid
        self.timestamp = float(dataparsed[0])
        self.deviceid, self.unitno = self.deviceinfo

        if dataparsed[3] is not None:
            if len(dataparsed[3])>0:
                try:
                    self.speed = int(dataparsed[3])
                except:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}], [ERROR] GPS Speed is Invalid: ", dataparsed[3])
                    self.speed = 0                            
            else:
                print("***WARNING*** Speed is Empty.")
                self.speed = 0
            try:
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
                 
            except:
                print("***WARNING*** GPS Data is invalid, use last data if available.")
        else:
            print("***WARNING*** GPS Stuck. Use last data if available.")   
            print(dataparsed)            

    def checkData(self,dataid,dataparsed,deviceinfo):
        if self.isDataValid(dataparsed):
            # If data valid, refresh lastdatareceived, parse data and update all variables
            self.parseData(dataid,dataparsed)
            print("DataID:",dataid, "- New Data")
            return dataparsed
        else:
            # Generate Default data
            print("Dataparsed:",dataparsed,"Not Valid")
            return self.generateDefaultData()
    
    def reset(self):
        self.resetflag.append(1)

    def recover(self):
        if len(self.resetflag)>0:
            self.resetflag.popleft()

    def stop(self):
        self.stopflag.append(1)
        self.alertplayer.stop(self.systemmodealert)
        self.alertlogger.stop()
        self.deviationrecorder.stop(1)

    def drawLabels(self,frame,frontstat):
        dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.timestamp))
        h,w,c = frame.shape
        frame = cv2.rectangle(frame, (0,0), (w,30), (41, 41, 41),-1)
        frame = cv2.putText(frame, dt, (10, 18), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        frame = cv2.putText(frame, str(self.deviceid) + " " + str(self.speed) +"/" + str(self.maxroadspeed) + " kmph " +
                            str(self.rpm) + " rpm " + str(self.gear) + 
                            " lat: " + str(self.lat) + " lon: " + str(self.lon) + 
                            " " + str(self.segment) + 
                            " " + str(self.road), (127, 18), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        frame = cv2.putText(frame, str(self.systemmode), (w-20, 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 0, 255), 2, cv2.LINE_AA)
        
        frame = cv2.putText(frame, str(self.deviationflags), (10, 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, 
                            (255, 0, 255), 1, cv2.LINE_AA)
        
        self.drawStats(frame,frontstat)
     
    def drawStats(self,frame,frontstat):
        h,w,c = frame.shape
    
    def drawDetections(self,frame):
        # frame = self.processor.overspeed.draw(frame)
        frame = self.processor.collision.draw(frame)
        return frame
    
    def initCounters(self):
        # Deviation Counter objects and tags
        # self.counteroverspeed = DeviationCounter(self.path,"OVERSPEED",self.maxpreframes)
        self.countercollision =  DeviationCounter(self.path,"COLLISION",self.maxpreframes)
        self.counterpedestrian =  DeviationCounter(self.path,"PEDESTRIAN",self.maxpreframes)

        self.counters = collections.deque()
        # self.counters.append(self.counteroverspeed)
        self.counters.append(self.countercollision)
        self.counters.append(self.counterpedestrian)

        self.donedeviationlist = collections.deque()
        # Start Deviation Video Recorder
        self.deviationrecorder = FrontDeviationRecorder(self.path, self.camside)

        # Warning Counter objects and tags
        # self.warningoverspeed = WarningCounter(self.path,"OVERSPEEDWARNING")
        # self.warnings = collections.deque()
        # self.warnings.append(self.warningoverspeed)

    # def updateWarnings(self,warningtags):

    #     for wrn in self.warnings:
    #         if wrn.warningcode in warningtags:
    #             wrn.check(isvalid=True)
    #         else:
    #             wrn.check(isvalid=False)
                
    #         if wrn.showalert:
    #             self.playAlert(wrn.getAlertMessage(), wrn.warningcode)
    
    def updateCounters(self, camside, systemmode, frame, deviationtags, dataparsed, frontstat):

        for cnt in self.counters:
            if cnt.deviationcode in deviationtags:
                # cnt.check(camside,systemmode,frame,True,dataparsed,self.speed,self.maxroadspeed,frontstat)
                cnt.check(camside,systemmode,frame,True,dataparsed,self.speed,self.maxroadspeed,frontstat,self.thumbnailframe)
                # camside, systemmode, frame, devstat, dataparsed, speed, maxroadspeed, framestat
            else:
                # cnt.check(camside,systemmode,frame,False,dataparsed,self.speed,self.maxroadspeed,frontstat)
                cnt.check(camside,systemmode,frame,False,dataparsed,self.speed,self.maxroadspeed,frontstat,self.thumbnailframe)

            if cnt.soundstatus != "NONE":
                self.playAlert(cnt.soundstatus, cnt.deviationcode)
            
            if cnt.status == "RUNNING":
                self.deviationflags = self.deviationflags + cnt.deviationcode + " "
                # print("TAGS:", self.deviationflags)

            if cnt.status == "DONE":
                self.donedeviationlist.append(DeviationRecord(cnt.systemmode,
                                                                self.path,
                                                                cnt.deviationcode,
                                                                cnt.deviationid,
                                                                cnt.devstart,
                                                                cnt.devend,
                                                                cnt.devmaxspeed,
                                                                cnt.devmaxroadspeed,
                                                                cnt.preframes,
                                                                cnt.preframesdata,
                                                                cnt.frames,
                                                                cnt.framedata,
                                                                cnt.framesounds,
                                                                self.maxpostframes,
                                                                self.recording_fps,
                                                                cnt.deviationthumbnail))
                cnt.reset()
        
        self.updateDoneCounters(frame,dataparsed,frontstat)
        self.sendStatus(deviationtags,frontstat)

    def updateDoneCounters(self, frame, dataparsed, frontstat):
        removeditem = []

        for done in self.donedeviationlist:
            done.addFrame(frame.copy(),dataparsed, frontstat)
            print("Done for DeviationID:", done.deviationid,"Status:",done.status)
            if done.status == "DONE":
                removeditem.append(done)
                self.deviationrecorder.records.append(copy.copy(done))

        for item in removeditem:
            self.donedeviationlist.remove(item)
        
        removeditem = None

    def sendStatus(self,deviationtags,frontstat):
        
        devstatus = (len(deviationtags)>0)
        devtag = str(deviationtags).replace("[","").replace("]","").replace("'","").replace(" ","")

        str_movement = self.camside + "|" + str(self.deviceid) + "|" + str(devstatus) + "|" + str(devtag) + "|" + str(devtag) + "|" + str(bool(devstatus)) + "|"        
        # str_movement = str_movement + str(self.speed) + "|" + str(self.lat) + "|" + str(self.lon) + "|" + str(self.sta) + "|" + str(self.segment) + "|" + str(self.road) + "|" + str(self.maxroadspeed) + "|" + str(self.rpm) + "|" + str(self.gear) + "|" +  str(self.numsat) + "|"
        str_movement = str_movement + str(self.speed) + "|" + str(self.lat) + "|" + str(self.lon) + "|" + str(self.sta) + "|" + str(self.segment) + "|" + str(self.road) + "|" + str(self.maxroadspeed) + "|" + str(self.rpm) + "|" + str(self.gear) + "|" +  str(self.numsat) + "|"+  str(self.speedcanbus) + "|"+  str(self.speedsource) + "|" + str(self.restricted) + "|" + str(self.highrisk) + "|" + str(self.nrp) + "|" + str(self.start_shift) + "|" + str(self.end_shift) + "|" + str(self.is_authorized) + "|" + str(self.location_hr) + "|" + str(self.gpsdataloghearbeat) + "|"
        
        print("SEND STATUS:",str_movement )
        self.udp.sendto(bytes( str_movement , "utf-8"), (self.udpserverip, self.udpserverport))

        # Sent to UDP vlog
        # self.udp.sendto(bytes( str_movement , "utf-8"), (self.udpserverip,5858))

    def process(self,framecap,dataid,dataparsed,deviceinfo,unknownoverspeed):
        
        self.deviationflags = ""
        # Check config
        self.checkConfig()

        # Process received data
        dataparsed = self.checkData(dataid,dataparsed,deviceinfo)

        # Local Variables
        warningtags = []
        deviationtags = []
        ispassed = False
        frontstat = ("None","None")

        # Duplicate original received frame
        oriframecap = None
        processedframe = None
        try:
            oriframecap = framecap.copy()
            processedframe = framecap.copy()
            self.thumbnailframe = framecap.copy()
        except:
            self.sendStatus(deviationtags,frontstat)
            return processedframe,deviationtags,dataid,dataparsed

        # If reset flag is still active, do not process anything
        if len(self.resetflag)>0:
            self.sendStatus(deviationtags,frontstat)
            return processedframe,deviationtags,dataid,dataparsed

        if int(self.systemmode)==2: # 1: Operational, 2: Testing/ Simulation, 3: Inactive Detection
            self.speed = 99
        
        # Check minimum speed to proceed
        # If current speed is None or less than minimun speed, do not proceed
        if self.speed is not None:
            if int(self.speed) >= int(self.minimumspeed):
                ispassed = True
        elif dataparsed is None:
            # No UDP Data received from Server
            dataparsed = self.generateDefaultData()  
            self.parseData(dataid,dataparsed)
            ispassed = True
        else:
            ispassed = True
        
        if int(self.systemmode)==3: # 1: Operational, 2: Testing/ Simulation, 3: Inactive Detection
            ispassed = False

        # If any invalid conditions for proceeding, return frame and deduct all counters
        if not ispassed:
            # Deduct all warnings
            # self.updateWarnings(warningtags)
            # Deduct all counters
            self.updateCounters(self.camside,self.systemmode,processedframe,deviationtags,dataparsed,frontstat)
            self.drawLabels(processedframe,frontstat)
            return processedframe,deviationtags,dataid,dataparsed

        # Otherwise all conditions are good to continue process
        # Process received frame
        processedframe, deviationtags, warningtags, frontstat = self.processor.process(self.systemmode,processedframe,dataparsed,unknownoverspeed)
        print("@@@@@@@@@@  DEVIATION TAGS New:", deviationtags, "WarningTags:", warningtags)
        # Update Counters
        self.updateCounters(self.camside,self.systemmode,processedframe,deviationtags,dataparsed,frontstat)
        # Update Warnings
        # self.updateWarnings(warningtags)

        # Return processed frame
        self.drawLabels(processedframe,frontstat)
        processedframe = self.drawDetections(processedframe)
        return processedframe,deviationtags,dataid,dataparsed