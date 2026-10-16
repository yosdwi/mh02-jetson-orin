import cv2
import collections
import time
import datetime
import threading
import os
import copy
import winsound
import socket
from classes.Config import *
from classes.Config import *

import json


class FrontDeviationRecorder:
    def __init__(self, path, side):
        self.path = path
        self.side = side
        self.config = Config(self.path)
        self.flag = collections.deque(maxlen=1)
        self.records = collections.deque()
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpserverip = str(self.config.getValue("UDP_SERVER_IP"))
        self.udpserverport = int(self.config.getValue("UDP_DEVIATION_SERVER_PORT"))
        self.config = Config("D:\\smartd\\script\\mh02model\\files\\configs\\mh02_front.json")
        threading.Thread(target=self.run, args=(1,)).start()

    def drawLabels(self,mode,frame,datalabel):
        h,w,c = frame.shape

        deviationid, timestamp, deviceid,speed,maxroadspeed,rpm,gear,lat,lon,segment,road,deviation = datalabel
            
        
        dt = str(datetime.datetime.fromtimestamp(timestamp))
        frame = cv2.rectangle(frame, (0,0), (w,40), (41, 41, 41),-1)
        frame = cv2.putText(frame, dt, (10, 18), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        frame = cv2.putText(frame, str(deviceid) + " " + str(speed) +"/" + str(maxroadspeed) + " kmph " +
                            str(rpm) + " rpm " + str(gear), (127, 18), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        frame = cv2.putText(frame, " lat: " + str(lat) + " lon: " + str(lon) + 
                            " " + str(segment) + 
                            " " + str(road), (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        
        frame = cv2.putText(frame, str(deviationid), (10, 58), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, 
                                    (0,0,255), 1, cv2.LINE_AA)
        
        
        if mode == 1:
            frame = cv2.putText(frame, str(deviation), (10, 70), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, 
                                (255, 0, 255), 1, cv2.LINE_AA)
            
        return frame

    def resize(self,frame,w,h):

        return cv2.resize(frame,(w,h))    

    def run(self, mode):
       
        while True:
            time.sleep(0.1)

            if len(self.flag)>0:
                break
            
            rec = None
            # Check and Iterate completed deviations for recording to video
            while self.records:
                self.config.load()
                FRAME_FRONT_SIZE = self.config.getValue("FRAME_FRONT_SIZE")
                _cw, _ch = int(FRAME_FRONT_SIZE.split(",")[0]), int(FRAME_FRONT_SIZE.split(",")[1])
                time.sleep(0.1)
                
                rec = self.records.popleft()
                
                print(">>>>>>>>RECORDING START:", rec.deviationid)

                # Create path
                fname_path = rec.filepath + rec.deviationid + "\\"
                os.system("mkdir " + fname_path )

                print("@@@@@@PATH:", fname_path)
                

                fourcc = cv2.VideoWriter_fourcc(*'avc1')   
                videofilename = fname_path + rec.deviationid + ".mp4"
                # videofilename = fname_path + rec.deviationid + ".avi"
                # h,w,c = rec.thumbnail.shape
                h,w,c = _ch, _cw, 3
                fourcc = cv2.VideoWriter_fourcc(*'avc1')  
                # fourcc = cv2.VideoWriter_fourcc("X", "V", "I", "D")

                writer = cv2.VideoWriter(videofilename,fourcc,int(rec.fps),(_cw, _ch))

                logfilename = fname_path + rec.deviationid + ".txt"
                logwriter = open(logfilename, 'a')

                # Record Pre Deviation
                frame = None
                linecounter = 0
                while rec.preframes:
                    line = rec.preframesdata.popleft()
                    rec.parseData(line,self.side)
                    frame = rec.preframes.popleft()
                    frame = self.resize(frame,_cw, _ch)
                    fh,fw,fc = frame.shape
                    if fh==h and fw==w:
                        if self.side == "FRONT":
                            frame = self.drawLabels(0,frame,  
                                                    (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                    rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                    rec.segment,rec.road,rec.deviationcode)
                                                    )
                            pass

                        writer.write(frame)
                        linecounter += 1
                        logwriter.write(rec.deviationcode + "," +
                                        rec.deviationid + "," +
                                        str(linecounter) + "," +
                                        "PRE," + str(line).replace("[","").replace("]","") + '\r')

                        logwriter.flush()
                os.fsync(logwriter.fileno())

                # Record On Deviation
                frame = None
                udpdevmessage = None
                thumbready = False

                while rec.frames:     
                    line = rec.framedata.popleft()    
                    rec.parseData(line,self.side)     
                    
                    # Prepare UDP Message for Completed Deviation
                    if udpdevmessage is None:
                        udpdevmessage = self.side + ";" + str(rec.deviationid) + ";" + str(rec.devstart) + ";" + str(rec.devend) + ";" + str(rec.devmaxspeed) + ";" + str(rec.segment) + ";" + str(rec.road) + ";" + str(rec.lat) + ";" + str(rec.lon) + ";" + str(rec.maxroadspeed) + ";" 

                        # Create JSON Data for Deviation Information
                        jsonfilename = f"{fname_path}{rec.deviationid}.json"

                        jsondata = {
                            "deviationid": rec.deviationid,
                            "deviationstart": rec.devstart,
                            "deviationend": rec.devend,
                            "speed": rec.speed,
                            "segment": rec.segment,
                            "road": rec.road,
                            "lat": rec.lat,
                            "lon": rec.lon,
                            "maxroadspeed": rec.maxroadspeed,
                            "deviceid": rec.deviceid,
                            "timestamp": rec.timestamp,
                            "deviationcode": rec.deviationcode,
                            "unitno": rec.unitno,
                            "numsat": rec.numsat
                        }

                        with open(jsonfilename, "w") as j:
                            json.dump(jsondata, j, indent=4)     

                    frame = rec.frames.popleft()
                    frame = self.resize(frame,_cw, _ch)
                    fh,fw,fc = frame.shape

                    if self.side == "FRONT":
                        frame = self.drawLabels(1,frame,  
                                                (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                rec.segment,rec.road,rec.deviationcode)
                                                )
                    
                    writer.write(frame)
                    linecounter += 1
                    logwriter.write(rec.deviationcode + "," +
                                        rec.deviationid + "," +
                                        str(linecounter) + "," +
                                        "ON," + str(line).replace("[","").replace("]","") + '\r')
                    logwriter.flush()

                    if not thumbready:
                        thumbfilename1 = fname_path + rec.deviationid + ".jpg"
                        thumbfilename2 = fname_path + "thumbnail.jpg"
                        cv2.imwrite(thumbfilename1, frame)
                        cv2.imwrite(thumbfilename2, frame)
                        thumbready = True

                os.fsync(logwriter.fileno())

                # Record Post Deviation
                frame = None
                while rec.postframes:
                    line = rec.postframesdata.popleft()
                    rec.parseData(line,self.side)
                    frame = rec.postframes.popleft()
                    frame = self.resize(frame,_cw, _ch)
                    fh,fw,fc = frame.shape
                    if fh==h and fw==w:
                    
                        if self.side == "FRONT":
                            frame = self.drawLabels(0,frame,  
                                                    (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                    rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                    rec.segment,rec.road,rec.deviationcode)
                                                    )
                        
                        writer.write(frame)
                        linecounter += 1
                        logwriter.write(rec.deviationcode + "," +
                                        rec.deviationid + "," +
                                        str(linecounter) + "," +
                                        "POS," + str(line).replace("[","").replace("]","") + '\r')
                        logwriter.flush()
                
                os.fsync(logwriter.fileno())

                frame = None
                writer.release()
                logwriter.close()

                if rec.systemmode == 1 and udpdevmessage is not None:
                    # Send UDP Message for Completed Deviation
                    self.udp.sendto(bytes( udpdevmessage , "utf-8"), (self.udpserverip, self.udpserverport))

                print(">>>>>>>>RECORDING END:", rec.deviationid)

    def stop(self,mode):
        self.flag.append(mode)
