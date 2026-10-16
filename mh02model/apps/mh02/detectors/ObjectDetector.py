import cv2
import numpy as np

class ObjectDetector:

    class Detection:

        def __init__(self, xmin, ymin, xmax, ymax, score, id, px_to_cm, actual_px, vehicle_speed):
            self.xmin = xmin
            self.ymin = ymin
            self.xmax = xmax
            self.ymax = ymax
            self.score = score
            self.id = id
            self.px_to_cm = px_to_cm
            self.actual_px = actual_px
            self.vehicle_speed = vehicle_speed

        def shape(self):
            # width, height
            return (self.xmax-self.xmin, self.ymax-self.ymin)

        def poslabel(self):
            return (int(self.xmin),int(self.ymin-10))

        def poscenter(self):
            xcenter = int(self.xmin + (self.xmax - self.xmin)/2)
            ycenter = int(self.ymin + (self.ymax - self.ymin)/2)
            return (xcenter,ycenter)

        def posmin(self):
            return (int(self.xmin), int(self.ymin))

        def posmax(self):
            return (int(self.xmax), int(self.ymax))

        def getdistancemeter(self):
            width_px = self.xmax-self.xmin
            width_ratio = 0
            if width_px > 0:
                width_ratio = self.actual_px/width_px
            return width_ratio

        def getdistancesecond(self):
            if self.vehicle_speed<1:
                return 0
            
            distance_meter = self.getdistancemeter()
            distance_kilometer = (distance_meter/1000)
            vehicle_time_hour = 0
            if self.vehicle_speed>0:
                vehicle_time_hour = (distance_kilometer/self.vehicle_speed)
            vehicle_time_second = (vehicle_time_hour * 3600)
            return vehicle_time_second

    class YOLOV4Tiny:

        def __init__(self, input_size, threshold, object_ids, px_to_cm, object_actual_pxs):
            self.input_size = input_size # (416, 416, 3)
            self.threshold = threshold
            self.object_ids = object_ids 
            self.px_to_cm = px_to_cm
            self.object_actual_pxs = object_actual_pxs
            self.coords = 4
            self.classes = 80
            self.bbox_size = (self.coords + 1 + self.classes)
            self.sides = [26,26]
            self.num = 2
            self.anchors = [23.0, 27.0, 37.0, 58.0, 81.0, 82.0]
            self.keep_aspect_ratio = False
            self.original_shape = None

            self.objects = []
        
        def sigmoid(self, x):
            return 1. / (1. + np.exp(-x))

        def parse_yolo_region(self,predictions,frame,vehicle_speed):
            h,w,c = frame.shape
            self.original_shape = (w,h)
            objects = []
            for row, col, n in np.ndindex(self.sides[0], self.sides[1], self.num):
                bbox = predictions[0, n * self.bbox_size:(n + 1) * self.bbox_size, row, col]

                object_probability = self.sigmoid(bbox[4])                 
                if object_probability < self.threshold:
                    continue
                class_probabilities = self.sigmoid(bbox[5:]) 

                x, y = self.sigmoid(bbox[:2])
                width, height = bbox[2:4]

                # Process raw value
                x = (col + x) / self.sides[1]
                y = (row + y) / self.sides[0]
                # Value for exp is very big number in some cases so following construction is using here
                try:
                    width = np.exp(width)
                    height = np.exp(height)
                except OverflowError:
                    continue
                width = width * self.anchors[2 * n] / self.input_size[0]
                height = height * self.anchors[2 * n + 1] / self.input_size[1]

                # Only 1 id per object
                class_id = np.argmax(class_probabilities)

                if not class_id in self.object_ids:
                    continue

                confidence = class_probabilities[class_id] * object_probability
                if confidence < self.threshold:
                    continue
                
                class_id_idx = self.object_ids.index(class_id)
                actual_px = self.object_actual_pxs[class_id_idx]
                objects.append(ObjectDetector.Detection(x - width / 2, y - height / 2, x + width / 2, y + height / 2,
                                        confidence.item(), class_id.item(), self.px_to_cm, actual_px, vehicle_speed))

            self.objects = objects

        def filter(self):
            detections = self.objects
            iou_threshold = self.threshold

            def iou(box_1, box_2):
                width_of_overlap_area = min(box_1.xmax, box_2.xmax) - max(box_1.xmin, box_2.xmin)
                height_of_overlap_area = min(box_1.ymax, box_2.ymax) - max(box_1.ymin, box_2.ymin)
                if width_of_overlap_area < 0 or height_of_overlap_area < 0:
                    area_of_overlap = 0
                else:
                    area_of_overlap = width_of_overlap_area * height_of_overlap_area
                box_1_area = (box_1.ymax - box_1.ymin) * (box_1.xmax - box_1.xmin)
                box_2_area = (box_2.ymax - box_2.ymin) * (box_2.xmax - box_2.xmin)
                area_of_union = box_1_area + box_2_area - area_of_overlap
                if area_of_union == 0:
                    return 0
                return area_of_overlap / area_of_union

            detections = sorted(detections, key=lambda obj: obj.score, reverse=True)
            for i in range(len(detections)):
                if detections[i].score == 0:
                    continue
                for j in range(i + 1, len(detections)):
                    # We perform IOU only on objects of same class
                    if detections[i].id != detections[j].id:
                        continue

                    if iou(detections[i], detections[j]) > iou_threshold:
                        detections[j].score = 0

            self.objects = [det for det in detections if det.score > 0]

        def resize_detections(self):
            detections = self.objects
            original_shape = self.original_shape
            for detection in detections:
                detection.xmin *= original_shape[0]
                detection.xmax *= original_shape[0]
                detection.ymin *= original_shape[1]
                detection.ymax *= original_shape[1]
            self.objects = detections
            return self.objects

        def process(self,outputs,frame,vehicle_speed):
            self.parse_yolo_region(outputs,frame,vehicle_speed)
            self.filter()
            return self.resize_detections()

    class Vehicle:
        
        def __init__(self,unit_actual_px):
            self.unit_actual_px = unit_actual_px

        def checkrelativepos(self,h,w,obj,adjustpoint,min_distance_sec):
            adjx,adjy = adjustpoint
            distance_meter = int(obj.getdistancemeter())
            
            if distance_meter <= 0:
                distance_meter = 1

            self.unit_relative_px = int(self.unit_actual_px/distance_meter)

            diffw = w-self.unit_relative_px
            diffwleft = int(diffw/2)
            diffwright = diffwleft
            self.xmin = diffwleft
            self.xmax = self.xmin + self.unit_relative_px
            self.xmin = self.xmin + adjx
            self.xmax = self.xmax + adjx

            self.ymax = obj.posmax()[1]
            self.ymin = self.ymax - self.unit_relative_px
            self.ymin = self.ymin + adjy
            self.ymax = self.ymax + adjy

            # Check if collision
            is_collision = False
            objxmin,objymin = obj.posmin()
            objxmax,objymax = obj.posmax()
            is_collision_obj_to_vehicle = ((objxmin >= self.xmin and objxmin <= self.xmax) or (objxmax >= self.xmin and objxmax <= self.xmax))
            is_collision_vehicle_to_obj = (self.xmin >= objxmin and self.xmax <= objxmax)
            is_collision_by_distance_sec = (round(obj.getdistancesecond())<=round(min_distance_sec))
            
            is_collision = ((is_collision_obj_to_vehicle or is_collision_vehicle_to_obj) and is_collision_by_distance_sec)
            return [(self.xmin,self.ymin),(self.xmax,self.ymax),is_collision]

    def __init__(self,mh02config,input_blob,output_blob,exec_net,modelheight,modelwidth):
        self.mh02config = mh02config
        self.modelheight = modelheight
        self.modelwidth = modelwidth
        self.input_blob = input_blob
        self.output_blob = "conv2d_20/BiasAdd/Add" #output_blob
        self.exec_net = exec_net

        self.object_ids = [0,2,5,7] # 0,2,5,7 => person, car, bus, truck
        self.object_actual_pxs = [100,440,640,640] # object width in pixel in 1 meter

        self.getconfigs()
        self.reset()

        self.model_detector = ObjectDetector.YOLOV4Tiny((self.modelheight,self.modelwidth,3),self.threshold,self.object_ids,self.px_to_cm,self.object_actual_pxs)
    
    def getconfigs(self):
        self.threshold = float(self.mh02config.getvalue("object_threshold"))
        self.person_threshold = float(self.mh02config.getvalue("pedestrian_threshold"))
        self.min_distance_sec = int(self.mh02config.getvalue("min_distance_sec"))
        self.px_to_cm = float(self.mh02config.getvalue("px_to_cm")) # 1 pixel = 0.5 cm
        self.unit_actual_px = int(self.mh02config.getvalue("unit_actual_px"))
        self.adjustpoint = (int(self.mh02config.getvalue("adjustpoint_x")),int(self.mh02config.getvalue("adjustpoint_y")))
        self.front_spot_meter = float(self.mh02config.getvalue("front_spot_meter"))

    def preprocess(self,frame):
        h,w,c = frame.shape
        self.front_spot_pos = self.getrelativespot(h,w,c,self.front_spot_meter,self.adjustpoint)

        self.img = cv2.resize(frame, (self.modelwidth, self.modelheight))
        self.img = self.img[np.newaxis, :, :, :]   # Batch size axis add
        self.img = self.img.transpose((0, 3, 1, 2))  # NHWC to NCHW
            
    def getoutputs(self):
        self.outputs = []
        self.outputs = self.exec_net.infer(inputs={self.input_blob: self.img})
        self.outputs = self.outputs[self.output_blob]

    def postprocess(self,frame,vehicle_speed):
        self.objects = self.model_detector.process(self.outputs,frame,vehicle_speed)

    def getrelativespot(self,h,w,c,nearspotmeter,adjustpoint):
        adjx,adjy = adjustpoint
        unit_actual_px_near = int(self.unit_actual_px/nearspotmeter)
        diffw = w-unit_actual_px_near
        diffwleft = int(diffw/2)
        diffwright = diffwleft
        xmin = diffwleft
        xmax = xmin + unit_actual_px_near
        xmin = xmin + adjx
        xmax = xmax + adjx

        diffh = h-unit_actual_px_near
        diffhtop = int(diffh/2)
        diffhbottom = diffhtop
        ymin = diffhtop 
        ymax = (ymin + unit_actual_px_near)
        ymin = ymin + adjy
        ymax = ymax + adjy

        return ((xmin,ymin),(xmax,ymax))

    def drawfrontspot(self,frame,h,w,c,nearspotmeter,adjustpoint):
        color = (0,255,255)
        posmin,posmax = self.getrelativespot(h,w,c,nearspotmeter,adjustpoint)
        # frame = cv2.rectangle(frame, posmin, posmax, color, 2)


        # frame = cv2.line(frame, maxpos1, maxpos2, color, 2)
        # # frame = cv2.line(frame, maxpos1, minpos2, color, 2)
        return frame

    def draw(self,frame):
        if self.objects == None:
            return frame
        
        h,w,c = frame.shape

        frame = self.drawfrontspot(frame,h,w,c,self.front_spot_meter,self.adjustpoint)
        
        for obj in self.objects:
            
            # Vehicle Relative Pos
            vehicle = ObjectDetector.Vehicle(self.unit_actual_px)
            relative_pos = vehicle.checkrelativepos(h,w,obj,self.adjustpoint,self.min_distance_sec)
            color = (0,255,0)
            color_obj = (0,255,0)
            if relative_pos[2]:
                color_obj = (0,255,255)
                color = (0,0,255)
                frame = cv2.rectangle(frame, relative_pos[0], relative_pos[1], color, 2) # -1 for fill

            # Draw object
            frame = cv2.rectangle(frame, obj.posmin(), obj.posmax(), color_obj, 1)
            frame = cv2.putText(frame, 
                            str(obj.id) + " (" + str(int(obj.score*100)) + ") " + 
                            str(round(obj.getdistancemeter())) + "m, " +
                            str(round(obj.getdistancesecond())) + "s", obj.poslabel(), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                            color_obj, 1, cv2.LINE_AA)

        return frame

    def reset(self):
        self.img = None
        self.outputs = []
        self.objects = None
        self.is_collision = False

        self.collision_objects = []
        self.is_collision_object = False 

        self.pedestrians = []
        self.is_collision_pedestrian = False

        self.front_spot_pos = None
    
    def getresults(self,frame):
        h,w,c = frame.shape

        coll_objects = []
        for obj in self.objects:
            # Vehicle Relative Pos
            vehicle = ObjectDetector.Vehicle(self.unit_actual_px)
            relative_pos = vehicle.checkrelativepos(h,w,obj,self.adjustpoint,self.min_distance_sec)
            if relative_pos[2]:
                
                if int(obj.id) > 0:
                    coll_objects.append(obj)               
                    self.collision_objects.append(obj)
                    self.is_collision_object = True
                else:
                    if obj.score > self.person_threshold:
                        coll_objects.append(obj)
                        self.pedestrians.append(obj)
                        self.is_collision_pedestrian = True
                    else:
                        print("PEDESTRIAN UNDER THRESHOLD:", obj.score, self.person_threshold)
            
        self.is_collision = (self.is_collision_object or self.is_collision_pedestrian)
        self.objects = coll_objects
        return self.objects, self.is_collision, self.is_collision_object, self.is_collision_pedestrian

    def updateparams(self,mh02config):
        self.mh02config = mh02config
        self.getconfigs()

    def detect(self,frame,vehicle_speed):
        self.reset()
        
        self.preprocess(frame.copy())
        self.getoutputs()
        self.postprocess(frame.copy(),vehicle_speed)

        return self.getresults(frame)