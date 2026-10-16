import collections
import copy
import time
from classes.Config import *

class DeviationRecord:
    def __init__(self, systemmode, path, deviationcode, deviationid, devstart, devend, 
                devmaxspeed, devmaxroadspeed,preframes, preframesdata, frames, framedata, framesounds, maxpostframes, fps, deviationthumbnail):
        
        self.systemmode = systemmode
        self.path = path
        self.config = Config(path)
        self.deviationcode = deviationcode
        self.deviationid = deviationid

        self.devstart = devstart
        self.devend = devend
        self.devmaxspeed = devmaxspeed
        self.devmaxroadspeed = devmaxroadspeed

        self.filepath = str(self.config.getValue("RECORDING_PATH"))
        # self.fps = int(self.config.getValue("RECORDING_FPS"))
        self.fps = fps
        # self.thumbnail = frames.copy().popleft()
        self.thumbnail = frames.copy().popleft()
        self.preframes = preframes.copy()
        self.preframesdata = preframesdata.copy()
        self.frames = frames.copy()
        self.framedata = framedata.copy()
        self.framesounds = framesounds.copy()
        self.maxpostframes = maxpostframes
        self.postframes = collections.deque(maxlen=self.maxpostframes)
        self.postframesdata = collections.deque(maxlen=self.maxpostframes)
        self.status = "WAITING"

        self.deviationthumbnail = deviationthumbnail.copy().popleft()
    
    def parseData(self,dataparsed,camside):
        # print("PARSE DATA:", dataparsed)
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
        self.gpsdatalogheartbeat = dataparsed[13]
        # ['1686194522', 'deviceid', 'unitno', '0', 'lat', 'lon', 'sta', 'segment', 'road', '55', '863', '3', '']
        # ['1686194522', 'deviceid', 'unitno', '0', 'lat', 'lon', 'sta', 'segment', 'road', '55', '863', '3', '', -1, -1, -1, 0, 0, False, False]
        # 13:  -1, -1, -1, 0, 0, False, False
        # earright,earleft,mar,pitch,yaw,masked,glasses = facestat
        
        if camside == "CABIN":
            self.earright = dataparsed[15]
            self.earleft = dataparsed[16]
            self.mar = dataparsed[17]
            self.pitch = dataparsed[18]
            self.yaw = dataparsed[19]
            self.masked = dataparsed[20]
            self.glasses = dataparsed[21]

    def addFrame(self, frame, dataparsed, framestat):
        if len(self.postframes) < self.maxpostframes:
            try:
                dataparsed = dataparsed + list(framestat)
            except:
                dataparsed = dataparsed + framestat

            self.postframes.append(frame.copy())
            self.postframesdata.append(copy.copy(dataparsed))
        else:
            self.status = "DONE"
