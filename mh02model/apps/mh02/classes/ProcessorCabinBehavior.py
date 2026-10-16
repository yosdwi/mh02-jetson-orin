# Update History
# Version 6.2
# 2024-06-18    JRP     Happy 21st years in PAMA ;)
#                       (1) Split Fatigue Detection and Behavior Detection
#                           to improve system performance.
#                       (2) Implement 0 kmph detection and alert mode.


import collections
import os
import time
import copy
import mediapipe as mp
import datetime
import traceback
import gc
from classes.Config import *
# from detectors.PoseDetector import *
# from detectors.SeatBeltDetector import *
# from detectors.SimpleFaceDetector import *
# from detectors.FaceLandmarkDetector import *
from detectors.FaceMaskDetector import *
# from detectors.EyeGlassDetector import *
# from detectors.PupilDetector import *
# from detectors.HandposeDetector import *
# from detectors.SmokingDetector import *
# from detectors.PhoningDetector import *

class ProcessorCabinBehavior:
    def __init__(self, path):

        # os.environ["TF_ENABLE_ONEDNN_OPTS"] = "1"
        # os.environ["OMP_NUM_THREADS"] = "4" # Limit to 200% (or 20% CPU)
        # tf.config.threading.set_inter_op_parallelism_threads(1) 
        # tf.config.threading.set_intra_op_parallelism_threads(1)        
    
        # Initiate config reader
        self.config = Config(path)
        self.modelpath = str(self.config.getValue("MODEL_PATH"))

        self.lastconfigreload = time.time()
        self.maxconfigidletime = 3
        self.updateConfig(0)

        # Detectors
        # self.simpleface = SimpleFaceDetector(self.modelpath)
        # self.seatbeltdetector = SeatBelt(int(self.seatbeltparams[0]),int(self.seatbeltparams[1]),
        #                                  int(self.seatbeltparams[2]),int(self.seatbeltparams[3]),
        #                                  int(self.seatbeltparams[4]),int(self.seatbeltparams[5]))                                         
        # self.poselandmark = PoseDetector(mp,self.posefaceroi)
        # self.facelandmark = FaceLandmarkDetector(mp,copy.copy(self.facelmkparams))
        self.facemask = FaceMaskDetector(0.9,self.modelpath)
        # self.eyeglass = EyeGlassDetector()
        # self.pupils = PupilDetector()
        # self.hands = HandposeDetector(mp)
        # self.smoking = SmokingDetector(self.smokingparams) #(1.4,4,8)
        # self.phoning = PhoningDetector(self.phoningparams)

    def parseData(self,dataparsed):
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

    def updateConfig(self, mode):
        reloadparams = False

        if mode == 0: # Initial
            self.config.load()
            reloadparams = True
        elif int(time.time() - self.lastconfigreload)>=int(self.maxconfigidletime):
            self.config.load()
            reloadparams = True
            self.lastconfigreload = time.time()

            print("***********************************************CONFIG UPDATED")

        if reloadparams:
            self.cabinroi = str(self.config.getValue("CABIN_ROI")).split(",")
            # self.checkseatbelt = int(self.config.getValue("SEATBELT_ACTIVE"))
            self.checkfacemask = int(self.config.getValue("FACEMASK_ACTIVE"))
            # self.checkeyeglass = int(self.config.getValue("EYEGLASS_ACTIVE"))
            # self.seatbeltparams = str(self.config.getValue("SEATBELT_CONFIG")).split(",") 
            # self.facelmkparams = str(self.config.getValue("FACE_CONFIG"))
            self.facemaskparams = str(self.config.getValue("FACEMASK_CONFIG"))
            # self.smokingparams = str(self.config.getValue("SMOKING_CONFIG")).split(",")
            # self.phoningparams = str(self.config.getValue("PHONING_CONFIG")).split(",")

            # print("***********************************************CONFIG UPDATED 2",self.checkseatbelt)

            # roixmin, roiymin, 
            # roixmax, roiymax
            self.posefaceroi = (int(self.cabinroi[0]),int(self.cabinroi[1]),
                                int(self.cabinroi[2]),int(self.cabinroi[3]))
            
            if mode != 0:
                self.updateDetectors()
            
    def updateDetectors(self):
        # Update Detectors
        # self.poselandmark.update(self.posefaceroi)
        # self.facelandmark.update(self.facelmkparams)
        self.facemask.update(float(self.facemaskparams))
        # self.smoking.update(self.smokingparams)
        # self.phoning.update(self.phoningparams)

    def resetDetectors(self):
        # Avoid invalid values that affect to detector's draw function
        # This function will be visited in every cycle
        # self.seatbeltdetector.reset()
        # self.simpleface.reset()
        # self.poselandmark.reset()
        # self.facelandmark.reset()
        # self.eyeglass.reset()
        # self.pupils.reset()
        # self.hands.reset()
        # self.smoking.reset()
        # self.phoning.reset()
        self.facemask.reset()

    def cropPoseRoi(self, frame):
        if frame is None:
            return None

        h,w,c = frame.shape
        roixmin, roiymin, roixmax, roiymax = self.posefaceroi

        if roixmax > w:
            roixmax = w

        if roiymax > h:
            roiymax = h

        img = frame.copy()
        crop = img[roiymin:roiymax,roixmin:roixmax]
        return crop
    
    def clear_gpu_memory(self):
        tf.keras.backend.clear_session()

        try:
            physical_devices = tf.config.experimental.list_physical_devices('GPU')
            for device in physical_devices:
                tf.config.experimental.set_memory_growth(device,False)
                tf.config.experimental.VirtualDeviceConfiguration(memory_limit=0)                
        except Exception as ex:
            print("=============================== Error cleaning GPU:", ex)

        gc.collect()

    def process(self,systemmode,frame,dataparsed,detection_mode):
        self.clear_gpu_memory()
        # Update Necessary Parameters/ Configs
        self.updateConfig(1)
        self.resetDetectors()
        self.parseData(dataparsed)

        self.datetimes = datetime.datetime.now()
        self.current_time = self.datetimes.strftime('%H:%M:%S')

        # Local Variables
        deviations = []
        earleft,earright,mar,pitch,yaw,masked,glasses,pupils = -100,-100,-100,0,0,False,False,False
        facestat = (earleft,earright,mar,pitch,yaw,masked,glasses)
        # seatbeltstatus = False
        facemaskstatus = False
        # eyeglassstatus = False
        # handsdetected = False
        # issmoking, ismouthclosed, pointsinroi = False, False, 0
        # isphoning = False

        # Check System Mode
        # 1: Operational, 2: Testing/ Simulation, 3: Inactive Detection
        # Or Speed is < min speed and all detections are disabled when vehicle speed is < min speed.
        if int(systemmode)==3 or detection_mode == "DISABLE_WHEN_IDLE": 
            return frame, deviations, facestat

        # Frame for Detections
        frame.flags.writeable = False
        h,w,c = frame.shape

        drawingframe = frame.copy()

        mpframe = frame.copy()
        mpframe.flags.writeable = False
        # mpframe = cv2.cvtColor(mpframe, cv2.COLOR_BGR2RGB)

        # mpframeposeroi = self.cropPoseRoi(frame)
        # mpframeposeroi.flags.writeable = False
        # mpframeposeroi = cv2.cvtColor(mpframeposeroi, cv2.COLOR_BGR2RGB)

        # Human Detection
        # poselmk = self.poselandmark.detect(mpframe)
        # Pose detection results will be validated to Face ROI
        # If detected person outside of Pose ROI, it the result will be reset 

        # if poselmk == None:
        #     # if detection_mode == "MOVING":
        #     #     deviations.append("NOFACE")
        #     return frame, deviations, facestat
        # else:
        #     print("Human detected.")

        # if self.checkseatbelt == 1 and detection_mode == "MOVING":
        #     if str(self.seatbeltparams[6]) == "R":
        #         shoulder = self.poselandmark.rightshoulder
        #     else:
        #         shoulder = self.poselandmark.leftshoulder
                
        #     seatbeltstatus =  self.seatbeltdetector.detect(shoulder,str(self.seatbeltparams[6]),mpframe)

        #     if not seatbeltstatus:
        #         deviations.append("SEATBELT")

        # Face
        # self.validface = self.simpleface.detect(mpframe,self.posefaceroi)

        # try:
        #     print("ValidFace:", self.validface)
        #     cv2.imshow("Valid Face",self.validface)
        # except:
        #     pass

        # Facelandmark
        # self.facelmk = self.facelandmark.detect(mpframe,(h,w),self.posefaceroi)        
        # is_faceloss = self.facelmk.isfaceloss
        # is_headup,is_headdown = self.facelmk.isheadup,self.facelmk.isheaddown
        # is_headright,is_headleft = self.facelmk.isheadright,self.facelmk.isheadleft
        # is_closedeyes,is_yawning = self.facelmk.isclosedeye,self.facelmk.isyawning

        is_noface = True
        glasses = False
                
        # print("***FACE***",self.validface)

        if self.validface is not None:
            is_noface = False

            # print("***CHECKING MAR***")
            # try:
            #     earright, earleft = self.facelmk.ear
            #     mar = self.facelmk.mar
            #     pitch, yaw = self.facelmk.pitch,self.facelmk.yaw     
            #     print("***EAR***", self.facelmk.ear)       
            # except Exception as ex:
            #     print("***WARNING*** Error when parsing EAR/MAR/Pitch/Yaw. Reason:", ex)
            #     print(traceback.format_exc())
            #     earright, earleft, mar, pitch, yaw = -10,-10,-10,0,0

            earright, earleft, mar, pitch, yaw = -100,-100,-100,0,0

            # Detect Hands Landmark
            # handsdetected, handsresults = self.hands.detect(mpframe,mpframeposeroi,self.posefaceroi)
            # if handsdetected:
            #     # Smoking Detection
            #     issmoking, ismouthclosed, pointsinroi = self.smoking.detect(mpframe,self.facelandmark.mouth,handsresults,poselmk)
            #     if issmoking:
            #         if detection_mode == "MOVING":
            #             deviations.append("SMOKING")
            #             drawingframe = self.smoking.draw(drawingframe)
            #     # if ismouthclosed:
            #     #     deviations.append("HANDONMOUTH") # Use this to avoid False Alert on Yawning when operator is in radio communication
            #     # elif issmoking:
            #     #     deviations.append("SMOKING")
                
            #     # Phoning Detection
            #     isphoning = self.phoning.detect(mpframe,self.facelandmark.face,self.facelandmark.mouth,handsresults)
            #     if isphoning:
            #         if detection_mode == "MOVING":
            #             deviations.append("PHONING")
            #             drawingframe = self.phoning.draw(drawingframe)

        
        # If face is detected
        if not is_noface:
            # Facemask
            if self.checkfacemask == 1 and detection_mode == "MOVING":
                masked = self.facemask.detect(self.validface)

            # # Eyeglasses
            # if self.checkeyeglass == 1 and detection_mode == "MOVING":
            #     glasses = self.eyeglass.detect(mpframe,
            #                                 self.facelandmark.detectorresult.lefteyeimg,
            #                                 self.facelandmark.detectorresult.righteyeimg,
            #                                 self.facelandmark.detectorresult.nosebridgeimg)
            #     print("Black Eye Glasses:", glasses)
            #     if glasses:
            #         print("EYEGLASS DETECTED:. SEARCHING for PUPILS...")
            #         pupils = self.pupils.detect(mpframe,
            #                                     self.facelandmark.detectorresult.righteyeimg,
            #                                     self.facelandmark.detectorresult.lefteyeimg)
            #         print("PUPILS DETECTED:", pupils)
            #         glasses = (not pupils)
        
        facestat = (earright,earleft,mar,pitch,yaw,masked,glasses)

        if not is_noface:
            if masked:
                deviations.append("FACEMASK")
            
            # if glasses:
            #     deviations.append("EYEGLASS")

            # if is_yawning:
            #     if pointsinroi <=1 : # Check if there are no fingers around mouth -> Any dark object that holded on the mouth can be detected as Open Mouth.
            #         deviations.append("YAWNING")
            #         # drawingframe = self.facelandmark.draw3d(drawingframe)

            # elif is_closedeyes:                    
            #     if is_headdown:
            #         if detection_mode == "MOVING":
            #             deviations.append("HEADDOWN")
            #             drawingframe = self.facelandmark.draw2dMin(drawingframe)
            #     elif is_headup:
            #         if detection_mode == "MOVING":
            #             deviations.append("HEADUP")
            #             drawingframe = self.facelandmark.draw2dMin(drawingframe)
            #     else:
            #         deviations.append("CLOSEDEYES")
            #         # drawingframe = self.facelandmark.draw2dMin(drawingframe)
            # elif is_faceloss:
            #     if is_headleft:
            #         if detection_mode == "MOVING":
            #             deviations.append("HEADLEFT")
            #             drawingframe = self.facelandmark.draw2dMin(drawingframe)
            #     elif is_headright:
            #         if detection_mode == "MOVING":
            #             deviations.append("HEADRIGHT")
            #             drawingframe = self.facelandmark.draw2dMin(drawingframe)
            #     elif is_headup:
            #         if detection_mode == "MOVING":
            #             deviations.append("HEADUP")
            #             drawingframe = self.facelandmark.draw2dMin(drawingframe)
            #     elif is_headdown:
            #         if detection_mode == "MOVING":
            #             deviations.append("HEADDOWN")
            #             drawingframe = self.facelandmark.draw2dMin(drawingframe)
        # else:
        #     if detection_mode == "MOVING":
        #         deviations.append("NOFACE")
        # FACELMK: False False True False
        # print("FACELMK:",is_noface,is_faceloss,is_closedeyes,is_yawning)

        # if self.speed > self.maxroadspeed:
        #     deviations.append("OVERSPEED")

        print("Deviations:", deviations)
        
        # return frame, deviations, facestat
        return drawingframe, deviations, facestat
