from datetime import datetime

class MineAwarenessDetector:

    def __init__(self, mineawarenessparams, numsatparams):
        self.update(mineawarenessparams, numsatparams)
        self.reset()

    def update(self, mineawarenessparams, numsatparams):
        self.threshold_restricted = float(mineawarenessparams[0]) if len(mineawarenessparams) > 0 else 1.0
        self.threshold_highrisk = float(mineawarenessparams[1]) if len(mineawarenessparams) > 1 else 1.0
        self.minimumnumsat = int(numsatparams)

    def reset(self):
        self.isrestricted_alert = False
        self.ishighrisk_alert = False
        self.isrestricted_unauthorized = False
        self.ishighrisk_unauthorized = False
        self.isroster_warning = False

    def check_authorization(self, is_authorized, nrp):
        if is_authorized == "0" and nrp and nrp.strip():
            return False
        return True

    def check_roster_validity(self, start_shift, end_shift):
        try:
            # print(current_time, start_shift, end_shift,"-------------------------------------------------------")
            if not start_shift or not end_shift:
                return False
            
            current_time = datetime.now().date()
            start_time = datetime.strptime(start_shift,"%Y%m%d").date()
            end_time = datetime.strptime(end_shift,"%Y%m%d").date()

            print((start_time <= current_time <= end_time),"-------------------------------------------------------")
            
            return start_time <= current_time <= end_time
        except Exception as e:
            print("ERROR CHECK VALIDITY", e)
            return False

    def process(self, restricted, highrisk, numsat, is_authorized, nrp, start_shift, end_shift):
        try:
                
            isvalidnumsat = (numsat >= self.minimumnumsat)
            
            if not isvalidnumsat:
                return


            if highrisk == "1":
                if restricted == "1":
                    self.isrestricted_alert = True
                else:
                    if self.check_roster_validity(start_shift, end_shift):
                        if self.check_authorization(is_authorized, nrp):
                            self.isroster_warning = True
                        else:
                            self.ishighrisk_alert = True
                    else:
                        self.ishighrisk_unauthorized = True
            else:
                pass

        except Exception as e:
            print(e)
            
        # if restricted == "1":
        #     self.isrestricted_alert = True
            
        #     if not self.check_authorization(is_authorized, nrp):
        #         self.isrestricted_unauthorized = True
            
        #     if not self.check_roster_validity(start_shift, end_shift):
        #         self.isroster_warning = True

        # if highrisk == "1":
        #     self.ishighrisk_alert = True
            
        #     if not self.check_authorization(is_authorized, nrp):
        #         self.ishighrisk_unauthorized = True
            
        #     if not self.check_roster_validity(start_shift, end_shift):
        #         self.isroster_warning = True

    def getresults(self):
        return (self.isrestricted_alert, self.ishighrisk_alert, 
                self.isrestricted_unauthorized, self.ishighrisk_unauthorized, 
                self.isroster_warning)

    def draw(self, frame):
        return frame

    def detect(self, frame, restricted, highrisk, numsat, is_authorized, nrp, start_shift, end_shift):
        self.reset()

        if restricted is None and highrisk is None:
            return self.getresults()
        
        self.process(restricted, highrisk, numsat, is_authorized, nrp, start_shift, end_shift)
        
        return self.getresults()