from mxnet import gluon
import requests
import mxnet as mx
from PIL import Image
import numpy as np
import json
import pickle
import base64
import time
# import mysql.connector as mysql
import _thread
import threading
import gzip
# import transformation
from itertools import combinations
import os
from cryptography.fernet import Fernet
import ast
import pandas as pd
import datetime
import cv2
# import torch
import argparse
from utils import *
from flask import Flask, render_template, Response, jsonify, request
from playsound import playsound
# passFile = open("pass.txt","r")
# mysql_pass = passFile.readline()
# passFile.close()

# app = Flask(__name__)
# global_frame = None
two_up = os.path.dirname(os.path.dirname(__file__))
# two_up = '/home/yantrakaar/Yantrakar_Client' #os.path.dirname(os.path.dirname(__file__))


class Predict():
    def __init__(self, isLocal):
        # self.db = mysql.connect(
        #     host="localhost", user="root", passwd=mysql_pass, database="test")
        # self.cursor = self.db.cursor()
        # self.databaseName = "cameraDatabaseFinal"
        if (isLocal):
            self.ctx = mx.gpu()  #if mx.context.num_gpus() else mx.cpu()
            self.net_human = self.get_model_human()
            if torch.cuda.is_available():
                self.device = 'cuda:0'
            else:
                self.device = 'cpu'
            self.net_mask = self.get_model_mask()
        self.image_extension = ".png"
        self.getDataJson()

        self.feature_map_sizes = [[45, 45], [23, 23], [12, 12], [6, 6], [4, 4]]
        self.anchor_sizes = [[0.04, 0.056], [0.08, 0.11], [0.16, 0.22],
                             [0.32, 0.45], [0.64, 0.72]]
        self.anchor_ratios = [[1, 0.62, 0.42]] * 5
        self.anchors = generate_anchors(self.feature_map_sizes,
                                        self.anchor_sizes, self.anchor_ratios)

        self.anchors_exp = np.expand_dims(self.anchors, axis=0)

        self.encryptionKey = b'gkmrxai04WhOcWj3EGl-2Io58Q8biOWOytdQbPhNYGU='

        self.getSystemConfiguration()
        # self.camera = cv2.VideoCapture(two_up + "/test_video/top.mp4")

    def getSystemConfiguration(self):
        with open(two_up + '/DATA/userSetting.txt', 'r') as file:
            data = file.read()
        cipher = Fernet(self.encryptionKey)
        userSetting = ast.literal_eval(
            (cipher.decrypt(data.encode('utf-8'))).decode('utf-8'))
        self.activationKey = userSetting["activationKey"]
        self.apiURL = userSetting["apiURL"]
        self.numberOfLambda = userSetting["numberOfLambda"]

    def read_pics_human(self, im):
        imgs = []
        im = cv2.resize(im, (200, 200))
        im = (np.array(im)).reshape(200, 200, 3)
        imgs.append(im)
        imgs = np.stack(imgs, axis=0)

        return mx.nd.array(imgs, self.ctx)

    def read_pics_mask(self, im):

        imgs = []
        fin_imgs = []

        im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        # imgs.append(im)
        im = cv2.resize(im, (360, 360))
        im = im / 255.0
        im = im.transpose((2, 0, 1))
        fin_imgs.append(im)

        imgs_transformed = np.stack(fin_imgs, axis=0)
        imgs_transformed = torch.tensor(imgs_transformed).float().to(
            self.device)

        return imgs_transformed

    def get_model_human(self):
        net = gluon.nn.SymbolBlock.imports(
            two_up + "/DATA/new_ssd_512_mobilenet1.0_voc-symbol.json",
            ['data'],
            two_up + "/DATA/new_ssd_512_mobilenet1.0_voc-0000.params",
            ctx=self.ctx)
        return net

    def get_model_mask(self):
        model = torch.load(two_up + '/models/model360.pth')
        model.to(self.device)
        return model

    def predict_mask(self, im):
        x = self.read_pics_mask(im)
        y_bboxes, y_scores, = self.net_mask.forward(x)

        y_bboxes_output = y_bboxes.detach().cpu().numpy()
        y_cls_output = y_scores.detach().cpu().numpy()

        pred = {}
        #print(y_bboxes_output)
        #print(y_cls_output)

        # for i in range(x.shape[0]):

        height, width, _ = im.shape

        # remove the batch dimension, for batch is always 1 for inference.
        y_bboxes = decode_bbox(self.anchors_exp, y_bboxes_output)[0]
        y_cls = y_cls_output[0]

        # To speed up, do single class NMS, not multiple classes NMS.
        bbox_max_scores = np.max(y_cls, axis=1)
        bbox_max_score_classes = np.argmax(y_cls, axis=1)

        # keep_idx is the alive bounding box after nms.
        keep_idxs = single_class_non_max_suppression(
            y_bboxes,
            bbox_max_scores,
            conf_thresh=0.5,
            iou_thresh=0.5,
        )

        output_info_class_id = []
        output_info_conf = []
        output_info_cords = []
        print(keep_idxs)

        for idx in keep_idxs:
            conf = float(bbox_max_scores[idx])
            class_id = bbox_max_score_classes[idx]
            bbox = y_bboxes[idx]
            # clip the coordinate, avoid the value exceed the image boundary.
            xmin = max(0, int(bbox[0] * width))
            ymin = max(0, int(bbox[1] * height))
            xmax = min(int(bbox[2] * width), width)
            ymax = min(int(bbox[3] * height), height)

            output_info_class_id.append(class_id)
            output_info_conf.append(conf)
            output_info_cords.append([xmin, ymin, xmax, ymax])

        temp = {
            'id': output_info_class_id,
            'prob': output_info_conf,
            'bbox': output_info_cords
        }

        print(output_info_conf)
        # pred.update({img_names[i]: temp})

        return temp

    def predict_human(self, im):
        x = self.read_pics_human(im)
        idx, prob, bbox = self.net_human(x)
        idx = idx.asnumpy()
        prob = prob.asnumpy()
        bbox = bbox.asnumpy()
        detection = idx.shape[1]
        # pred = {}

        # for i in range(len(img_names)):
        ctr = 0
        temp = []
        for k in range(detection):
            if idx[0][k][0] == 14.0 and ctr < 10 and prob[0][k][0] >= 0.4:
                ctr += 1
                cords = bbox[0][k].tolist()
                temp.append((int((cords[0] + cords[2]) / 2), int(cords[3])))

            # pred.update({im: temp})
        return temp

    def findWorldDistance(self, matrix, worldRatio, point1, point2):
        point1 = np.asarray(point1).reshape((2, 1))
        point2 = np.asarray(point2).reshape((2, 1))

        if (worldRatio == None):
            return -1

        temp = np.zeros((3, 1))
        temp[0][0] = point1[0][0]
        temp[1][0] = point1[1][0]
        temp[2][0] = 1

        cornerInTopView = matrix.dot(temp)
        corner1 = np.zeros((2, 1))
        corner1[0][0] = cornerInTopView[0][0] / cornerInTopView[2][0]
        corner1[1][0] = cornerInTopView[1][0] / cornerInTopView[2][0]

        temp = np.zeros((3, 1))
        temp[0][0] = point2[0][0]
        temp[1][0] = point2[1][0]
        temp[2][0] = 1

        cornerInTopView = matrix.dot(temp)
        corner2 = np.zeros((2, 1))
        corner2[0][0] = cornerInTopView[0][0] / cornerInTopView[2][0]
        corner2[1][0] = cornerInTopView[1][0] / cornerInTopView[2][0]

        if (worldRatio != None):
            pixelDistance = np.sqrt(((corner1[0][0] - corner2[0][0])**2) +
                                    ((corner1[1][0] - corner2[1][0])**2))
            worldDistance = worldRatio * pixelDistance
            return worldDistance
        else:
            return -1

    def getDataJson(self):
        with open(two_up + '/DATA/cameraDatabase.json', 'r') as jsonFile:
            cameraData = json.load(jsonFile)

        self.cameraDataProcessed = {}

        for cameraKey, cameraValue in cameraData.items():
            if (cameraValue["CalibrationData"] != None):
                cameraMatrix = np.array(
                    cameraValue["CalibrationData"]["calibrationMatrix"])
                self.cameraDataProcessed.update({
                    cameraKey: {
                        "calibrationMatrix": cameraMatrix,
                        "worldRatio":
                        cameraValue["CalibrationData"]["worldRatio"]
                    }
                })
            else:
                self.cameraDataProcessed.update({
                    cameraKey: {
                        "calibrationMatrix": None,
                        "worldRatio": None
                    }
                })

    def processData(self, im, dbData, mask_points):
        violatedPointsData = {}

        height, width, _ = im.shape

        points = combinations(dbData, 2)
        violatedPoints = []
        distancingViolated = False
        for point1, point2 in points:
            point1_scaled = (int(point1[0] * width / 256),
                             int(point1[1] * height / 256))
            point2_scaled = (int(point2[0] * width / 256),
                             int(point2[1] * height / 256))
            distance = self.findWorldDistance(
                self.cameraDataProcessed["000001"]["calibrationMatrix"],
                self.cameraDataProcessed["000001"]["worldRatio"],
                point1_scaled, point2_scaled)
            if (point1 == point2):
                continue
            elif (distance == -1):
                continue
            elif (distance < 150):
                violatedPoints.append((point1_scaled, point2_scaled))
        violatedPointsData.update({"000001": violatedPoints})

        for _, violatedPoints in violatedPointsData.items():
            if (len(violatedPoints) > 0):
                distancingViolated = True
                for pointpair in violatedPoints:
                    im = cv2.line(im, pointpair[0], pointpair[1], (0, 0, 100))

        maskViolated = False
        for box in mask_points['bbox']:
            maskViolated = True
            cv2.rectangle(im, (box[0], box[1]), (box[2], box[3]),
                          color=(0, 0, 255))

        # if violated==True:
        #cv2.imwrite(two_up+ "/FRAMES/" + str(time.clock())+".jpg", im)

        #cv2.imshow("output", im)
        # cv2.waitKey(1)
        return maskViolated, distancingViolated


