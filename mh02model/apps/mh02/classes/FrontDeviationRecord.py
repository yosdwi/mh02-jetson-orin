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
        # ['1686194522', 'deviceid', 'unitno', '0', 'lat', 'lon', 'sta', 'segment', 'road', '55', '863', '3', '']
        # ['1686194522', 'deviceid', 'unitno', '0', 'lat', 'lon', 'sta', 'segment', 'road', '55', '863', '3', '', -1, -1, -1, 0, 0, False, False]
        # 13:  -1, -1, -1, 0, 0, False, False
        # earright,earleft,mar,pitch,yaw,masked,glasses = facestat
        
        # if camside == "CABIN":
            # self.earright = dataparsed[13]
            # self.earleft = dataparsed[14]
            # self.mar = dataparsed[15]
            # self.pitch = dataparsed[16]
            # self.yaw = dataparsed[17]
            # self.masked = dataparsed[18]
            # self.glasses = dataparsed[19]

            # self.earright = dataparsed[18]
            # self.earleft = dataparsed[19]
            # self.mar = dataparsed[20]
            # self.pitch = dataparsed[21]
            # self.yaw = dataparsed[22]
            # self.masked = dataparsed[23]
            # self.glasses = dataparsed[24]

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
