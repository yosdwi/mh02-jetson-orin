# Update History
# Version 6.2
# 2024-06-03    JRP     Happy 21st years in PAMA ;)
#                       (1) Split Fatigue Detection and Behavior Detection
#                           to improve system performance.
#                       (2) Implement 0 kmph detection and alert mode.

import cv2
import math
import numpy as np

class SeatBelt:

    # def __init__(self, shoulder, adjx, adjy, width, height, anglemin, anglemax):
    def __init__(self, adjx, adjy, width, height, anglemin, anglemax):
        
        self.adjx = adjx
        self.adjy = adjy
        self.width = width
        self.height = height

        # Seatbelt Detector's Parameters
        self.seatbeltlines = []
        # self.seatbeltlinesleft = []

        
        self.anglemin = anglemin
        self.anglemax = anglemax
        self.rho = 1  # distance resolution in pixels of the Hough grid
        self.theta = np.pi / 180  # angular resolution in radians of the Hough grid
        self.threshold = 35  # minimum number of votes (intersections in Hough grid cell)
        self.min_line_length = 50  # minimum number of pixels making up a line
        self.max_line_gap = 10  # maximum gap in pixels between connectable line segments

        self.seatbeltcounter = 0
        self.seatbeltcountermin = 1

    def reset(self):
        self.seatbeltlines = []
        self.seatbeltlinesleft = []

        self.seatbeltcounter = 0
        

    def draw(self, frame):
        if frame is None:
            return frame

        # try:
        #     frame = cv2.rectangle(frame, (self.lxmin,self.lymin), (self.lxmax,self.lymax), (41, 41, 41),1)
        #     for item in self.seatbeltlinesleft:
        #         angle = item[2]
        #         xmin,ymin = item[0]
        #         xmax,ymax = item[1]
                
        #         frame = cv2.circle(frame, (xmin,ymin), int(1), (255,0,255), 2, cv2.LINE_AA)
        #         frame = cv2.circle(frame, (xmax,ymax), int(1), (0,255,255), 2, cv2.LINE_AA)

        #         # posmin = (xmin + self.shoulderx, ymin+self.shouldery)
        #         # posmax = (xmax + self.shoulderx, ymax+self.shouldery)
        #         print("Check line",(xmin,ymin)," ",(xmax,ymax), " ", angle)
        #         cv2.line(frame,(xmin,ymin),(xmax,ymax),(255,255,0),5)
        # except:
        #     print("An exception occurred")

        if self.seatbeltcounter < 1:
            return frame

        frame = cv2.rectangle(frame, (self.xmin,self.ymin), (self.xmax,self.ymax), (41, 41, 41),1)
     
        
        for item in self.seatbeltlines:
            angle = item[2]
            xmin,ymin = item[0]
            xmax,ymax = item[1]
            posmin = (xmin + self.shoulderx, ymin+self.shouldery)
            posmax = (xmax + self.shoulderx, ymax+self.shouldery)
            cv2.line(frame,posmin,posmax,(255,255,0),5)

        return frame
    
    def setseatbeltarea(self,shoulder,side):
        self.side = side

        if shoulder is None:
            shoulder = [0,0]

        self.shoulderx = shoulder[0]
        self.shouldery = shoulder[1]
        # Seatbelt ROI

        if self.side == "R":

            self.xmin, self.ymin = (int(shoulder[0])-self.adjx), (int(shoulder[1])-self.adjy)

            if self.xmin < 0:
                self.xmin = 0

            if self.ymin < 0:
                self.ymin = 0

            self.xmax = self.xmin + self.width
            self.ymax = self.ymin + self.height
        else:
            self.xmax = self.shoulderx + self.adjx
            self.ymin = self.shouldery - self.adjy
            self.xmin = self.xmax - self.width
            self.ymax = self.ymin + self.height

            self.lxmax = self.xmax
            self.lymax = self.ymax
            self.lxmin = self.xmin
            self.lymin = self.ymin
            print("seatbelt left : ",self.xmin ," ",self.ymin," ",self.xmax," ",self.ymax," - ",self.shoulderx," ",self.shouldery)


    def detect(self,shoulder,side,frame):

        if shoulder is None:
            return False

        print("shoulder : ",shoulder)
        self.setseatbeltarea(shoulder,side)

        if frame is None:
            return False
        
        cp_frame = frame.copy()
        crop_img = cp_frame[self.ymin:self.ymax, self.xmin:self.xmax]

        if crop_img is None:
            return False

        ch,cw,cc = crop_img.shape

        if ch < 1 or cw < 1:
            return False

        gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray,100,150,apertureSize = 3)
        lines = cv2.HoughLinesP(edges, self.rho, self.theta, self.threshold, np.array([]),
                                self.min_line_length, self.max_line_gap)

        self.seatbeltcounter = 0

        if not lines is None:
            for line in lines:
                for x1,y1,x2,y2 in line:
                    deltaY = y2-y1
                    deltaX = x2-x1
                    angle = math.atan2(deltaY,deltaX) * 180 / math.pi
                    print("ANGLE:",angle, (x1,y1),(x2,y2))
                    
                    # if angle < 0:
                    #     # 239,69 242,130
                    #     # 239,130 242,69
                    #     self.seatbeltlinesleft.append(((x1,y2),(x2,y1),angle))
                    
                    # cv2.line(crop_img,(x1,y1),(x2,y2),(255,0,0),5)
                    
                    if (y1<y2):
                        seatbeltheight = y2-y1
                    else:
                        seatbeltheight = y1-y2

                    # print("angle : ",angle, " " ,seatbeltheight)
                    if self.side == "R" and angle > self.anglemin and angle < self.anglemax and seatbeltheight>=30:
                        self.seatbeltcounter += 1
                        self.seatbeltlines.append(((x1,y1),(x2,y2),angle))
                        # cv2.line(crop_img,(x1,y1),(x2,y2),(255,0,0),5)
                        # cv2.line(frame,(x1,y1),(x2,y2),(255,0,0),5)
                        print((x1,y1),(x2,y2),angle)

                    if self.side == "L" and (angle * -1) > self.anglemin and (angle * -1) < self.anglemax and seatbeltheight>=30:
                        self.seatbeltcounter += 1
                        self.seatbeltlines.append(((x1,y1),(x2,y2),angle))
                    
                    if self.seatbeltcounter >= self.seatbeltcountermin:
                        break

                if self.seatbeltcounter >= self.seatbeltcountermin:
                    break

        
        # cv2.imshow("Seat Belt", crop_img)
        print("Seatbelts:", self.seatbeltcounter)
        return (self.seatbeltcounter > 0)
