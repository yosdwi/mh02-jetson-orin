import collections
import time
import threading
import os
import winsound
import uuid
from classes.Config import *

class AlertPlayerFront:
    
    def __init__(self, path):
        self.path = path
        self.config = Config(path)
        self.alertmode = int(self.config.getValue("ALERT_MODE_FRONT"))
        self.alertpath = str(self.config.getValue("ALERT_PATH"))
        self.alerts = collections.deque()
        self.flag = collections.deque(maxlen=1)
        threading.Thread(target=self._worker, daemon=True).start()

    def update(self):
        self.config.load()
        self.alertmode = int(self.config.getValue("ALERT_MODE_FRONT"))
        self.alertpath = str(self.config.getValue("ALERT_PATH"))

    def add(self, sound_text, alert_type="UNKNOWN"):
        if self.alertmode == 0:
            return
        
        if len(self.alerts) > 1:
          while self.alerts:
              dropped_alert = self.alerts.popleft()
        
        self.alerts.append({'text': sound_text, 'type': alert_type})

    def _worker(self):        
        while len(self.flag) == 0:
            if self.alerts:
                try:
                    alert = self.alerts.popleft()
                    self._play_alert(alert)
                except Exception as e:
                    print(f"ERROR: AlertPlayerFrontNew - Alert processing failed: {e}")
            else:
                time.sleep(0.01)

    def _play_alert(self, alert):
        try:
            if alert['text'] == 'Beep':
                # i=0
                # for i in range(0,3):
                #     print("========INI BUNYI BEEP 2")
                #     winsound.Beep(1800, 400)
                self._play_beep()
            else:
                self._play_voice(alert['text'])
                                
        except Exception as e:
            print(f"ERROR: AlertPlayerFrontNew - Alert play failed: {e}")
            self._play_beep()

    def _play_voice(self, text):
        try:
            # Generate unique filename to prevent race conditions
            unique_id = str(uuid.uuid4())[:8]
            wav_filename = f"alert_{unique_id}.wav"
            wav_filepath = os.path.join(self.alertpath, wav_filename)
            
            alert_text = text.replace('"', "'")
            
            wsay_command = f'{self.alertpath}wsay "{alert_text}" --voice 6 -o "{wav_filepath}"'
            os.system(wsay_command)
            
            if os.path.exists(wav_filepath):
                winsound.PlaySound(wav_filepath, winsound.SND_FILENAME)
                
                try:
                    os.remove(wav_filepath)
                except:
                    pass 
            else:
                print(f"ERROR: AlertPlayerFrontNew - WAV file not created: {wav_filepath}")
                self._play_beep()
            
        except Exception as e:
            print(f"ERROR: AlertPlayerFrontNew - Voice playback failed: {e}")
            self._play_beep()

    def _play_beep(self):
        try:
            i=0
            for i in range(0,3):
                # winsound.Beep(1800, 400)
                # winsound.MessageBeep()
                winsound.PlaySound("C:\\Windows\\Media\\Windows Error.wav", winsound.SND_FILENAME)
        except Exception as e:
            print(f"ERROR: AlertPlayerFrontNew - Beep failed: {e}")

    def stop(self, mode):
        self.flag.append(mode)
