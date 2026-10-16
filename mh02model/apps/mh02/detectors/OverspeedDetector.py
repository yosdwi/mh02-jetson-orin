class OverspeedDetector:

    def __init__(self, overspeedparams, numsatparams):
        self.update(overspeedparams, numsatparams)
        self.reset()

    def update(self, overspeedparams, numsatparams):
        self.threshold_input = float(overspeedparams[0])
        self.use_percentage = self.threshold_input < 1  
        self.minimumnumsat = int(numsatparams)

    def reset(self):
        self.isoverspeed = False
        self.iswarning = False

    def process(self, speed, maxroadspeed, numsat, restricted, highrisk):
        isvalidnumsat = (numsat >= self.minimumnumsat)
        if speed > maxroadspeed and isvalidnumsat:
            self.isoverspeed = True
        if not self.isoverspeed:
            if self.use_percentage:
                diffratio = speed / maxroadspeed
                if diffratio >= self.threshold_input:
                    self.iswarning = True
            else:
                threshold_speed = maxroadspeed - self.threshold_input
                if speed >= threshold_speed and isvalidnumsat:
                    self.iswarning = True

    def getresults(self):
        return self.isoverspeed, self.iswarning

    def draw(self, frame):
        return frame

    def detect(self, frame, speed, maxroadspeed, numsat, restricted, highrisk):
        self.reset()

        if speed is None:
            return self.getresults()
        
        self.process(speed, maxroadspeed, numsat, restricted, highrisk)
        
        return self.getresults()
