import uuid
import os
from classes.Config import *
from classes.UDPServer import *
from classes.Camera import *
from classes.VisualizerCabin import *


class MH02Cabin:
    def __init__(self):

        # Initiate config reader
        self.config = Config("E:\\MH02\\MH02_V5\\files\\configs\\mh02_cabin.json")
        self.deviceconfig = Config("E:\\MH02\\MH02_V5\\files\\configs\\smartd.json")
        os.system("wmic bios get serialnumber > D:\\smartd\\script\\sn\\sn.txt")

        self.CAM_URL = self.config.getValue("CAM_URL")
        self.UDP_LOCAL_PORT = self.config.getValue("UDP_LOCAL_PORT")
        self.UDP_BUFFER_SIZE = self.config.getValue("UDP_BUFFER_SIZE")
        self.MAX_PRE_FRAMES = self.config.getValue("MAX_PRE_FRAMES")
        self.MAX_POST_FRAMES = self.config.getValue("MAX_POST_FRAMES")

        self.DEVICE_ID = self.deviceconfig.getValue("DEVICE_ID")
        self.UNIT_NO = self.deviceconfig.getValue("UNIT_NO")

        self.dataid = None
        self.dataparsed = None

        # Start UDP server to receive realtime data from Node-Red
        self.udp = UDPServer("127.0.0.1",self.UDP_LOCAL_PORT,self.UDP_BUFFER_SIZE)

        # Connect to Camera
        self.cap = Camera(self.CAM_URL,2)

        # Start visualizer
        self.visualizer = VisualizerCabin(self.config.path,5,self.MAX_PRE_FRAMES,self.MAX_POST_FRAMES,(self.DEVICE_ID,self.UNIT_NO))
        print(self.visualizer)

    def parseUDP(self,message):
        # times|deviceid|unitno|speed|lat|lon|sta|segment|road|maxroadspeed|
        if message is None:
            return None
        arrmsg = message.popleft().split("|")
        if len(arrmsg)<1:
            return None
        # print(arrmsg)
        return arrmsg

    def run(self):

        while True:

            # Check if any received data from Node-Red
            udpstat, udpmessage = self.udp.getMessage()

            udpparsed = self.parseUDP(udpmessage)
            if udpparsed is not None:
                # If new data is received, set data id and replace dataparsed content with the new one
                # Otherwise dataparsed value will remain with last data
                # Visualizer will evaluate dataparsed by comparing its data id and only proceed with new data.
                dataid = str(uuid.uuid4())
                dataparsed = udpparsed

            # If UDP server is not running, re-initiate UDP Server
            if not udpstat:
                print("UDP Server is not running")
                self.udp = UDPServer("127.0.0.1",self.UDP_LOCAL_PORT,self.UDP_BUFFER_SIZE)

            # Grab new frame from Camera
            framestat, framecap = self.cap.read()
            if framestat and (framecap is not None):
                # If Camera is connected and frame is not empty send frame, dataid and dataparsed to Visualizer
                frame,_deviationtags,_resdataid,_dataparsed = self.visualizer.process(framecap.popleft(),dataid,dataparsed, (self.DEVICE_ID,self.UNIT_NO))
                cv2.imshow('Cabin', frame)

            elif framestat == False:
                # If Camera is disconnected, reconnect the Camera and 
                print("Reconnecting")
                self.cap = Camera(self.CAM_URL,2,2)
                # Ask Visualizer to reset all data and statistics
                # Remain temporary deviations will be saved and sent to Node-red
                self.visualizer.reset()

            if cv2.waitKey(1) == 27:
                break

        # Stop all threads
        self.udp.stop(1)
        self.cap.stop(1)
        self.visualizer.stop()

        cv2.destroyAllWindows()
        exit(-1)

















