import cv2
import numpy as np
import math

class PupilDetector:

    def __init__(self):
        self.scaling_factor = 0.7
        self.reset()
        pass

    def reset(self):
        self.pupilcounter = 0
        self.ispupildetected = False
        self.righteyeimg = None
        self.lefteyeimg = None
        self.eyeimgs = []

    def preprocess(self, eyeimg):
        img = cv2.resize(eyeimg.copy(), None,   fx=self.scaling_factor, 
                                                fy=self.scaling_factor, 
                                                interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return gray
    

    def process(self,eyeimg):
        gray = cv2.cvtColor(eyeimg, cv2.COLOR_BGR2GRAY)
        circles = cv2.HoughCircles( gray,cv2.HOUGH_GRADIENT, dp = 1,minDist = 5,
		                            param1=130,param2=10,minRadius=1,maxRadius=-1)
        # circles = cv2.HoughCircles( gray,cv2.HOUGH_GRADIENT, dp = 1,minDist = 5,
		#                             param1=250,param2=10,minRadius=1,maxRadius=-1)
        
        try:
            self.pupilcounter = self.pupilcounter + len(circles[0])
        except:
            pass

        # if circles is not None:
        #     self.pupilcounter += 1

        print("PUPILS CIRCLE:", circles, "Acc. Count:", self.pupilcounter )

    def getresults(self):
        self.ispupildetected = (self.pupilcounter >=0 and self.pupilcounter <= 7)
        return self.ispupildetected

    def detect(self,frame,righteyeimg,lefteyeimg):
        self.reset()
        if righteyeimg is None or lefteyeimg is None:
            return self.getresults()
        
        self.eyeimgs.append(righteyeimg)
        self.eyeimgs.append(lefteyeimg)

        for eyeimg in self.eyeimgs:
            self.process(eyeimg)

        return self.getresults()









