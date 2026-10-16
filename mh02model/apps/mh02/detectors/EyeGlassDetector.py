import cv2
import numpy as np
import math

class EyeGlassDetector:

    def __init__(self):
        self.rho = 1  # distance resolution in pixels of the Hough grid
        self.theta = np.pi / 180  # angular resolution in radians of the Hough grid
        self.threshold = 35  # minimum number of votes (intersections in Hough grid cell)
        self.min_line_length = 100  # minimum number of pixels making up a line
        self.max_line_gap = 10  # maximum gap in pixels between connectable line segments
        
        self.reset()

    def reset(self):
        self.lefteye, self.righteye = None, None
        self.isblackeyeglass = False
        self.nosebridge = None

        self.eyeglasscolours = [(77,95),(123,138)]

    def draw(self, frame):
        # return frame
        try:
            print("DRAW EYEGLASS")
            cv2.imshow("LEFT", self.lefteye)
            cv2.imshow("RIGHT", self.righteye)
            # cv2.imshow("NOSE", self.nosebridge)
            return frame
        except:
            print("FAILED DRAW EYEGLASS")
            return frame

    def preprocess(self,frame):
        pass
    
    def getMostColour(self,eyeimg):
        n_clusters = 1

        imgdata = eyeimg.reshape(-1, 3)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        flags = cv2.KMEANS_RANDOM_CENTERS
        compactness, labels, centers = cv2.kmeans(imgdata.astype(np.float32), n_clusters, None, criteria, 10, flags)

        cluster_sizes = np.bincount(labels.flatten())

        palette = []
        for cluster_idx in np.argsort(-cluster_sizes):
            palette.append(np.full((eyeimg.shape[0], eyeimg.shape[1], 3), fill_value=centers[cluster_idx].astype(int), dtype=np.uint8))
        palette = np.hstack(palette)

        return palette[0]
    
    def getEyeGlassBridge(self):
        img_gray = cv2.cvtColor(self.nosebridge.copy(), cv2.COLOR_BGR2GRAY)
        img_gray = cv2.cvtColor(img_gray,cv2.COLOR_GRAY2BGR)
        img_blur = cv2.GaussianBlur(np.array(img_gray),(3,3), sigmaX=0, sigmaY=0)
        edges = cv2.Canny(image=img_blur, threshold1=100, threshold2=200)

        # cv2.imshow("BRIDGE", edges)

        edges_center = edges.T[(int(len(edges.T)/2))]
    
        print("CENTER:", edges_center)
        # gray = cv2.cvtColor(self.nosebridge, cv2.COLOR_BGR2GRAY)
        # cv2.imshow("GRAY", gray)
        # edges = cv2.Canny(gray,100,150,apertureSize = 3)
        # cv2.imshow("EDGES", edges)
        # lines = cv2.HoughLinesP(edges, self.rho, self.theta, self.threshold, np.array([]),
        #                         self.min_line_length, self.max_line_gap)
        # if not lines is None:
        #     for line in lines:
        #         for x1,y1,x2,y2 in line:
        #             deltaY = y2-y1
        #             deltaX = x2-x1
        #             angle = math.atan2(deltaY,deltaX) * 180 / math.pi
        #             # print("ANGLE:",angle)
        #             cv2.line(self.nosebridge,(x1,y1),(x2,y2),(255,0,0),5)
        #             cv2.imshow("NOSE", self.nosebridge)

        #             # if angle > self.anglemin and angle < self.anglemax:
        #             #     self.seatbeltcounter += 1
        #             #     self.seatbeltlines.append(((x1,y1),(x2,y2),angle))
        #             #     # cv2.line(crop_img,(x1,y1),(x2,y2),(255,0,0),5)
        #             #     # cv2.line(frame,(x1,y1),(x2,y2),(255,0,0),5)
        #             #     # print((x1,y1),(x2,y2),angle)

    def process(self,frame):
        
        eyeimgs = [self.lefteye,self.righteye]
        mostcolours = []

        for img in eyeimgs:
            rescol = self.getMostColour(img)
            mostcolours.append(rescol)

        # print("MOST COLORS:", mostcolours)
        glasscounter = 0
        for col in mostcolours:
            # print("COLOR ITEM:", col[0])
            eyecol,_,_ = col[0]
            for clr in self.eyeglasscolours:
                cmin, cmax = clr
                print("THR:", cmin, cmax, "PALETTE:", eyecol, "RES:", (int(cmin) <= eyecol <= int(cmax)))
                if int(cmin) <= eyecol <= int(cmax): 
                    glasscounter += 1

        self.isblackeyeglass = (glasscounter>0)
        glasscounter = 0

        self.getEyeGlassBridge()

    def getResults(self):
        return False #self.isblackeyeglass
        
    def detect(self,frame,lefteye,righteye,nosebridge):
        self.reset()
        
        if lefteye is None or righteye is None or nosebridge is None:
            return self.getResults()
        
        self.lefteye = lefteye.copy()
        self.righteye = righteye.copy()
        self.nosebridge = nosebridge.copy()

        self.preprocess(frame)
        self.process(frame)

        return self.getResults()