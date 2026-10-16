import cv2
import math
import numpy as np
import time

class SmokingDetector:

    def __init__(self, smokingparams):
        self.update(smokingparams)
        self.reset()

    def update(self, smokingparams):
        mouthroiratio, smokingpointsthreshold, closedpointthreshold = float(smokingparams[0]),int(smokingparams[1]),int(smokingparams[2])
        self.mouthroiratio = mouthroiratio
        self.smokingpointsthreshold = smokingpointsthreshold
        self.closedpointthreshold = closedpointthreshold

    def reset(self):
        self.mouthframe = None
        self.mouth = None
        self.mouthroi = None
        self.pointsinroi = 0
        self.handsinroi = None
        self.selectedpointsvalid = False #selected hand points for validation
        self.shouldersline = None

        self.handleftdetected,self.handrightdetected,self.handslmk = False, False, None
        self.lefthand = None
        self.righthand = None
        self.poselmk = None
        self.leftshoulder, self.rightshoulder = None, None

        self.issmoking = False
        self.ismouthclosed = False

    def draw(self,frame):
        if self.mouthroi is None:
            return frame

        m_start, m_end = self.mouthroi

        # Draw mouth box
        if self.issmoking:
            frame = cv2.rectangle(frame,m_start,m_end,(0,255,0),1)
        else:
            frame = cv2.rectangle(frame,m_start,m_end,(0,0,0),1)

        # Draw shoulder line
        # frame = cv2.line(frame, self.leftshoulder, self.rightshoulder, (0,255,0),4)
        return frame
    
    def createMouthROI(self):
        m_upper,m_lower,m_left,m_right = self.mouth # (791, 372) (791, 372) (765, 373) (804, 379)
        mxmin, _ = m_left
        mxmax, _ = m_right
        mwidth = int(mxmax - mxmin)

        xratio = ((self.mouthroiratio-1)/2)
        xadj = int(mwidth * xratio)
        mxmin = mxmin - xadj
        mxmax = mxmax + xadj
        mwidth = int(mxmax - mxmin)
        
        # print("MOUTH:", (mxmax - mxmin), mwidth, xadj,self.mouthroiratio,(self.mouthroiratio-1))
        _, mymin = m_upper
        _, mymax = m_lower

        mymin = mymin - int(mwidth * 0.3)
        mymax = mymax + int(mwidth * 0.3)
        self.mouthroi = (mxmin,mymin),(mxmax,mymax)

    def checkIfInMouthROI(self,point):
        (mxmin,mymin),(mxmax,mymax) = self.mouthroi
        px,py = point
        if px >= mxmin and px <= mxmax and py >= mymin and py <= mymax:
            return True
        else:
            return False

    def getShoulders(self):
        # Get shoulders for checking Wrist Ratio

        if self.poselmk is None:
            self.poselmk = [0,0]

        for p in self.poselmk:
            if p[0]=='LEFT_SHOULDER':
                self.leftshoulder = (p[1],p[2])
            elif p[0]=='RIGHT_SHOULDER':
                self.rightshoulder = (p[1],p[2])

    def countWristDistanceRatio(self):
        wrist_distance_ratio = 0
        wy,hy,lwx,lwy,rwx,rwy = None,None,None,None,None,None
        leftwrist, rightwrist = self.handslmk.wrist[0],self.handslmk.wrist[1]
        if not leftwrist is None:
            lwx,lwy = leftwrist
        if not rightwrist is None:
            rwx,rwy = rightwrist

        if (not lwy is None) and (not rwy is None):
            if lwy<=rwy:
                wy = lwy
            else:
                wy = rwy
        elif (not lwy is None) and (rwy is None):
            wy = lwy
        elif (lwy is None) and (not rwy is None):
            wy = rwy
        else:
            return wrist_distance_ratio

        lx,ly = self.leftshoulder
        rx,ry = self.rightshoulder
        if ly<=ry:
            hy = ly
        elif ry<ly:
            hy = ry
        
        if wy>=hy:
            wrist_distance = 0
        else:
            wrist_distance = hy - wy

        shoulder_distance = lx - rx
        wrist_distance_ratio = wrist_distance/shoulder_distance
        return wrist_distance_ratio

    def preprocess(self,frame,mouth,handsresults):

        self.getShoulders()

        self.mouthframe = frame.copy()
        self.mouth = mouth
        self.createMouthROI()
        
        self.handleftdetected,self.handrightdetected,self.handslmk = handsresults

        # m_upper,m_lower,m_left,m_right = self.facelandmark.mouth
        # handsresults.handleftlmk = handleftlmk
        # handsresults.handrightlmk = handrightlmk
        # handsresults.wrist = [None,None]
        # handsresults.thumb_tip = [None,None]
        # handsresults.index_finger_tip = [None,None]
        # handsresults.middle_finger_tip = [None,None]
        # handsresults.ring_finger_tip = [None,None]
        # handsresults.pinky_tip = [None,None]
        self.lefthand = self.handslmk.handleftlmk
        self.righthand = self.handslmk.handrightlmk

    def countPointsROI(self):
        self.pointsinroi = 0
        leftpointsinroi = 0
        rightpointsinroi = 0

        if self.handleftdetected:
            for point in self.lefthand:
                if self.checkIfInMouthROI(point):
                    leftpointsinroi = leftpointsinroi + 1
                    if self.handsinroi is None:
                        self.handsinroi = 1
            
        if self.handrightdetected:
            for point in self.righthand:
                if self.checkIfInMouthROI(point):
                    rightpointsinroi = rightpointsinroi + 1
                    if self.handsinroi is None:
                        self.handsinroi = 2

        # print("HANDS IN ROI:", self.handsinroi)
        # print("TOTAL Points inside ROI","L:", leftpointsinroi, "R:", rightpointsinroi)
        self.pointsinroi = leftpointsinroi + rightpointsinroi

    def checkSelectedPointsROI(self):
        if self.handsinroi is None:
            return False
        validatepoints = 0

        if self.handsinroi == 1: # Left hand in ROI
            tx, ty = self.handslmk.thumb_tip[1]
            ix, iy = self.handslmk.index_finger_tip[1]
            mx, my = self.handslmk.middle_finger_tip[1]
            px, py = self.handslmk.pinky_tip[1]
            if (iy<ty) and (my<ty):
                validatepoints = validatepoints + 1
            if (iy<py) and (my<py):
                validatepoints = validatepoints + 1

        elif self.handsinroi == 2: # Right hand in ROI
            tx, ty = self.handslmk.thumb_tip[0]
            ix, iy = self.handslmk.index_finger_tip[0]
            mx, my = self.handslmk.middle_finger_tip[0]
            px, py = self.handslmk.pinky_tip[0]
            if (iy<ty) and (my<ty):
                validatepoints = validatepoints + 1
            if (iy<py) and (my<py):
                validatepoints = validatepoints + 1

        return (validatepoints>0)
    
    def checkSelectedPointsPosition(self):
        if self.handsinroi is None:
            return False
        
        (mxmin,mymin),(mxmax,mymax) = self.mouthroi
        validatepoints = 0

        if self.handsinroi == 1: # Left hand in ROI
            ix, iy = self.handslmk.index_finger_tip[1]
            mx, my = self.handslmk.middle_finger_tip[1]
        elif self.handsinroi == 2: # Right hand in ROI
            ix, iy = self.handslmk.index_finger_tip[0]
            mx, my = self.handslmk.middle_finger_tip[0]

        # Check if fingers in Mouth ROI

        indexfingerinroi = self.checkIfInMouthROI((ix, iy))
        middlefingerinroi = self.checkIfInMouthROI((mx, my))

        if indexfingerinroi or middlefingerinroi:
            return True

        if (ix >= mxmin) and (ix <= mxmax):
            validatepoints = validatepoints + 1

        if (mx >= mxmin) and (mx <= mxmax):
            validatepoints = validatepoints + 1

        return (validatepoints>0)

    def postprocess(self):
        # print("SELECTED POINTS in ROI:",self.checkSelectedPointsROI())
        self.issmoking = ((self.pointsinroi>=self.smokingpointsthreshold) and self.checkSelectedPointsROI() and self.checkSelectedPointsPosition())
        self.ismouthclosed = (self.pointsinroi>=self.closedpointthreshold)

        if self.ismouthclosed:
            wristdistanceratio = self.countWristDistanceRatio()

    def process(self,frame,mouth,handsresults):
        self.preprocess(frame,mouth,handsresults)

        self.countPointsROI()

        self.postprocess()
        return

    def getresult(self):
        return self.issmoking, self.ismouthclosed, self.pointsinroi

    def detect(self, frame, mouth, handsresults, poselmk):
        self.poselmk = poselmk
        self.process(frame, mouth, handsresults)

        return self.getresult()

    