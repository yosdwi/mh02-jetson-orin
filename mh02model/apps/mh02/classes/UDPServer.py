import socket
import collections
import threading

class UDPServer:

    def __init__(self, ip, port, buffersize):
        self.ip = ip
        self.port = port
        self.buffersize = buffersize

        self.isrunning = False
        self.flag = collections.deque(maxlen=1)
        self.message = collections.deque(maxlen=1)

        self.clientaddress = collections.deque(maxlen=1)
        self.UDPserversocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

        try:
            self.UDPserversocket.bind((self.ip, self.port))
            self.UDPserversocket.setblocking(0)
            print("UDP Server is running on", self.port)
            threading.Thread(target=self.run, args=(1,)).start()
        except:
            print("UDP Server is Failed on", self.port)

    def run(self, mode):
    
        while True:
            if len(self.flag)>0:
                self.isrunning = False
                break
            
            self.isrunning = True

            try:
                data = self.UDPserversocket.recvfrom(self.buffersize)
                self.message.append(data[0].decode())
                self.clientaddress.append(data[1])

                clientMsg = "Message from Client:{}".format(self.message)
                clientIP  = "Client IP Address:{}".format(self.clientaddress)
        
                # print(clientMsg)
                # print(clientIP)
            except:
                pass
        
        return

    def stop(self,mode):
        self.flag.append(mode)
            
    def getMessage(self):
        if len(self.message)>0:
            return self.isrunning, self.message
        else:
            return self.isrunning, None
        
    def sendMessage(self, message):
        if len(self.clientaddress)<1:
            return False
        try:
            bytestosend = str.encode(message)
            self.UDPserversocket.sendto(bytestosend, self.clientaddress)
            return True
        except:
            return False
    