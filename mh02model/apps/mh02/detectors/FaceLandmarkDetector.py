import cv2
import math
import numpy as np
import time

class FaceLandmarkDetector:

    class FaceResult:

        def __init__(self,frame,face,eyes,mouth,faceposeresult,ear,mar,pitchrange,yawrange):
            self.reset() # All properties are stated inside of this procedure
            self.getfaceroi(face,frame)
            self.checkclosedeye(eyes,ear,frame)
            self.checkyawning(mouth,mar)
            self.checkfaceloss(faceposeresult,pitchrange,yawrange)

        def reset(self):
            self.face = None
            self.faceroi = None
            self.faceimg = None
            self.lefteyeimg = None
            self.righteyeimg = None
            self.nosebridgeimg = None
            self.ear = (-1,-1)
            self.isclosedeye = False
            self.mar = -1
            self.isyawning = False
            self.pitch, self.yaw, self.roll = -1,-1,-1
            self.isnoface, self.isheadup, self.isheaddown, self.isheadright, self.isheadleft, self.isfaceloss = True, False,False,False,False,False

        def getfaceroi(self,face,frame):
            if not face:
                return
            self.face = face
            
            f_upper,f_lower,f_left,f_right,f_middle = face
            f_upperx, f_uppery = f_upper
            f_lowerx, f_lowery = f_lower
            f_leftx, f_lefty = f_left
            f_rightx, f_righty = f_right
            self.isnoface = False
            xmin,ymin,xmax,ymax = int(f_leftx*0.9),int(f_uppery*0.6),int(f_rightx*1.07),int(f_lowery*1.05)
            # self.faceroi = ((int(f_leftx*0.9),int(f_uppery*0.6)),(int(f_rightx*1.07),int(f_lowery*1.05)))
            self.faceroi = ((xmin,ymin),(xmax,ymax))

            try:
                cp_frame = frame.copy()
                cp_frame = cp_frame[ymin:ymax, xmin:xmax]
                cp_frame = cv2.cvtColor(cp_frame, cv2.COLOR_BGR2RGB)
                self.faceimg = cp_frame.copy()
            except:
                self.faceimg = None

        def euclideandistance(self, point, point1):
            x, y = point
            x1, y1 = point1
            distance = math.sqrt((x1 - x)**2 + (y1 - y)**2)
            return distance

        def checkclosedeye(self,eyes,ear,frame):
            if not eyes:
                self.ear = (-5,-5)
                self.isclosedeye = False
                return

            try:                        
                right_eye, left_eye = eyes
            except:
                right_eye, left_eye = None, None
                self.ear = (-4,-4)
                self.isclosedeye = False
                return

            self.ear = (-3,-3)
            
            if not right_eye or not left_eye:
                self.ear = (-3,-3)
                self.isclosedeye = False
                return

            if right_eye is not None:
                # Right Eye
                rh_right,rh_left,rv_top,rv_bottom = right_eye
                
                rh_rightx, rh_righty = rh_right
                rh_leftx, rh_lefty = rh_left
                rh_diff = abs(rh_rightx - rh_leftx)

                rv_topx,rv_topy = rv_top
                rv_bottomx,rv_bottomy = rv_bottom            
                rv_diff = abs(rv_bottomy - rv_topy)

                r_ear = 0
                if rh_diff>0:
                    r_ear = (rv_diff/rh_diff)

                # re_res = (rv_diff<=ear)
                re_res = (r_ear<=ear)
            else:
                r_ear = -3
                re_res = False

            if left_eye is not None:
                # Left Eye
                lh_right,lh_left,lv_top,lv_bottom = left_eye

                lh_rightx, lh_righty = lh_right
                lh_leftx, lh_lefty = lh_left
                lh_diff = abs(lh_rightx - lh_leftx)

                lv_topx,lv_topy = lv_top
                lv_bottomx,lv_bottomy = lv_bottom
                lv_diff = abs(lv_bottomy-lv_topy)

                l_ear = 0
                if lh_diff > 0:
                    l_ear = (lv_diff/lh_diff)

                # le_res = (lv_diff<=ear)
                le_res = (l_ear<=ear)
            else:
                l_ear = -3
                le_res = False

            self.ear = (r_ear,l_ear)   
            self.isclosedeye = (re_res or le_res)

            # print("******************EAR:", self.ear, ear, self.isclosedeye)
            # self.ear = (rv_diff,lv_diff)
                       
            # Left Eye Image
            try:
                lxmin, _ = lh_right
                lxmax, _ = lh_left
                _, lymin = lv_top
                _, lymax = lv_bottom
                
                # lxmin,lxmax,lymin,lymax = int(lxmin * 0.95),int(lxmax * 1.05),int(lymin * 0.95),int(lymax * 1.05)
                lxmin,lxmax,lymin,lymax = int(lxmin * 1),int(lxmax * 1),int(lymin * 0.97),int(lymax * 1.03)

                cp_frame = frame.copy()
                cp_frame = cp_frame[lymin:lymax, lxmin:lxmax]
                cp_frame = cv2.cvtColor(cp_frame, cv2.COLOR_BGR2RGB)
                # cp_frame = cv2.cvtColor(cp_frame, cv2.COLOR_BGR2GRAY)
                # cp_frame = cv2.cvtColor(cp_frame,cv2.COLOR_GRAY2BGR)
                self.lefteyeimg = cp_frame.copy()
                _h,_w,_c = self.lefteyeimg.shape
                if _h < 1 or _w < 1:
                    self.lefteyeimg = None

                # print("EYEGLASS - LEFT:", self.lefteyeimg)
            except:
                print("LEFT EYE ERROR")
                self.lefteyeimg = None

            # Right Eye Image
            try:
                rxmin, _ = rh_right
                rxmax, _ = rh_left
                _, rymin = rv_top
                _, rymax = rv_bottom

                # rxmin,rxmax,rymin,rymax = int(rxmin * 0.95),int(rxmax * 1.05),int(rymin * 0.95),int(rymax * 1.05)
                rxmin,rxmax,rymin,rymax = int(rxmin * 1),int(rxmax * 1),int(rymin * 0.97),int(rymax * 1.03)

                cp_frame = frame.copy()
                cp_frame = cp_frame[rymin:rymax, rxmin:rxmax]
                cp_frame = cv2.cvtColor(cp_frame, cv2.COLOR_BGR2RGB)
                # cp_frame = cv2.cvtColor(cp_frame, cv2.COLOR_BGR2GRAY)
                # cp_frame = cv2.cvtColor(cp_frame,cv2.COLOR_GRAY2BGR)
                self.righteyeimg = cp_frame.copy()
                _h,_w,_c = self.righteyeimg.shape
                if _h < 1 or _w < 1:
                    self.righteyeimg = None

                # print("EYEGLASS - RIGHT:", self.righteyeimg)
            except:
                self.righteyeimg = None
                print("RIGHT EYE ERROR")

            # Nose Bridge Image
            try:
                _, bymin = rv_top
                bxmin, _ = rh_left

                _, bymax = lv_bottom
                bxmax, _ = lh_right

                bxmin,bxmax,bymin,bymax = int(bxmin * 1),int(bxmax * 1),int(bymin * 0.95),int(bymax * 1)

                cp_frame = frame.copy()
                cp_frame = cp_frame[bymin:bymax, bxmin:bxmax]
                cp_frame = cv2.cvtColor(cp_frame, cv2.COLOR_BGR2RGB)
                # cp_frame = cv2.cvtColor(cp_frame, cv2.COLOR_BGR2GRAY)
                # cp_frame = cv2.cvtColor(cp_frame,cv2.COLOR_GRAY2BGR)
                self.nosebridgeimg = cp_frame.copy()
                _h,_w,_c = self.nosebridgeimg.shape
                if _h < 1 or _w < 1:
                    self.nosebridgeimg = None
            except:
                pass
        
        def checkyawning(self,mouth,mar):
            if not mouth:
                return

            m_upper,m_lower,m_left,m_right = mouth
            
            m_leftx,m_lefty = m_left
            m_rightx,m_righty = m_right
            mh_diff = abs(m_leftx-m_rightx)

            m_upperx,m_uppery = m_upper
            m_lowerx,m_lowery = m_lower
            mv_diff = abs(m_lowery-m_uppery)

            self.mar = 0
            if mh_diff > 0:
                self.mar = (mv_diff/mh_diff)

            # mv_res = (mv_diff>=mar)
            m_res = (self.mar>=mar)

            # print("******************MAR:", self.mar,mar )
            self.isyawning = m_res
            
        def checkfaceloss(self,faceposeresult,pitchrange,yawrange):
            if not faceposeresult:
                return

            p_min, p_max = pitchrange
            y_min, y_max = yawrange
            self.pitch, self.yaw, self.roll = faceposeresult
            # print("PITCH:", self.pitch, p_min, p_max, "YAW:", self.yaw, y_min, y_max)
            self.isheadup = (self.pitch >= p_max)
            self.isheaddown = (self.pitch <= p_min)
            self.isheadright = (self.yaw <= y_min)
            self.isheadleft = (self.yaw >= y_max)
            self.isfaceloss = (self.isheadup or self.isheaddown or self.isheadright or self.isheadleft)

    def __init__(self,mp,facelmkconfig):

        self.update(facelmkconfig)

        self.LEFT_IRIS = [474,475, 476, 477]
        self.RIGHT_IRIS = [469, 470, 471, 472]

        self.LEFT_EYE =[ 362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385,384, 398 ]
        self.RIGHT_EYE=[ 33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161 , 246 ]

        self.LOWER_LIPS =[ 61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
        self.UPPER_LIPS=[ 185, 40, 39, 37,0 ,267 ,269 ,270 ,409, 415, 310, 311, 312, 13, 82, 81, 42, 183, 78]

        self.MOUTH = [ 13,14,78,308 ]
        # self.MOUTH = [ 0,17,78,308 ]
        self.FACE = [ 10,152,234,454,6 ]
        self.FACEPOSE = [ 1, 9, 57, 130, 287, 359 ]
        self.faceposereal = np.array([
                                [285, 528, 200],
                                [285, 371, 152],
                                [197, 574, 128],
                                [173, 425, 108],
                                [360, 574, 128],
                                [391, 425, 108]
                            ], dtype=np.float64)

        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles
        self.mp_face_mesh = mp.solutions.face_mesh
        self.drawing_spec = self.mp_drawing.DrawingSpec(thickness=1, circle_radius=1)
    
        self.face_mesh = self.mp_face_mesh.FaceMesh(
                            static_image_mode=False,                          
                            max_num_faces=2,
                            refine_landmarks=True,
                            min_detection_confidence=0.5,
                            min_tracking_confidence=0.5)
        
    def update(self,facelmkconfig):
        self.facelmkconfig = facelmkconfig.split(",")
        ear_thres = float(self.facelmkconfig[0])
        mar_thres  = float(self.facelmkconfig[1])
        pitch_range = (int(self.facelmkconfig[2]), int(self.facelmkconfig[3])) 
        yaw_range = (int(self.facelmkconfig[4]), int(self.facelmkconfig[5]))

        self.ear_thres,self.mar_thres = ear_thres,mar_thres
        self.pitch_range = pitch_range
        self.yaw_range = yaw_range

    def draw3d(self, frame):

        if not self.lmk3d:
            return frame

        if self.lmk3d:

            try:
                for face_landmarks in self.lmk3d:
                    self.mp_drawing.draw_landmarks(
                        image=frame,
                        landmark_list=face_landmarks,
                        connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=self.mp_drawing_styles
                        .get_default_face_mesh_tesselation_style())
                    self.mp_drawing.draw_landmarks(
                        image=frame,
                        landmark_list=face_landmarks,
                        connections=self.mp_face_mesh.FACEMESH_CONTOURS,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=self.mp_drawing_styles
                        .get_default_face_mesh_contours_style())
                    self.mp_drawing.draw_landmarks(
                        image=frame,
                        landmark_list=face_landmarks,
                        connections=self.mp_face_mesh.FACEMESH_IRISES,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=self.mp_drawing_styles
                        .get_default_face_mesh_iris_connections_style())
                
                # print("FACEROI:", self.detectorresult.faceroi," FACE:", self.detectorresult.face,
                #       "SHAPE:", self.detectorresult.faceimg.shape)

                posmin, posmax = self.detectorresult.faceroi
                # xmin, ymin = posmin
                # xmax, ymax = posmax
                frame = cv2.rectangle(frame, posmin, posmax, (45, 45, 45),2)
                # cv2.imshow("FACE",self.detectorresult.faceimg)
            except:
                pass
        

        return frame
    
    def draw2dMin(self,frame):
        try:

            if self.lmkpoints:
                
                for p in self.right_eye:
                    cv2.circle(frame, p, int(1), (255,0,255), 1, cv2.LINE_AA)

                for p in self.left_eye:
                    cv2.circle(frame, p, int(1), (255,255,0), 1, cv2.LINE_AA)

                for p in self.mouth:
                    cv2.circle(frame, p, int(1), (0,255,255), 1, cv2.LINE_AA)

                for p in self.face:
                    cv2.circle(frame, p, int(1), (255,255,255), 1, cv2.LINE_AA)
                
        except:
            pass

        return frame

    def draw2d(self,frame):
        
        try:

            if self.lmkpoints:
                
                self.draw2dMin()
                
                for i, info in enumerate(zip(('pitch', 'yaw', 'roll'), self.faceposeresult)):
                    k, v = info
                    text = f'{k}: {int(v)}'
                    cv2.putText(frame, text, (20, i*30 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 0, 200), 2)
        except:
            pass

        return frame

    def draw(self,frame):
        return self.draw3d(frame)

    def preprocess(self,frame):
        return frame
    
    def rotation_matrix_to_angles(self,rotation_matrix):
        x = math.atan2(rotation_matrix[2, 1], rotation_matrix[2, 2])
        y = math.atan2(-rotation_matrix[2, 0], math.sqrt(rotation_matrix[0, 0] ** 2 +
                                                        rotation_matrix[1, 0] ** 2))
        z = math.atan2(rotation_matrix[1, 0], rotation_matrix[0, 0])
        return np.array([x, y, z]) * 180. / math.pi

    def calculatepose(self,shape):
        h,w = shape

        self.facepose = np.array(self.facepose, dtype=np.float64)
        
        focal_length = 1 * w
        cam_matrix = np.array([[focal_length, 0, w / 2],
                            [0, focal_length, h / 2],
                            [0, 0, 1]])

        dist_matrix = np.zeros((4, 1), dtype=np.float64)

        success, rotation_vec, transition_vec = cv2.solvePnP(
            self.faceposereal, self.facepose,
            cam_matrix, dist_matrix)

        rotation_matrix, jacobian = cv2.Rodrigues(rotation_vec)

        self.faceposeresult = self.rotation_matrix_to_angles(rotation_matrix)
        pitch = self.faceposeresult[0]
        yaw = self.faceposeresult[1]
        roll = self.faceposeresult[2]
        self.faceposeresult = (pitch,yaw,roll)

    def getfacepose(self):
        self.facepose = []
        for idx in self.FACEPOSE:
            self.facepose.append(self.lmkpoints[idx])

    def getface(self):
        f_upper = self.lmkpoints[self.FACE[0]]
        f_lower = self.lmkpoints[self.FACE[1]]
        f_left = self.lmkpoints[self.FACE[2]]
        f_right = self.lmkpoints[self.FACE[3]]
        f_middle = self.lmkpoints[self.FACE[4]]
        self.face = (f_upper,f_lower,f_left,f_right,f_middle)

    def getmouth(self):
        m_upper = self.lmkpoints[self.MOUTH[0]]
        m_lower = self.lmkpoints[self.MOUTH[1]]
        m_left = self.lmkpoints[self.MOUTH[2]]
        m_right = self.lmkpoints[self.MOUTH[3]]
        self.mouth = (m_upper,m_lower,m_left,m_right)

    def geteyes(self):
        # Right Eye
        rh_right = self.lmkpoints[self.RIGHT_EYE[0]]
        rh_left = self.lmkpoints[self.RIGHT_EYE[8]]
        rv_top = self.lmkpoints[self.RIGHT_EYE[12]]
        rv_bottom = self.lmkpoints[self.RIGHT_EYE[4]]
        self.right_eye = (rh_right,rh_left,rv_top,rv_bottom)

        # Left Eye
        lh_right = self.lmkpoints[self.LEFT_EYE[0]]
        lh_left = self.lmkpoints[self.LEFT_EYE[8]]
        lv_top = self.lmkpoints[self.LEFT_EYE[12]]
        lv_bottom = self.lmkpoints[self.LEFT_EYE[4]]
        self.left_eye = (lh_right,lh_left,lv_top,lv_bottom)

    def validate(self, posefaceroi):
        rh_right,rh_left,rv_top,rv_bottom = self.right_eye
        lh_right,lh_left,lv_top,lv_bottom = self.left_eye

        rtopx, rtopy = rv_top
        ltopx, ltopy = lv_top

        incounter = 0

        roixmin, roiymin, roixmax, roiymax = posefaceroi

        if rtopx >= roixmin and rtopx <= roixmax:
            incounter += 1
        
        if rtopy >= roiymin and rtopy <= roiymax:
            incounter += 1
        
        if ltopx >= roixmin and ltopx <= roixmax:
            incounter += 1
        
        if ltopy >= roiymin and ltopy <= roiymax:
            incounter += 1

        result = (int(incounter) == 4)

        if not result:
            self.right_eye = None
            self.left_eye = None

        return result

    def postprocess(self,shape, posefaceroi):

        if self.lmks is None:
            return

        img_height, img_width = shape

        for item in self.lmks:
            self.lmkpoints = []

            for point in item:
                x = int(point.x * img_width)
                y = int(point.y * img_height)
                self.lmkpoints.append((x,y))

            self.geteyes()
            if not self.validate(posefaceroi):
                self.lmkpoints = []
                continue
            else:
                self.getmouth()
                self.getface()
                self.getfacepose()
                self.calculatepose(shape)
                self.lmk = item
                break
    
    def process(self,frame,shape,posefaceroi):
        # cv2.imshow('FACE', frame)
        
        frame = self.preprocess(frame)
        self.results = self.face_mesh.process(frame)
        # print("***FACE RESULT***", self.results.multi_face_landmarks)
        if self.results.multi_face_landmarks:
            self.lmk3d = self.results.multi_face_landmarks

            self.lmks = []
            for item in self.results.multi_face_landmarks:
                self.lmks.append(item.landmark)
            
        self.postprocess(shape, posefaceroi)
        
    def getresult(self,frame):
        self.detectorresult = FaceLandmarkDetector.FaceResult(
                                    frame,
                                    self.face,
                                    (self.right_eye,self.left_eye),
                                    self.mouth,
                                    self.faceposeresult,
                                    self.ear_thres,self.mar_thres,
                                    self.pitch_range,self.yaw_range)
        return self.detectorresult

    def reset(self):
        self.detectorresult = None
        self.results = None
        self.lmk3d = None
        self.lmks = None
        self.lmk = None
        self.lmkpoints = None
        self.right_eye = None
        self.left_eye = None
        self.mouth = None
        self.face = None
        self.facepose = None
        self.faceposeresult = None

    def detect(self,frame,shape,posefaceroi):
        self.reset()
        self.process(frame,shape,posefaceroi)
        
        return self.getresult(frame)
