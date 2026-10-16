import redis
import json
import time
from typing import Optional, Tuple, Union

class RedisManager:
    def __init__(self, host='127.0.0.1', port=6379, db=0):
        self.host = host
        self.port = port
        self.db = db
        self.redis_client = None
        self.last_heartbeat = None
        self._connect()

    def _connect(self):
        try:
            self.redis_client = redis.Redis(
                host=self.host, 
                port=self.port, 
                db=self.db,
                socket_connect_timeout=1,
                socket_timeout=1,
                retry_on_timeout=True,
                health_check_interval=30
            )
            self.redis_client.ping()
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Redis connection failed: {e}")
            self.redis_client = None

    def Get(self, data_type):
        
        if not self.redis_client:
            self._connect()
        
        if not self.redis_client:
            return None
            
        try:
            json_data = self.redis_client.get(f"{data_type}")
            
            if json_data:
                data = json.loads(json.loads(json_data.decode('utf-8')))
                self.last_heartbeat = data['heartbeat']
                return data
            else:
                return None

        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Redis GET failed: {e}")
            self.redis_client = None  
            return None

    def DetectUnchanges(self, timeout_seconds: int = 5) -> bool:
        if not self.last_heartbeat:
            return True
        
        current_time = int(time.time())
        time_diff = current_time - self.last_heartbeat
        
        return time_diff > timeout_seconds

