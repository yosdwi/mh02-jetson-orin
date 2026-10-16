import cv2
import numpy as np
import keras
import tensorflow as tf
import os
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing.image import img_to_array

class FaceMaskDetector:

    def __init__(self, threshold, modelpath):
        self.threshold = threshold
        self.maskNet = keras.models.load_model(modelpath + "mask_detector.model")
        self.reset()
        
    def update(self,threshold):
        self.threshold = threshold

    def reset(self):
        self.ismasked = False

    def draw(self,frame):
        return frame
    
    def getResults(self):
        return self.ismasked
    
    def preprocess(self,face):
        faces = []
        try:
            face = cv2.resize(face, (224, 224))
            face = img_to_array(face)
            face = preprocess_input(face)
            faces.append(face)
            return faces
        except:
            return faces

    def process(self,faces):
        if len(faces)<1:
            return None, None
        
        faces = np.array(faces, dtype="float32")
        preds = self.maskNet.predict(faces, batch_size=32)
        pred = preds[0]
        pred_mask,pred_nomask = pred[0],pred[1]
        return pred_mask,pred_nomask

    def postprocess(self,pred_mask):
        if pred_mask is None:
            return
        self.ismasked = (pred_mask >= self.threshold)

    def detect(self,face):
        faces = self.preprocess(face)
        pred_mask, pred_nomask = self.process(faces)
        self.postprocess(pred_mask)
        return self.getResults()