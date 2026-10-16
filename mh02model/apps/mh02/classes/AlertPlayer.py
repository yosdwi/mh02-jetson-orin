# Update History
# Version 6.2
# 2024-06-03    JRP     Happy 21st years in PAMA ;)
#                       (1) Split Fatigue Detection and Behavior Detection
#                           to improve system performance.
#                       (2) Implement 0 kmph detection and alert mode.


import collections
import time
import datetime
import threading
import os
import winsound
from classes.Config import *

class AlertPlayer:
    def __init__(self, path):
        self.flag = collections.deque(maxlen=1)
        self.path = path
        self.config = Config(path)
        self.alertmode = int(self.config.getValue("ALERT_MODE"))
        self.alertpath = str(self.config.getValue("ALERT_PATH"))
        self.fatigue_alert_mute_times = str(self.config.getValue("FATIGUE_ALERT_MUTE_TIME"))
        self.mute_time_arr = []
        self.vehicleismoving = True
        self.alerts = collections.deque()
        threading.Thread(target=self.run, args=(1,)).start()

    def update(self):
        self.config.load()
        self.alertmode = int(self.config.getValue("ALERT_MODE"))
        self.alertpath = str(self.config.getValue("ALERT_PATH"))
        self.fatigue_alert_mute_times = str(self.config.getValue("FATIGUE_ALERT_MUTE_TIME"))

        # print("************************sound mode : ",self.alertmode,self.path)

    def add(self, msg):
        self.alerts.append(msg)

    def stop(self, mode):
        self.flag.append(mode)


    def parse_mute_times(self):
        global mute_time_arr

        self.mute_time_arr = []
        _mute_times_strs = self.fatigue_alert_mute_times.replace("|","").split(",")
        
        for _times in _mute_times_strs:
            _times_arr = _times.split("-")
            self.mute_time_arr.append(_times_arr)


    def checkMuteStatus(self):

        self.parse_mute_times()

        _local_time = time.localtime()
        _current_time = time.strftime("%H:%M:%S", _local_time)
        _mute_status = False

        for _item in self.mute_time_arr:
            _start_time = _item[0]
            _end_time = _item[1]

            if _start_time <= _end_time:
                _mute_status = (_current_time>=_start_time and _current_time<=_end_time)
            else:
                _mute_status = ((_current_time>=_start_time and _current_time<="23:59:59") or (_current_time>="00:00:00" and _current_time<=_end_time))
                # Start Time is bigger than End Time, exp: 23:00:00 PM to 01:00:00 AM (different date)
            
            # print(_start_time,_end_time,_mute_status)
            if _mute_status:
                # Exit when found that mute status is True
                # Otherwise check all mute times
                break

        return _mute_status    


    def run(self, mode):
        while True:
            time.sleep(0.001)          
            if len(self.alerts)>0:
                alert = self.alerts.popleft()
                # print("alert :",alert)
                # print(alertmode)

                if self.alertmode==0:
                    # Alert is deactivated/ Disabled permanently
                    print("alert mode0 : ",self.alertmode)
                    print("soundmuted")
                    continue
                
                if self.checkMuteStatus() == True and self.vehicleismoving == False:
                    continue

                # print("************************alert mode1 BEFORE 1 : ",self.alertmode,datetime.datetime.now())
                # os.system(self.alertpath + 'wsay "' + alert + '" --voice 5 ')
                os.system(self.alertpath + 'wsay "' + alert + '" --voice 6 -o ' + self.alertpath + '\\alert.wav')
                # print("************************alert mode1 BEFORE 2 : ",self.alertmode,datetime.datetime.now())
                winsound.PlaySound(self.alertpath + '\\alert.wav', winsound.SND_FILENAME)
                # print("************************alert mode1 AFTER : ",self.alertmode,datetime.datetime.now())                
                                
            if len(self.flag)>0:
                break