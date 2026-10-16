import os
import threading
import collections
import time
from datetime import datetime

class AlertLogger:

    def __init__(self, base_path="..\\..\\..\\..\\..\\pama\\ftp"):
        self.base_path = base_path
        self.log_queue = collections.deque()
        self.flag = collections.deque(maxlen=1)
        
        os.makedirs(self.base_path, exist_ok=True)
        
        threading.Thread(target=self.run, args=(1,)).start()
    
    def log_alert(self, sound_text, device_id, unit_no, alert_tags, speed, segment, road, 
                  lat, lon, maxroadspeed, numsat, speedcanbus, speedsource, 
                  restricted="", highrisk="", nrp="", start_shift="", end_shift="", 
                  is_authorized="", location_hr=""):
 
        try:
            # Generate timestamp and create PID
            dt = datetime.now()
            timestamp = dt.strftime("%Y%m%d%H%M%S")
            
            if isinstance(alert_tags, list) and alert_tags:
                for tag in alert_tags:
                    pid = f"{device_id}_{unit_no}_{tag}_{timestamp}"
                    
                    log_data = {
                        'sound_text': sound_text,
                        'pid': pid,
                        'speed': speed,
                        'segment': segment,
                        'road': road,
                        'lat': lat,
                        'lon': lon,
                        'maxroadspeed': maxroadspeed,
                        'numsat': numsat,
                        'speedcanbus': speedcanbus,
                        'speedsource': speedsource,
                        'restricted': restricted,
                        'highrisk': highrisk,
                        'nrp': nrp,
                        'start_shift': start_shift,
                        'end_shift': end_shift,
                        'is_authorized': is_authorized,
                        'location_hr': location_hr,
                        'timestamp': timestamp
                    }
                    
                    self.log_queue.append(log_data)
            else:
                tag_str = str(alert_tags) if alert_tags else "UNKNOWN"
                pid = f"{device_id}_{unit_no}_{tag_str}_{timestamp}"
                
                log_data = {
                    'sound_text': sound_text,
                    'pid': pid,
                    'speed': speed,
                    'segment': segment,
                    'road': road,
                    'lat': lat,
                    'lon': lon,
                    'maxroadspeed': maxroadspeed,
                    'numsat': numsat,
                    'speedcanbus': speedcanbus,
                    'speedsource': speedsource,
                    'restricted': restricted,
                    'highrisk': highrisk,
                    'nrp': nrp,
                    'start_shift': start_shift,
                    'end_shift': end_shift,
                    'is_authorized': is_authorized,
                    'location_hr': location_hr,
                    'timestamp': timestamp
                }
                
                self.log_queue.append(log_data)
            
        except Exception as e:
            print(f"ERROR: AlertLogger - Failed to queue log: {e}")
    
    def _write_log_file(self, log_data):
        try:
            date_folder = datetime.utcnow().strftime("%Y%m%d")
            
            filename = f"{log_data['timestamp']}.txt"

            filepath = os.path.join(self.base_path, date_folder, filename)
            
            file_content = ";".join([
                log_data['sound_text'],
                log_data['pid'],
                str(log_data['speed']),
                str(log_data['segment']),
                str(log_data['road']),
                str(log_data['lat']),
                str(log_data['lon']),
                str(log_data['maxroadspeed']),
                str(log_data['numsat']),
                str(log_data['speedcanbus']),
                str(log_data['speedsource']),
                str(log_data['restricted']),
                str(log_data['highrisk']),
                str(log_data['nrp']),
                str(log_data['start_shift']),
                str(log_data['end_shift']),
                str(log_data['is_authorized']),
                str(log_data['location_hr'])
            ])
            
            with open(filepath, "w", encoding='utf-8') as f:
                f.write(file_content)
                        
        except Exception as e:
            print(f"ERROR: AlertLogger - Failed to write log file: {e}")
    
    def stop(self):
        self.flag.append(1)
    
    def run(self, mode):
    
        while True:
            time.sleep(0.01)  
            
            if len(self.log_queue) > 0:
                log_data = self.log_queue.popleft()
                self._write_log_file(log_data)
            
            # Check stop flag
            if len(self.flag) > 0:
                while len(self.log_queue) > 0:
                    log_data = self.log_queue.popleft()
                    self._write_log_file(log_data)
                break
        
        print("DEBUG: AlertLogger - Stopped")