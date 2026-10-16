import collections
import datetime
import copy
import socket
import numpy
from datetime import datetime
from classes.Config import *

class MineAwarenessWarningCounter:

    def __init__(self, path, warningcode):
        self.config = Config(path)        
        self.warningcode = warningcode        
        self.reset()
        self.update()
                
    def reset(self):
        self.showalert = False
        self.lastwarningfound = None
        self.lastwarningnotfound = None

    def update(self):
        self.lastupdateparameters = datetime.now()
        warningparams = self.config.getValue(self.warningcode + "_PARAMS")
        params = warningparams.split("|")
        self.foundthresholdseconds, self.notfoundthresholdseconds, self.warningid, self.warningdesc, self.warningtext, self.warningsoundfile = int(params[0]), int(params[1]), params[2], params[3], params[4], params[5]

    def getAlertMessage(self):
        return self.warningtext
  
    def check(self,isvalid):
        curr = datetime.now()
        self.showalert = False

        # Check last update parameters
        updatesdiff = curr - self.lastupdateparameters
        if updatesdiff.seconds >= 5:
            self.update()

        # Check warning
        if isvalid:
            self.lastwarningnotfound = None

            if self.lastwarningfound is None:
                self.lastwarningfound = curr
                self.showalert = True
            
            founddiffseconds = curr - self.lastwarningfound
            if founddiffseconds.seconds >= self.foundthresholdseconds:
                self.lastwarningfound = curr
                self.showalert = True
        else:
            if self.lastwarningnotfound is None:
                self.lastwarningnotfound = curr
            
            notfounddiffseconds = curr - self.lastwarningnotfound
            if notfounddiffseconds.seconds >= self.notfoundthresholdseconds:
                self.reset()



