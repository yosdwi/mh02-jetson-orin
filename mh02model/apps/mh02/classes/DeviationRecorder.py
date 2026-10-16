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

import json


class DeviationRecorder:
    def __init__(self, path, side):
        self.path = path
        self.side = side
        self.config = Config(self.path)
        self.flag = collections.deque(maxlen=1)
        self.records = collections.deque()
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpserverip = str(self.config.getValue("UDP_SERVER_IP"))
        self.udpserverport = int(self.config.getValue("UDP_DEVIATION_SERVER_PORT"))
        self.coloradjusterstat = str(self.config.getValue("FRAME_CABIN_COLOR_ADJUSTER"))
        self.gammastat = str(self.config.getValue("FRAME_CABIN_GAMMA"))
        threading.Thread(target=self.run, args=(1,)).start()

    def drawLabels(self,mode,frame,datalabel):
        h,w,c = frame.shape

        if self.side == "CABIN":
            deviationid, timestamp, deviceid,speed,maxroadspeed,rpm,gear,lat,lon,segment,road,deviation,earright,earleft,mar,pitch,yaw,masked,glasses = datalabel

            earright = earright if earright not in ["", "NA", None] else -9
            earleft = earleft if earleft not in ["", "NA", None] else -9
            mar = mar if mar not in ["", "NA", None] else -9

            strfacestat = "EAR: ("
            if earright < 0:
                strfacestat = strfacestat + "NA:"
            else:
                strfacestat = strfacestat + str(round(earright,2)) + ":"

            if earleft < 0:
                strfacestat = strfacestat + "NA) "
            else:
                strfacestat = strfacestat + str(round(earleft,2)) + ") "

            if mar >= 0:
                strfacestat = strfacestat + "MAR: " + str(round(mar,2)) + " "
            else:
                strfacestat = strfacestat + "MAR: NA " 

            if self.coloradjusterstat:
                coloradjusterstat = self.coloradjusterstat
            else:
                coloradjusterstat = "NA"

            if self.gammastat:
                gammastat = self.gammastat
            else:
                gammastat = "NA"

            strfacestat = strfacestat + "P: " + str(round(pitch,2)) + ", Y:" + str(round(yaw,2)) + ", CA:" + str(coloradjusterstat) + ", G:" + str(gammastat)

            frame = cv2.rectangle(frame, (0,h-30), (w,h), (41, 41, 41),-1)

            frame = cv2.putText(frame, strfacestat, (10, h-12), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                                (255, 255, 255), 1, cv2.LINE_AA)
        elif self.side == "FRONT":
            deviationid, timestamp, deviceid,speed,maxroadspeed,rpm,gear,lat,lon,segment,road,deviation = datalabel
            
        
        dt = str(datetime.datetime.fromtimestamp(timestamp))
        # frame = cv2.rectangle(frame, (0,0), (w,30), (41, 41, 41),-1)
        frame = cv2.rectangle(frame, (0,0), (w,40), (41, 41, 41),-1)
        frame = cv2.putText(frame, dt, (10, 18), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
                            (255, 255, 255), 1, cv2.LINE_AA)
        # frame = cv2.putText(frame, str(deviceid) + " " + str(speed) +"/" + str(maxroadspeed) + " kmph " +
        #                     str(rpm) + " rpm " + str(gear) + 
        #                     " lat: " + str(lat) + " lon: " + str(lon) + 
        #                     " " + str(segment) + 
        #                     " " + str(road), (127, 18), 
        #                     cv2.FONT_HERSHEY_SIMPLEX, 0.3, 
        #                     (255, 255, 255), 1, cv2.LINE_AA)
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
    

    def run(self, mode):
        while True:
            time.sleep(0.1)

            if len(self.flag)>0:
                break
            
            rec = None
            isDeviationThumbnail = None

            # Check and Iterate completed deviations for recording to video
            while self.records:
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

                try:
                    h, w, c = rec.deviationthumbnail.shape
                    isDeviationThumbnail = True
                except Exception as e:
                    h,w,c = rec.thumbnail.shape
                    isDeviationThumbnail = False

                fourcc = cv2.VideoWriter_fourcc(*'avc1')  
                # fourcc = cv2.VideoWriter_fourcc("X", "V", "I", "D")          
                writer = cv2.VideoWriter(videofilename,fourcc,int(rec.fps),(w, h))

                logfilename = fname_path + rec.deviationid + ".txt"
                logwriter = open(logfilename, 'a')

                # Record Pre Deviation
                merge_start = int(datetime.datetime.now().timestamp() * 1000)
                frame = None
                linecounter = 0
                while rec.preframes:
                    line = rec.preframesdata.popleft()
                    rec.parseData(line,self.side)
                    frame = rec.preframes.popleft()
                    fh,fw,fc = frame.shape
                    if fh==h and fw==w:
                        if self.side == "CABIN":
                            frame = self.drawLabels(0,frame,  
                                                    (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                    rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                    rec.segment,rec.road,rec.deviationcode,
                                                    rec.earright,rec.earleft,rec.mar,
                                                    rec.pitch,rec.yaw,rec.masked,rec.glasses)
                                                    )
                        elif self.side == "FRONT":
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
                        udpdevmessage = self.side + ";" + str(rec.deviationid) + ";" + str(rec.devstart) + ";" + str(rec.devend) + ";" + str(rec.speed) + ";" + str(rec.segment) + ";" + str(rec.road) + ";" + str(rec.lat) + ";" + str(rec.lon) + ";" + str(rec.maxroadspeed) + ";"  
                        
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
                            "merge_start": merge_start,
                        }

                        # try:
                        #     with open(jsonfilename, "w") as j:
                        #         json.dump(jsondata, j, indent=4)
                        # except:
                        #     pass
                    
                    frame = rec.frames.popleft()
                    fh,fw,fc = frame.shape
                    # frame = self.drawLabels(1,frame,rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                    #                             rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                    #                             rec.segment,rec.road,rec.deviationcode)
                    if self.side == "CABIN":
                        frame = self.drawLabels(1,frame,  
                                                    (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                    rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                    rec.segment,rec.road,rec.deviationcode,
                                                    rec.earright,rec.earleft,rec.mar,
                                                    rec.pitch,rec.yaw,rec.masked,rec.glasses)
                                                    )
                    elif self.side == "FRONT":
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

                        if isDeviationThumbnail:
                            if self.side == "CABIN":
                                rec.deviationthumbnail = self.drawLabels(1,rec.deviationthumbnail,  
                                                            (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                            rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                            rec.segment,rec.road,rec.deviationcode,
                                                            rec.earright,rec.earleft,rec.mar,
                                                            rec.pitch,rec.yaw,rec.masked,rec.glasses)
                                                            )
                            elif self.side == "FRONT":
                                rec.deviationthumbnail = self.drawLabels(1,rec.deviationthumbnail,  
                                                        (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                        rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                        rec.segment,rec.road,rec.deviationcode)
                                                        )
                                
                            writer.write(rec.deviationthumbnail)
                            cv2.imwrite(thumbfilename1, rec.deviationthumbnail)
                            cv2.imwrite(thumbfilename2, rec.deviationthumbnail)
                        else:
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
                    fh,fw,fc = frame.shape
                    if fh==h and fw==w:
                        # frame = self.drawLabels(0,frame,rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                        #                         rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                        #                         rec.segment,rec.road,rec.deviationcode)
                        if self.side == "CABIN":
                            frame = self.drawLabels(0,frame, 
                                                    (rec.deviationid,rec.timestamp,rec.deviceid,rec.speed,
                                                    rec.maxroadspeed,rec.rpm,rec.gear,rec.lat,rec.lon,
                                                    rec.segment,rec.road,rec.deviationcode,
                                                    rec.earright,rec.earleft,rec.mar,
                                                    rec.pitch,rec.yaw,rec.masked,rec.glasses)
                                                    )
                        elif self.side == "FRONT":
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
                    merge_end = int(datetime.datetime.now().timestamp() * 1000)

                    jsondata["merge_end"] = merge_end
                    try:
                        with open(jsonfilename, "w") as j:
                            json.dump(jsondata, j, indent=4)
                    except:
                        pass

                    self.udp.sendto(bytes( udpdevmessage , "utf-8"), (self.udpserverip, self.udpserverport))

                print(">>>>>>>>RECORDING END:", rec.deviationid)

    def stop(self,mode):
        self.flag.append(mode)