csv_didnt_open = {}
# initialised here so that it basic model import does
# wait for client connection
model = Predict(True)


# locks = []
def startOnePrediction(im):
    global csv_didnt_open, model
    # avg = 0
    # num_imgs = 0
    # while True:
    # num_imgs += 1
    # starttime = time.clock()
    # mask_points = model.predict_mask(im)
    mask_points={}
    violatedPoints_human = model.predict_human(im)
    print("PREDICTION MASK")
    print(mask_points)
    print("PREDICTION HUMAN")
    print(violatedPoints_human)
    return model.processData(im, violatedPoints_human, mask_points)


    # avg = avg*(num_imgs-1)/num_imgs + 1/(time.clock() - starttime)/num_imgs
    # print(avg)
def start():
    cap = cv2.VideoCapture(two_up + "/test_video/top.mp4")
    while True:
        ret, frame = cap.read()
        if ret:
            isMask, isDist = startOnePrediction(frame)
        if isMask:
            playsound(two_up+"/DATA/maskAudio.mp3")
        if isDist:
            playsound(two_up+"/DATA/distancingAudio.mp3")
        cv2.waitKey(1)

def video_stream():
    global global_frame

    cap = cv2.VideoCapture(0)
    isFirst = True

    while True:
        ret, frame1 = cap.read()

        if ret:
            doSend = startOnePrediction(frame1)
            if isFirst:
                isFirst = False
                ret, jpeg = cv2.imencode('.jpg', frame1)
                frame = jpeg.tobytes()
            if doSend:
                ret, jpeg = cv2.imencode('.jpg', frame1)
                frame = jpeg.tobytes()
        else:
            frame = None

        # frame streaming part
        if frame != None:
            global_frame = frame
            yield (b'--frame\r\n'
                   b'Content-Type:image/jpeg\r\n'
                   b'Content-Length: ' + str(len(frame)).encode() + b'\r\n'
                   b'\r\n' + frame + b'\r\n')
        else:
            yield (b'--frame\r\n'
                   b'Content-Type:image/jpeg\r\n'
                   b'Content-Length: ' + str(len(global_frame)).encode() +
                   b'\r\n'
                   b'\r\n' + global_frame + b'\r\n')
        cv2.waitKey(1)


# @app.route('/video_feed')
# # This is the video streaming Route. Used in src attribute of image tag in HTML
# # To stream the video
# def video_feed():
#     """Video streaming route. Put this in the src attribute of an img tag."""
#     return Response(video_stream(),
#                     mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    start()
#     app.run(host='0.0.0.0', debug=False, threaded=True, use_reloader=False)
