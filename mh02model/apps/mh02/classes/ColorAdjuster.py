import numpy as np
import cv2

class ColorAdjuster:

    def __init__(self):
        pass

    def adjust_LAB(self, img):
        if img is None:
            return None
        
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=0.25, tileGridSize=(8,8))
        cl = clahe.apply(l_channel)
        limg = cv2.merge((cl,a,b))
        enhanced_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        return enhanced_img

    def adjust_Gamma(self, img, gamma=1.0):
        if img is None:
            return None
        
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(img, table)

    def adjust_OverExposed(self, img):
        if img is None:
            return None
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 21, 15)
        result = img.copy()
        result[thresh==255] = (255,255,255)
        return result

    def adjust_Binary(self, img):
        if img is None:
            return None
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:,:,2]
        T = cv2.ximgproc.niBlackThreshold(gray, maxValue=255, type=cv2.THRESH_BINARY_INV, blockSize=81, k=0.1, binarizationMethod=cv2.ximgproc.BINARIZATION_WOLF)
        grayb = (gray > T).astype("uint8") * 255
        return grayb