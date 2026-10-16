import json
import os
import uuid

class Config:

    def __init__(self, path):
        self.path = path
        # self.backuppath = f"D:\\Users\\p6103081\\Downloads\\Config\\backups\\{os.path.basename(self.path)}"
        self.backuppath = f"D:\\smartd\\backups\\configs\\{os.path.basename(self.path)}"
        self.data = None
        self.datautf = None
        
        if os.path.exists(self.path):
            self.lastmodified = os.path.getmtime(self.path)
            self.currentmodified = os.path.getmtime(self.path)
            self.load()
        else:
            print("[FATAL] Config not found...")

    def openMainConfig(self):
        openres = False
        # Copy main config to temp
        tmpmain = self.path + "." + str(uuid.uuid4()) + ".temp"
        cmdret = os.system("type " + self.path + " > " + tmpmain)
        # Try load from temp
        try:
            with open(tmpmain, 'r') as f:
                self.datautf = f
                self.data = json.load(f)
                print("[INFO] Load config success...")
            cmdret = os.system("DEL " + tmpmain)
            self.lastmodified = os.path.getmtime(self.path)
            openres = True
        except:
            cmdret = os.system("DEL " + tmpmain)
            print("[INFO] Load config failed...")
            openres = False
        return openres

    def restoreFromBackup(self):
        backupres = False
        tmpbackup = self.backuppath + "." + str(uuid.uuid4()) + ".temp"
        cmdret = os.system("type " + self.backuppath + " > " + tmpbackup)
        # Try load from temp
        try:
            with open(tmpbackup, 'r') as f:
                self.datautf = f
                self.data = json.load(f)
                print("[INFO] Load BACKUP config success...")

            cmdret = os.system("type " + tmpbackup + " > " + self.path)
            self.lastmodified = os.path.getmtime(self.path)
            print("[INFO] Restoring from backup config success...")
            mdret = os.system("DEL " + tmpbackup)
            backupres = True
        except:
            cmdret = os.system("DEL " + tmpbackup)
            print("[ERROR] Restoring from backup config failed...")
            backupres = False
        
        return backupres

    def restoreFromCache(self):
        cacheres = False
        try:
            cachetemp = self.backuppath + "." + str(uuid.uuid4()) + ".cache.temp"
            with open(cachetemp, 'w') as f:
                json.dump(self.data, f, indent=4)
                print("[INFO] Saving current values to temporary is SUCCESS")
            
            cmdret = os.system("type " + cachetemp + " > " + self.backuppath)
            cmdret = os.system("type " + cachetemp + " > " + self.path)
            self.lastmodified = os.path.getmtime(self.path)
            mdret = os.system("DEL " + cachetemp)
            cacheres = True
        except Exception as ex:
            print("[FATAL] Saving current values is failed. Reason:", ex)

        return cacheres

    def load(self):
        if self.data is None: # First load
            openres = self.openMainConfig()
        else:
            self.currentmodified = os.path.getmtime(self.path)            
            if self.currentmodified > self.lastmodified:
                print("[INFO] Config is updated. Reload.")
                openres = self.openMainConfig()
            else:
                openres = True
                print("[INFO] Config is not updated. Keep current version")
        
        if openres == False:
            print("[ERROR] Loading main config is failed.")
            print("[ERROR] Try restoring from backup.")
            backupres = self.restoreFromBackup()
            if backupres:
                print("[INFO] Main config successfully restored.")
            else:
                # Main config and backup are corrupt
                # Check if loaded config exists
                if self.data is not None:
                    print("[INFO] Restoring from current cache...")
                    cacheres = self.restoreFromCache()
                    if cacheres == True:
                        print("[INFO] Restoring from current cache success")
                    else:
                        print("[ERROR] Restoring from cache is failed. REPLACE FILE.")
                else:
                    print("[ERROR] Restoring from backup is failed. REPLACE FILE.")
    
    def getValue(self,key):
        try:
            return self.data[key]
        except:
            return None