# Update History
# Version 6.2
# 2024-06-18    JRP     Happy 21st years in PAMA ;)
#                       (1) Split Fatigue Detection and Behavior Detection
#                           to improve system performance.
#                       (2) Implement 0 kmph detection and alert mode.

import cv2
import collections
import time
# import datetime
import threading

# Removed get_now() and get_fromtimestamp() functions - using time.time() and time.strftime() instead

import os
import copy
import socket
import traceback
import uuid
import numpy

from classes.Config import *
from classes.ProcessorFrontOverspeed import *

from classes.AlertPlayerFront import *
from classes.AlertLogger import *
from classes.DeviationCounter import *
from classes.FrontDeviationRecord import *
from classes.FrontOverspeedDeviationRecorder import *
from classes.WarningCounter import *
from classes.MineAwarenessWarningCounter import *

class VisualizerFrontOverspeed:

    def __init__(self,path,maxiddle,maxpreframes,maxpostframes,deviceinfo,recording_fps):

        # Camera stream frame
        self.thumbnailframe = None

        self.camstream = collections.deque(maxlen=1)
        self.camstreamframe = None
        self.lastdeviationtags = []
        self.lastdataparsed = None
        self.lastfrontstat = None
        self.lastwarningtags = None
        self.countflag = False

        # Initiate config reader
        self.path = path
        self.config = Config(path)
        self.camside = str(self.config.getValue("CAMSIDE"))
        self.systemmode = int(self.config.getValue("SYSTEM_MODE_FRONT"))
        self.systemmodealert = int(self.config.getValue("ALERT_MODE_FRONT"))
        self.deviceinfo = deviceinfo
        self.recording_fps = recording_fps
        self.coloradjusterstatus = True
        self.gammapoint = 1

        # FATIGUE 0 KMPH
        # self.fatigue_active_mode = int(self.config.getValue("FATIGUE_ACTIVE_ANYTIME"))
        # self.fatigue_alert_mute_times = str(self.config.getValue("FATIGUE_ALERT_MUTE_TIME"))
        # self.fatigue_active_mode_max_speed = int(self.config.getValue("FATIGUE_ACTIVE_ANYTIME_MAX_SPEED"))

        # UDP Client
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpserverip = str(self.config.getValue("UDP_SERVER_IP"))
        self.udpserverport = int(self.config.getValue("UDP_STATUS_SERVER_PORT_OVERSPEED"))

        self.udpserverport_deviation = int(self.config.getValue("UDP_DEVIATION_SERVER_PORT"))

        # Initiate frame processor
        self.processor = ProcessorFrontOverspeed(path)

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
        self.alertlogger = AlertLogger() 

        # Initiate Counters
        self.initCounters()

        # Start Real Time Threading
        threading.Thread(target=self.run, args=(1,)).start()

    def run(self, mode):
        while True:

            if len(self.stopflag) > 0:
                break

            if len(self.camstream) > 0:
                self.camstreamframe = self.camstream.popleft()                
                
                # Update Counters
                if self.lastfrontstat is not None:
                    if self.countflag:           
                        self.updateCounters(self.camside,self.systemmode)
                        self.drawLabels()

                        self.updateWarnings()

                # cv2.imshow("Real Time", self.camstreamframe)
                # if cv2.waitKey(1) == 27:
                #     pass                    
            
            time.sleep(1/100)

    def playAlert(self, sound_text, alert_type="UNKNOWN"):
        if self.systemmode == 1:
            self.alertplayer.add(sound_text, alert_type)
            pass

        if self.lastdeviationtags and self.lastwarningtags:
            tags = self.lastdeviationtags + self.lastwarningtags
        elif self.lastdeviationtags:
            tags = self.lastdeviationtags
        elif self.lastwarningtags:
            tags = self.lastwarningtags
        else:
            tags = [alert_type]
        
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
            # gpsdataloghearbeat=self.gpsdataloghearbeat
        )
    
    def checkConfig(self):
        if int((time.time() - self.lastconfigcheck)) >= self.maxconfigiddle:
            self.config.load()
            self.lastconfigcheck = time.time()
            # Update Visualizer Parameters
            # self.systemmode = int(self.config.getValue("SYSTEM_MODE_CABIN"))
            # self.fatigue_active_mode = int(self.config.getValue("FATIGUE_ACTIVE_ANYTIME"))
            # self.fatigue_alert_mute_times = str(self.config.getValue("FATIGUE_ALERT_MUTE_TIME"))
            # self.fatigue_active_mode_max_speed = int(self.config.getValue("FATIGUE_ACTIVE_ANYTIME_MAX_SPEED"))

            # self.coloradjusterstatus = int(self.config.getValue("FRAME_CABIN_COLOR_ADJUSTER"))
            # self.gammapoint = float(self.config.getValue("FRAME_CABIN_GAMMA"))

            self.systemmode = int(self.config.getValue("SYSTEM_MODE_FRONT"))
            #Update Counter Parameters
            for cnt in self.counters:
                cnt.updateParams()

            #Update Alert Player
            self.alertplayer.update()
        
    def initVars(self):
        self.timestamp = int(time.time()) #No timestamp from server so use system time
        self.deviceid, self.unitno = self.deviceinfo
        self.speed = 0
        self.lat = 0
        self.lon = 0
        self.sta = ""
        self.segment = ""
        self.road = ""
        self.maxroadspeed = 40
        self.rpm = 0
        self.gear = 0
        self.numsat = 0
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

        # self.minimumspeed = self.config.getValue("MINIMUM_SPEED_CAB")
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
        dataparsed = (int(time.time()),_deviceid,_unitno,"-9999","-8888","-8888","STA","UNKNOWN","UNKNOWN","0","0","0","0","0","0","0","0","","","","0","")
        
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

    def drawLabels(self):

        dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.timestamp))
        h,w,c = self.camstreamframe.shape
        self.camstreamframe = cv2.rectangle(self.camstreamframe, (0,0), (w,30), (41, 41, 41),-1)
        self.camstreamframe = cv2.putText(self.camstreamframe, dt, (10, 18), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        self.camstreamframe = cv2.putText(self.camstreamframe, str(self.deviceid) + " " + str(self.speed) +"/" + str(self.maxroadspeed) + " kmph " +
                            str(self.rpm) + " rpm " + str(self.gear) + 
                            " lat: " + str(self.lat) + " lon: " + str(self.lon),(127, 18),
                            # " lat: " + str(self.lat) + " lon: " + str(self.lon) + 
                            # " " + str(self.segment) + 
                            # " " + str(self.road), (127, 18), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        self.camstreamframe = cv2.putText(self.camstreamframe, str(self.systemmode), (w-20, 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 0, 255), 2, cv2.LINE_AA)
        
        self.camstreamframe = cv2.putText(self.camstreamframe, str(self.deviationflags), (10, 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, 
                            (255, 0, 255), 1, cv2.LINE_AA)
        
        self.drawStats()
     
    def drawStats(self):
        h,w,c = self.camstreamframe.shape

        # strfrontstat = "EAR: ("
        # earright,earleft,mar,pitch,yaw,masked,glasses = self.lastfrontstat
        # if earright < 0:
        #     strfrontstat = strfrontstat + "NA:"
        # else:
        #     strfrontstat = strfrontstat + str(round(earright,2)) + ":"

        # if earleft < 0:
        #     strfrontstat = strfrontstat + "NA) "
        # else:
        #     strfrontstat = strfrontstat + str(round(earleft,2)) + ") "

        # if mar >= 0:
        #     strfrontstat = strfrontstat + "MAR: " + str(round(mar,2)) + " "
        # else:
        #     strfrontstat = strfrontstat + "MAR: NA "        
        # strfrontstat = strfrontstat + "P: " + str(round(pitch,2)) + ", Y:" + str(round(yaw,2))
        strfrontstat = str(self.segment) + " " + str(self.road)
        # strfrontstat = strfrontstat + " G: " + str(self.gammapoint) +", CA: " + str(self.coloradjusterstatus)

        self.camstreamframe = cv2.rectangle(self.camstreamframe, (0,h-30), (w,h), (41, 41, 41),-1)

        self.camstreamframe = cv2.putText(self.camstreamframe, strfrontstat, (10, h-12), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
    
    def drawDetections(self,frame):
        # frame = self.processor.poselandmark.draw(frame)
        # if self.processor.seatbeltdetector is not None:
        #     frame = self.processor.seatbeltdetector.draw(frame)
        # frame = self.processor.facelandmark.draw(frame)
        # frame = self.processor.eyeglass.draw(frame)
        # frame = self.processor.smoking.draw(frame)
        # frame = self.processor.hands.draw(frame)
        # frame = self.processor.phoning.draw(frame)
        return frame
    
    def initCounters(self):
        # Deviation Counter objects and tags
        # self.counternoface = DeviationCounter(self.path,"NOFACE",self.maxpreframes)
        # self.counterclosedeyes =  DeviationCounter(self.path,"CLOSEDEYES",self.maxpreframes)
        # self.counteryawning =  DeviationCounter(self.path,"YAWNING",self.maxpreframes)
        # self.counterheadup =  DeviationCounter(self.path,"HEADUP",self.maxpreframes)
        # self.counterheaddown =  DeviationCounter(self.path,"HEADDOWN",self.maxpreframes)
        # self.counterheadleft =  DeviationCounter(self.path,"HEADLEFT",self.maxpreframes)
        # self.counterheadright =  DeviationCounter(self.path,"HEADRIGHT",self.maxpreframes)
        # self.counterseatbelt =  DeviationCounter(self.path,"SEATBELT",self.maxpreframes)
        # # self.counterfacemask = DeviationCounter(self.path,"FACEMASK",self.maxpreframes)
        # self.countereyeglass = DeviationCounter(self.path,"EYEGLASS",self.maxpreframes)
        # self.countersmoking = DeviationCounter(self.path,"SMOKING",self.maxpreframes)
        # # self.counterhandonmouth = DeviationCounter(self.path,"HANDONMOUTH",self.maxpreframes)
        # self.counterphoning = DeviationCounter(self.path,"PHONING",self.maxpreframes)

        self.counteroverspeed = DeviationCounter(self.path,"OVERSPEED",self.maxpreframes)
        self.counterhighrisk = DeviationCounter(self.path,"HIGHRISK",self.maxpreframes)
        self.counterhighrisk_restricted = DeviationCounter(self.path,"RESTRICTED",self.maxpreframes)

        self.counters = collections.deque()
        self.counters.append(self.counteroverspeed)
        self.counters.append(self.counterhighrisk)
        self.counters.append(self.counterhighrisk_restricted)
        # self.counters.append(self.counternoface)
        # self.counters.append(self.counterclosedeyes)
        # self.counters.append(self.counteryawning)
        # self.counters.append(self.counterheadup)
        # self.counters.append(self.counterheaddown)
        # self.counters.append(self.counterheadleft)
        # self.counters.append(self.counterheadright)
        # self.counters.append(self.counterseatbelt)
        # # self.counters.append(self.counterfacemask)
        # self.counters.append(self.countereyeglass)
        # self.counters.append(self.countersmoking)
        # # self.counters.append(self.counterhandonmouth)
        # self.counters.append(self.counterphoning)

        self.donedeviationlist = collections.deque()
        # Start Deviation Video Recorder
        self.deviationrecorder = FrontOverspeedDeviationRecorder(self.path, self.camside)

        # Warning Counter objects and tags
        self.warningoverspeed = WarningCounter(self.path,"OVERSPEEDWARNING")
        self.warningauthorized = MineAwarenessWarningCounter(self.path,"AUTHORIZEDWARNING")
        self.warnings = collections.deque()
        self.warnings.append(self.warningoverspeed)
        self.warnings.append(self.warningauthorized)

    def updateWarnings(self):

        for wrn in self.warnings:
            if wrn.warningcode in self.lastwarningtags:
                wrn.check(isvalid=True)
            else:
                wrn.check(isvalid=False)
                
            if wrn.showalert:
                dt_timestamp = float(self.lastdataparsed[0])
                dt = time.strftime('%Y%m%d_%H%M%S', time.localtime(dt_timestamp))
                devstart = dt

                self.playAlert(wrn.getAlertMessage(), wrn.warningcode)
                print(f"DEBUG: Played warning alert: {wrn.warningcode}")
                
                # udpdevmessage = self.camside + ";" + str(self.lastwarningtags) + ";" + str(devstart) + ";" + str(devstart) + ";" + str(self.speed) + ";" + str(self.segment) + ";" + str(self.road) + ";" + str(self.lat) + ";" + str(self.lon) + ";" + str(self.maxroadspeed) + ";" + str(self.location) + ";"
                udpdevmessage = self.camside + ";" + str(self.lastwarningtags[0]) + ";" + str(devstart) + ";" + str(devstart) + ";" + str(self.speed) + ";" + str(self.segment) + ";" + str(self.road) + ";" + str(self.lat) + ";" + str(self.lon) + ";" + str(self.maxroadspeed) + ";" 
                 # Send UDP Message for Warning Logs
                self.udp.sendto(bytes( udpdevmessage , "utf-8"), (self.udpserverip, self.udpserverport_deviation))

    def updateCounters(self, camside, systemmode):
        self.deviationflags = ""

        # Adjust current timestamp
        # (int(time.time()),DEVICE_ID,UNIT_NO,"-9999","-8888","-8888","STA","UNKNOWN","UNKNOWN","0","0","0",None,None,None,None,None,None,False,False)
        
        # self.lastdataparsed[0] = int(time.time())
        try:    
            self.lastdataparsed[0] = int(time.time())
        except:
            _lastdataparsed = list(self.lastdataparsed)
            _lastdataparsed[0] = int(time.time())
            self.lastdataparsed = _lastdataparsed
        
        for cnt in self.counters:
            if cnt.deviationcode in self.lastdeviationtags:
                # cnt.check(camside,systemmode,self.camstreamframe,True,self.lastdataparsed,self.speed,self.maxroadspeed,self.lastfrontstat)
                cnt.check(camside,systemmode,self.camstreamframe,True,self.lastdataparsed,self.speed,self.maxroadspeed,self.lastfrontstat,self.thumbnailframe)
            else:
                # cnt.check(camside,systemmode,self.camstreamframe,False,self.lastdataparsed,self.speed,self.maxroadspeed,self.lastfrontstat)
                cnt.check(camside,systemmode,self.camstreamframe,False,self.lastdataparsed,self.speed,self.maxroadspeed,self.lastfrontstat,self.thumbnailframe)

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
                                                                cnt.deviationthumbnail
                                                                ))
                cnt.reset()
        
        self.updateDoneCounters(self.camstreamframe,self.lastdataparsed,self.lastfrontstat)
        self.sendStatus(self.lastdeviationtags,self.lastfrontstat)

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

        # if frontstat is not None:            
        #     earright,earleft,mar,pitch,yaw,masked,glasses = frontstat
        # else:
        #     earright,earleft,mar,pitch,yaw,masked,glasses = -2,-2,-2,-2,-2,False,False

        # if deviationtags is not None:
        #     devstatus = (len(deviationtags)>0)
        # else:
        #     devstatus = False
            
        # if devstatus:
        #     devtag = str(deviationtags).replace("[","").replace("]","").replace("'","").replace(" ","")
        # else:
        #     devtag = ""

        # str_movement = self.camside + "|" + str(self.deviceid) + "|" + str(devstatus) + "|" + str(devtag) + "|" + str(devtag) + "|" + str(bool(devstatus)) + "|"        
        # str_movement = str_movement + str(earleft) + "|" + str(earright) + "|" + str(mar) + "|" + str(pitch) + "|" + str(yaw) + "|" + str(bool(masked)) + "|" + str(bool(glasses)) + "|"
        # print("SEND STATUS FATIGUE:", str_movement, self.udpserverip, self.udpserverport)
        # str_movement_vlog = str_movement + str(self.speed) + "|" + str(self.maxroadspeed) + "|" + str(self.rpm) + "|" + str(self.gear) + "|" +  str(self.lat) + "|" +  str(self.lon) +  "|" +  str(self.segment) + "|" +  str(self.road) + "|" +  str("123")
        # self.udp.sendto(bytes( str_movement , "utf-8"), (self.udpserverip, self.udpserverport))

        # #Sent to UDP server vlog
        # self.udp.sendto(bytes( str_movement_vlog , "utf-8"), (self.udpserverip,6868))

        devstatus = (len(deviationtags)>0)
        devtag = str(deviationtags).replace("[","").replace("]","").replace("'","").replace(" ","")

        str_movement = self.camside + "|" + str(self.deviceid) + "|" + str(devstatus) + "|" + str(devtag) + "|" + str(devtag) + "|" + str(bool(devstatus)) + "|"        
        str_movement = str_movement + str(self.speed) + "|" + str(self.lat) + "|" + str(self.lon) + "|" + str(self.sta) + "|" + str(self.segment) + "|" + str(self.road) + "|" + str(self.maxroadspeed) + "|" + str(self.rpm) + "|" + str(self.gear) + "|" +  str(self.numsat) + "|"+  str(self.speedcanbus) + "|"+  str(self.speedsource) + "|" + str(self.restricted) + "|" + str(self.highrisk) + "|" + str(self.nrp) + "|" + str(self.start_shift) + "|" + str(self.end_shift) + "|" + str(self.is_authorized) + "|" + str(self.location_hr) + "|" + str(self.gpsdataloghearbeat) + "|"
        
        print("SEND STATUS:",str_movement )
        self.udp.sendto(bytes( str_movement , "utf-8"), (self.udpserverip, self.udpserverport))

        # Sent to UDP vlog
        self.udp.sendto(bytes( str_movement , "utf-8"), (self.udpserverip,5858))

    def checkDetectionMode(self):
        # _fatigue_active_mode_anytime = self.fatigue_active_mode
        _detection_mode = 0 # 0: Ignore All on All Speed, 10: Active all and current speed is moving, 11: Active All on All Speed, 20: Fatigue Only and current speed is not Moving  
        _ismoving = False

        if self.speed is None:
            self.speed = -9999

        if int(self.systemmode)==3:
            _detection_mode = 0
        else:
            if int(self.systemmode)==2: # Testing Mode
                _detection_mode = 11
                self.alertplayer.vehicleismoving = True
            else:
                # Operation Mode
                if int(self.speed) >= int(self.minimumspeed):
                    _ismoving = True
                else:
                    _ismoving = False
                
                # if int(_fatigue_active_mode_anytime) == 1:
                #     # 0 kph is active
                #     if not _ismoving:
                #         _detection_mode = 20 # 2: Fatigue Only when current speed is not Moving
                #         # Turn off alert when is not moving
                #         self.alertplayer.vehicleismoving = False
                #     else:
                #         _detection_mode = 10 # 10: Active all only is moving
                #         # Turn on alert because it is moving
                #         self.alertplayer.vehicleismoving = True
                # else:
                # 0 kph is NOT active
                if _ismoving:
                    _detection_mode = 10 # 1: Active All on All Speed
                    self.alertplayer.vehicleismoving = True
                else:
                    _detection_mode = 0 # Disable all because current speed is not moving and 0 kph is not active
                    self.alertplayer.vehicleismoving = False
                        
        return _detection_mode

    def process(self,framecap,dataid,dataparsed,deviceinfo,unknownoverspeed):

        # If dataparsed is invalid, system will generate default dataparsed for next process.
        dataparsed = self.checkData(dataid,dataparsed,deviceinfo)

        # Check config
        self.checkConfig()

        _detection_mode = self.checkDetectionMode()

        self.deviationflags = ""
        
        # Local Variables
        warningtags = []
        deviationtags = []
        ispassed = False
        frontstat = (-1,-1,-1,0,0,False,False)

        # If reset flag is still active, do not process anything
        if len(self.resetflag)>0:
            self.countflag = False
            self.sendStatus(deviationtags,frontstat)
            return framecap,deviationtags,dataid,dataparsed

        # Duplicate original received frame
        # oriframecap = None
        processedframe = None
        try:
            # oriframecap = framecap.copy()
            processedframe = framecap.copy()
            self.thumbnailframe = framecap.copy()
        except:
            self.countflag = False
            self.sendStatus(deviationtags,frontstat)
            return processedframe,deviationtags,dataid,dataparsed

        # Process received frame
        # processedframe, deviationtags, frontstat = self.processor.process(self.systemmode,processedframe,dataparsed,_detection_mode,unknownoverspeed)
        processedframe, deviationtags, warningtags, frontstat = self.processor.process(self.systemmode,processedframe,dataparsed,_detection_mode,unknownoverspeed)
        print("@@@@@@@@@@ LAST DEVIATION TAGS Value:", self.lastdeviationtags, "New:", deviationtags, "WarningTags:", warningtags)
        # Update Counters
        self.lastdeviationtags = deviationtags
        self.lastdataparsed = dataparsed
        self.lastfrontstat = frontstat
        self.lastwarningtags = warningtags
        self.countflag = True
        
        # Return processed frame        
        # processedframe = self.drawDetections(processedframe)
        return processedframe,deviationtags,dataid,dataparsed
