import cv2
import math
import numpy as np
import traceback
from detectors.SeatBeltDetector import *

class PoseDetector:

    def __init__(self,mp, posefaceroi):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(  static_image_mode=False, 
                                        min_detection_confidence=0.3,
                                        min_tracking_confidence=0.3)
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        self.posefaceroi = posefaceroi

    def validateFaceROI(self):
        incounter = 0
        rearx, reary = self.rightear
        learx, leary = self.leftear
        roixmin, roiymin, roixmax, roiymax = self.posefaceroi

        if rearx >= roixmin and rearx <= roixmax:
            incounter += 1
        
        if reary >= roiymin and reary <= roiymax:
            incounter += 1
        
        if learx >= roixmin and learx <= roixmax:
            incounter += 1
        
        if leary >= roiymin and leary <= roiymax:
            incounter += 1

        result = (int(incounter) == 4)
        return result

    def draw3d(self, frame):
        try:
            self.mp_drawing.draw_landmarks(
                    frame,
                    self.results.pose_landmarks,
                    self.mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=self.mp_drawing_styles.get_default_pose_landmarks_style())
        except Exception as ex:
            print("***WARNING*** Error in drawing 3D pose. Reaseon:", ex)
            print(traceback.format_exc())
        
        return frame

    def drawpoints(self, frame):
        
        if not self.posefaceroi is None:
            fxmin,fymin,fxmax,fymax = self.posefaceroi
            frame = cv2.rectangle(frame, (fxmin,fymin), (fxmax,fymax), (255,255,255), 1)

        try:
            if self.poselmk is None:
                return frame

            for item in self.poselmk:
                label,x,y = item
                frame = cv2.circle(frame, (x,y), int(1), (255,0,255), 2, cv2.LINE_AA)
        except Exception as ex:
            print("***WARNING*** Error in drawing 2D pose. Reaseon:", ex)
            print(traceback.format_exc())
        
        return frame

    def draw(self, frame):
        frame = self.drawpoints(frame)
        # frame = self.draw3d(frame)
        # frame = self.drawseatbelt(frame)
        return frame

    def update(self, posefaceroi):
        self.posefaceroi = posefaceroi

    def reset(self):
        self.results = None
        self.poselmk = None
        self.leftshoulder = None
        self.rightshoulder = None
        self.rightear = None
        self.leftear = None
        
    def preprocess(self):
        pass

    def postprocess(self,frame):
        h,w,c = frame.shape

        # for item in self.mp_pose.PoseLandmark:
        #     print("POSE ITEM:", item)

        if self.results.pose_landmarks:
            self.poselmk = []
            nose = self.results.pose_landmarks.landmark[self.mp_pose.PoseLandmark.NOSE]
            nose.x = int(nose.x * w)
            nose.y = int(nose.y * h)
            self.poselmk.append(("NOSE",int(nose.x),int(nose.y)))

            shoulder = self.results.pose_landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
            shoulder.x = int(shoulder.x * w)
            shoulder.y = int(shoulder.y * h)
            self.poselmk.append(("LEFT_SHOULDER",int(shoulder.x),int(shoulder.y)))
            self.leftshoulder = (int(shoulder.x),int(shoulder.y))
            
            shoulder = self.results.pose_landmarks.landmark[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
            shoulder.x = int(shoulder.x * w)
            shoulder.y = int(shoulder.y * h)
            self.poselmk.append(("RIGHT_SHOULDER",int(shoulder.x),int(shoulder.y)))
            self.rightshoulder = (int(shoulder.x),int(shoulder.y))

            rightear = self.results.pose_landmarks.landmark[self.mp_pose.PoseLandmark.RIGHT_EAR]
            rightear.x = int(rightear.x * w)
            rightear.y = int(rightear.y * h)
            self.rightear = (int(rightear.x),int(rightear.y))
            self.poselmk.append(("RIGHT_EAR",int(rightear.x),int(rightear.y)))

            leftear = self.results.pose_landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_EAR]
            leftear.x = int(leftear.x * w)
            leftear.y = int(leftear.y * h)
            self.leftear = (int(leftear.x),int(leftear.y))
            self.poselmk.append(("LEFT_EAR",int(leftear.x),int(leftear.y)))
            
            # Validate
            if not self.validateFaceROI():
                self.reset()

    def process(self,frame):
        self.preprocess()
        self.results = self.pose.process(frame)
        self.postprocess(frame)

    def getresults(self):
        return self.poselmk

    def detect(self,frame):
        self.reset()
        if frame is None:
            return self.getresults() 

        self.process(frame)

        return self.getresults()