import cv2
import math
import numpy as np
import time

class PhoningDetector:

    def __init__(self,phoningparams):
        self.reset()
        self.update(phoningparams)

    def update(self,phoningparams):
        self.mouthroiratio = float(phoningparams[0])
        self.phoningpointsthreshold = int(phoningparams[1])
        self.phoningvalidationthreshold = int(phoningparams[2])
        
    def reset(self):
        self.mouth = False
        self.mouthroi = None
        self.isphoning = False
        self.face_upper,self.face_lower,self.face_left,self.face_right,self.face_middle = None, None, None, None, None
        self.left_roi = None
        self.right_roi = None
        self.handleftdetected,self.handrightdetected,self.handslmk = None, None, None
        self.pointsinroi = 0
        self.handsinroi = None

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

    def createPhoneROI(self):
        self.createMouthROI()
        (mtxmin,mtymin),(mtxmax,mtymax) = self.mouthroi

        faceside = "CENTER"

        xu,yu = self.face_upper
        xr,yr = self.face_right
        xl,yl = self.face_left

        h = yr - yu
        wr = xu - xr
        wl = xl - xu

        if wr>=wl:
            faceside = "TO_LEFT"
            wl=wr
        else:
            faceside = "TO_RIGHT"
            wr=wl

        xrmin = xr - int(wr*0.5) 
        xrmax = xr
        
        xlmin = xl
        xlmax = xl + int(wl*0.5)

        if faceside == "TO_LEFT":
            xrmax = xr + int(wr*0.8)
            xlmax = xl + int(wl*0.8)
        elif faceside == "TO_RIGHT":
            xlmin = xl - int(wl*0.8)
            xrmin = xr - int(wr*0.8) 

        # Make sure Phone ROIs do not interference Mouth ROI
        if xrmax > mtxmin:
            xrmax = mtxmin - 2
        if xlmin < mtxmax:
            xlmin = mtxmax + 2

        yrmin = yr - int(h*0.5)
        yrmax = yr + int(h*1.4)
        self.right_roi = (xrmin,yrmin),(xrmax,yrmax)

        
        ylmin = yl - int(h*0.5)
        ylmax = yl + int(h*1.4)
        self.left_roi = (xlmin,ylmin),(xlmax,ylmax)

    def checkPointinROI(self,point,roi):
        (mxmin,mymin),(mxmax,mymax) = roi
        px,py = point
        if px >= mxmin and px <= mxmax and py >= mymin and py <= mymax:
            return True
        else:
            return False

    def checkHandsinROI(self):
        self.pointsinroi = 0
        leftpointsinroi = 0
        rightpointsinroi = 0

        lefthand = self.handslmk.handleftlmk
        righthand = self.handslmk.handrightlmk

        if self.handleftdetected:
            for point in lefthand:
                if self.checkPointinROI(point,self.left_roi):
                    leftpointsinroi = leftpointsinroi + 1
                    if self.handsinroi is None:
                        self.handsinroi = 1
            
        if self.handrightdetected:
            for point in righthand:
                if self.checkPointinROI(point,self.right_roi):
                    rightpointsinroi = rightpointsinroi + 1
                    if self.handsinroi is None:
                        self.handsinroi = 2
        
        print("PHONING HANDS IN ROI:", self.handsinroi)
        print("PHONING TOTAL Points inside ROI","L:", leftpointsinroi, "R:", rightpointsinroi, "Thres:", self.phoningpointsthreshold)
        self.pointsinroi = leftpointsinroi + rightpointsinroi

    def checkSelectedPointsROI(self):
        if self.handsinroi is None:
            return False
        
        validatepoints = 0
        handindex = 0
        tx, ty, ix, iy, mx, my, rx, ry, px, py = None, None, None, None, None, None, None, None, None, None

        if self.handsinroi == 1: # Left hand in ROI
            handindex = 1

        elif self.handsinroi == 2: # Right hand in ROI
            handindex = 0

        tx, ty = self.handslmk.thumb_tip_0[handindex]
        ix, iy = self.handslmk.index_finger_tip_0[handindex]
        mx, my = self.handslmk.middle_finger_tip_0[handindex]
        rx, ry = self.handslmk.ring_finger_tip_0[handindex]
        px, py = self.handslmk.pinky_tip_0[handindex]
            
        if (py>ry):
            validatepoints = validatepoints + 1
        if (ty>iy):
            validatepoints = validatepoints + 1
        if (iy>my):
            validatepoints = validatepoints + 1
        if (ry>my):
            validatepoints = validatepoints + 1
        if (ty>py) and (ty>ry) and (ty>my) and (ty>iy):
            validatepoints = validatepoints + 5

        # print("FINGERS INDEX:",handindex,ty,iy,my,ry,py)
        print("PHONING VALIDATE POINTS:",validatepoints, "Thres:", self.phoningvalidationthreshold)
        return (validatepoints>=self.phoningvalidationthreshold)

    def preprocess(self,face,mouth,handsresults):
        self.face_upper,self.face_lower,self.face_right,self.face_left,self.face_middle = face        
        self.mouth = mouth        
        self.handleftdetected,self.handrightdetected,self.handslmk = handsresults
        self.createPhoneROI()

    def postprocess(self):
        self.isphoning = ((self.pointsinroi>=self.phoningpointsthreshold) and self.checkSelectedPointsROI())
        
    def process(self,frame,face,mouth,handsresults):
        self.preprocess(face,mouth,handsresults)
        self.checkHandsinROI()
        self.postprocess()

    def getresult(self):
        return self.isphoning

    def draw(self,frame):
        # Draw Left ROI
        if not self.left_roi is None:
            lmin,lmax = self.left_roi
            if self.handsinroi==1:
                frame = cv2.rectangle(frame,lmin,lmax,(0,255,0),2)
            else:
                frame = cv2.rectangle(frame,lmin,lmax,(0,0,0),2)

        # Draw Right ROI
        if not self.right_roi is None:
            rmin,rmax = self.right_roi
            if self.handsinroi==2:
                frame = cv2.rectangle(frame,rmin,rmax,(0,255,0),2)
            else:
                frame = cv2.rectangle(frame,rmin,rmax,(0,0,0),2)

        return frame


    def detect(self,frame,face,mouth,handsresults):
        self.process(frame,face,mouth,handsresults)
        return self.getresult()