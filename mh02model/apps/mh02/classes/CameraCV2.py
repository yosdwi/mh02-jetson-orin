import cv2
import os
import threading
import collections
import time


class CameraCV2:

    def __init__(self, path, maxinactive):
        self.isrunning = False
        self.maxinactive = int(maxinactive)
        self.lastframetime = None
        self.flag = collections.deque(maxlen=1)

        self.cap = None
        self.frame = collections.deque(maxlen=1)
        self.path = path

        if self.path.startswith("rtsp"):
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
            self.cap = cv2.VideoCapture(self.path, cv2.CAP_FFMPEG)
        else:
            if self.path.isnumeric():
                self.cap = cv2.VideoCapture(int(self.path))
            else:
                self.cap = cv2.VideoCapture(self.path)

        if self.cap.isOpened():
            self.isrunning = True
            threading.Thread(target=self.run, args=(1,)).start()
        else:
            self.release()
            time.sleep(3)

    def run(self, mode):
        while True:
            if len(self.flag)>0:
                break

            stat = False
            try:
                stat, frame = self.cap.read()                
            except:
                pass
            
            if stat:
                    self.frame.append(frame)
                    self.isrunning = True
                    self.lastframetime = None
            else:
                if self.lastframetime is None:
                    self.lastframetime = time.time()
                else:
                    print(time.time(), " - ", self.lastframetime, " - ", self.maxinactive)
                    if (int(time.time() - self.lastframetime)>=int(self.maxinactive)):
                        break

            time.sleep(1/150)

        self.release()
        self.isrunning = False
        return

    def read(self):
        if len(self.frame)>0:
            return self.cap.isOpened(), self.frame
        else:
            return self.cap.isOpened(), None
        
    def stop(self,mode):
        self.flag.append(mode)
        print("Flag", len(self.flag))

    def release(self):
        self.cap.release()

