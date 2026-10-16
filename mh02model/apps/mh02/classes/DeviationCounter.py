import collections
import datetime
import copy
import socket
import numpy
from classes.Config import *

class DeviationCounter:
    
    def __init__(self, path, deviationcode, maxpreframes):
        self.config = Config(path)
        self.deviationcode = deviationcode
        self.maxpreframes = maxpreframes
        self.loadParams()
        self.reset()
        
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpserverip = str(self.config.getValue("UDP_SERVER_IP"))
        self.udpserverport = int(self.config.getValue("UDP_DEVIATION_SERVER_PORT"))

    def loadParams(self):
        self.deviationparams = (self.config.getValue(self.deviationcode + "_PARAMS")).split("|")
        self.visualthreshold = int(self.deviationparams[0])
        self.soundthreshold = int(self.deviationparams[1])
        self.maxdeductionsteps = int(self.deviationparams[2])
        self.deviationdesc = self.deviationparams[4]
        self.deviationsoundfile = self.deviationparams[5]
        self.deviationsoundtext = self.deviationparams[6]
        # print(self.deviationparams)

    def updateParams(self):
        if self.status != "IDLE":
            return
        self.config.load()
        self.loadParams()

    def reset(self):
        self.systemmode = 1
        self.deviationid = None
        self.devstart = None
        self.devend = None
        self.devmaxspeed = 0
        self.devmaxroadspeed = 0
        self.preframes = collections.deque(maxlen=self.maxpreframes)
        self.preframesdata = collections.deque(maxlen=self.maxpreframes)
        self.frames = collections.deque()
        self.framedata = collections.deque()
        self.framesounds = collections.deque()
        self.counter = 0
        self.deductioncounter = 0
        self.status = "IDLE"
        self.soundstatus = "NONE"

        self.deviationthumbnail = collections.deque(maxlen=1)

    def start(self, camside, systemmode, frame, dataparsed, soundtext, speed, devmaxroadspeed, thumbnailframe):
        self.systemmode = systemmode
        if int(self.systemmode) == 1:
            tag = ""
        elif int(self.systemmode) == 2:
            tag = "TESTING_"
        
        dt = datetime.datetime.fromtimestamp(float(dataparsed[0]))
        self.devstart = dt.strftime("%Y%m%d_%H%M%S")
        self.devmaxspeed = speed
        self.devmaxroadspeed = devmaxroadspeed
        self.deviationid = tag + self.deviationcode + "_" + self.devstart #datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.frames.append(frame.copy())
        self.framedata.append(dataparsed)
        self.soundstatus = self.deviationsoundtext
        self.framesounds.append(soundtext)
        self.status = "RUNNING"

        self.deviationthumbnail.append(thumbnailframe.copy())

        # Send Incomplete Deviation to Server by UDP
        msgalert = "INCOMPLETE_" + camside +";" + camside + ";" + self.deviationcode + ";" + self.deviationid + ";" + self.devstart + ";"
        self.udp.sendto(bytes(msgalert, "utf-8"), (self.udpserverip, self.udpserverport))
        print(self.udpserverip, self.udpserverport, msgalert)

    def end(self,dataparsed):
        dt = datetime.datetime.fromtimestamp(float(dataparsed[0]))
        self.devend = dt.strftime("%Y%m%d_%H%M%S")
        self.status = "DONE"
        self.soundstatus = "NONE"

    def check(self, camside, systemmode, frame, devstat, dataparsed, speed, maxroadspeed, framestat, thumbnailframe):
        # FRONT 1 False ['1687163120', 'deviceid', 'unitno', '93', 'lat', 'lon', 'sta', 'segment', 'road', '58', '62', '6', ''] 93 58 None
        if dataparsed is not None:
            try:
                dataparsed = dataparsed + list(framestat)
            except:
                try:
                    dataparsed = dataparsed + framestat
                except:
                    print("FRAMESTAT ERROR:", framestat)
                    pass

        if self.status in ("IDLE", "WAITING"):
            self.preframes.append(frame.copy())
            self.preframesdata.append(dataparsed)
        if devstat:
            self.counter += 1
            if self.status == "IDLE" and self.counter > 0:
                self.status = "WAITING"
            elif self.status == "WAITING" and self.counter >= self.visualthreshold:
                self.start(camside,systemmode,frame,dataparsed,self.deviationsoundtext, speed, maxroadspeed, thumbnailframe)
            elif self.status == "RUNNING":
                if self.devmaxspeed < speed:
                    self.devmaxspeed = speed
                self.frames.append(frame.copy())
                self.framedata.append(copy.copy(dataparsed))
                self.deductioncounter = 0
                if self.counter >= self.soundthreshold:
                    self.counter = self.visualthreshold
                    self.soundstatus = self.deviationsoundtext
                    self.framesounds.append(self.soundstatus)
                else:
                    self.soundstatus = "NONE"     
                    self.framesounds.append(None)
            elif self.status == "DONE":
                self.counter = 0
                self.deductioncounter = 0
                self.soundstatus = "NONE"
        else:
            self.counter -= 1
            if self.status == "IDLE" and self.counter < 0:
                self.counter = 0
            elif self.status == "WAITING" and self.counter < 0:
                self.reset()
            elif self.status == "WAITING" and self.counter > 0:
                self.deductioncounter += 1
                if self.deductioncounter >= self.maxdeductionsteps:
                    self.reset()
            elif self.status == "RUNNING":
                self.frames.append(frame.copy())
                self.framedata.append(dataparsed)
                self.soundstatus = "NONE" 
                self.framesounds.append(None)
                self.deductioncounter += 1
                if self.deductioncounter >= self.maxdeductionsteps:
                    self.end(dataparsed)
            elif self.status == "DONE":
                self.counter = 0
                self.deductioncounter = 0
                self.soundstatus = "NONE"

        # if self.deviationcode == "YAWNING":
            # print("Counter Detail:",self.deviationcode,self.counter,self.deductioncounter,self.maxdeductionsteps,self.devmaxspeed,self.devmaxroadspeed,self.status,self.soundstatus)
