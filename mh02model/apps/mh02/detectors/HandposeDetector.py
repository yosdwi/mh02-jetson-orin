import cv2
import math
import numpy as np
import json


class HandposeDetector:

    class HandsResult:
        def __init__(self,posefaceroi,frameshape,handleftlmk,handrightlmk):
            self.frameshape = frameshape
            self.frameheight, self.framewidth, _ = frameshape
            self.posefaceroi = posefaceroi
            self.roixmin,self.roiymin, self.roixmax, self.roiymax = posefaceroi
            
            self.resetPoints(handleftlmk,handrightlmk)
            self.extractAllPoints()
            self.getSelectedPoints()
            
        def resetPoints(self,handleftlmk,handrightlmk):
            self.handleftlmk = handleftlmk
            self.handrightlmk = handrightlmk
            self.wrist = [None,None]
            self.thumb_tip = [None,None]
            self.index_finger_tip = [None,None]
            self.middle_finger_tip = [None,None]
            self.ring_finger_tip = [None,None]
            self.pinky_tip = [None,None]

            self.thumb_tip_0 = [None,None]
            self.index_finger_tip_0 = [None,None]
            self.middle_finger_tip_0 = [None,None]
            self.ring_finger_tip_0 = [None,None]
            self.pinky_tip_0 = [None,None]

        def extractPoint(self,point):
            x = int(point.x * (self.roixmax - self.roixmin)) + self.roixmin
            y = int(point.y * (self.roiymax - self.roiymin)) + self.roiymin
            return x,y

        def extractAllPoints(self):
            lmks = []
            if len(self.handleftlmk)>0:
                for i in range(21):
                    lmks.append(self.extractPoint(self.handleftlmk[i]))
            self.handleftlmk = lmks
            lmks = []
            if len(self.handrightlmk)>0:
                for i in range(21):
                    lmks.append(self.extractPoint(self.handrightlmk[i]))
            self.handrightlmk = lmks
                
            # print("LEFT LMKS:", self.handleftlmk, "RIGHT LMKS:", self.handrightlmk)

        def getSelectedPoints(self):
            
            if len(self.handrightlmk)>0:
                self.wrist[0] = self.handrightlmk[0]
                self.thumb_tip[0] = self.handrightlmk[4]
                self.index_finger_tip[0] = self.handrightlmk[8]
                self.middle_finger_tip[0] = self.handrightlmk[12]
                self.ring_finger_tip[0] = self.handrightlmk[16]
                self.pinky_tip[0] = self.handrightlmk[20]

                self.thumb_tip_0[0] = self.handrightlmk[2]
                self.index_finger_tip_0[0] = self.handrightlmk[6]
                self.middle_finger_tip_0[0] = self.handrightlmk[10]
                self.ring_finger_tip_0[0] = self.handrightlmk[14]
                self.pinky_tip_0[0] = self.handrightlmk[18]
            
            if len(self.handleftlmk)>0:
                self.wrist[1] = self.handleftlmk[0]
                self.thumb_tip[1] = self.handleftlmk[4]
                self.index_finger_tip[1] = self.handleftlmk[8]
                self.middle_finger_tip[1] = self.handleftlmk[12]
                self.ring_finger_tip[1] = self.handleftlmk[16]
                self.pinky_tip[1] = self.handleftlmk[20]

                self.thumb_tip_0[1] = self.handleftlmk[2]
                self.index_finger_tip_0[1] = self.handleftlmk[6]
                self.middle_finger_tip_0[1] = self.handleftlmk[10]
                self.ring_finger_tip_0[1] = self.handleftlmk[14]
                self.pinky_tip_0[1] = self.handleftlmk[18]


    def __init__(self,mp):
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        self.hands = self.mp_hands.Hands(
            static_image_mode = False,
            max_num_hands=2,
            min_detection_confidence=0.5
        )

    def reset(self):
        self.posefaceroi = None
        self.handsdetected = False
        self.handleftdetected = False
        self.handrightdetected = False
        self.handleftlmk = []
        self.handrightlmk = []
        self.results = None
        self.handslmk = None

    def draw(self,frame):
        if self.results is None:
            return frame

        # if self.results.multi_hand_landmarks is None:
        #     return frame

        # for hand_landmarks in self.results.multi_hand_landmarks:
        #     self.mp_drawing.draw_landmarks(
        #         frame,
        #         hand_landmarks,
        #         self.mp_hands.HAND_CONNECTIONS,
        #         self.mp_drawing_styles.get_default_hand_landmarks_style(),
        #         self.mp_drawing_styles.get_default_hand_connections_style()
        #     )

        if self.handslmk is None:
            return frame

        for p in self.handslmk.handleftlmk:
            cv2.circle(frame, p, int(2), (255,0,255), 2, cv2.LINE_AA)

        for p in self.handslmk.handrightlmk:
            cv2.circle(frame, p, int(2), (255,0,255), 2, cv2.LINE_AA)

        return frame

    def getHandPoints(self,frame):
        for hand_no, hand_landmarks in enumerate(self.results.multi_hand_landmarks):
            if "Left" in str(self.results.multi_handedness[hand_no]):
                self.handrightlmk = hand_landmarks.landmark
            elif "Right" in str(self.results.multi_handedness[hand_no]):
                self.handleftlmk = hand_landmarks.landmark
        
        self.handslmk = HandposeDetector.HandsResult(self.posefaceroi,frame.shape,self.handleftlmk,self.handrightlmk)

    def preprocess(self,frameposeroi,posefaceroi):
        self.posefaceroi = posefaceroi
        self.results = self.hands.process(frameposeroi)
        self.handsdetected = (not self.results.multi_hand_landmarks is None)
        # roixmin, roiymin, roixmax, roiymax = posefaceroi

    def process(self,frame,frameposeroi,posefaceroi):
        self.preprocess(frameposeroi,posefaceroi)
        if self.handsdetected:
            self.postprocess(frame)

    def postprocess(self,frame):
        if self.results is None:
            return
        
        if self.results.multi_hand_landmarks is None:
            return

        self.handsdetected = True
        # print('Handedness:', self.results.multi_handedness)
        for item in self.results.multi_handedness:
            # print(item)
            if "Right" in str(item):
                self.handleftdetected = True
            if "Left" in str(item):
                self.handrightdetected = True
        
        self.getHandPoints(frame)
        # print("Hand Result:", self.handslmk.wrist, "Shape:", self.handslmk.frameheight, self.handslmk.framewidth, self.handslmk.roixmin, self.handslmk.roiymin)

    def getresults(self):
        handsresults = self.handleftdetected,self.handrightdetected,self.handslmk
        if not self.handslmk is None:
            print("HAND LMKS Wrist:", self.handslmk.wrist)
        return self.handsdetected, handsresults

    def detect(self,frame,frameposeroi,posefaceroi):
        self.reset()

        if frame is None:
            return self.getresults() 

        self.process(frame,frameposeroi,posefaceroi)

        return self.getresults()