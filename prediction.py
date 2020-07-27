from mxnet import gluon
import requests
import mxnet as mx
from PIL import Image
import numpy as np
import json
import pickle
import base64
import time
import mysql.connector as mysql
import _thread
import threading 
import gzip

passFile = open("pass.txt","r")
mysql_pass = passFile.readline()
passFile.close()

class Predict():
    def __init__(self, isLocal):
        self.db = mysql.connect(
            host="localhost", user="root", passwd=mysql_pass, database="test")
        self.cursor = self.db.cursor()
        self.databaseName = "cameraDatabaseFinal7"
        if(isLocal):
            self.ctx = mx.gpu() if mx.context.num_gpus() else mx.cpu()
            self.net = self.get_model()
        self.image_extension=".jpg"

    def getNames(self):
        self.db.reconnect()
        query = """SELECT frameID
                FROM """ + self.databaseName + """
                WHERE process_flag=0
                ORDER BY SUBSTRING(frameID, 7) 
                LIMIT 6"""
        self.cursor.execute(query)
        return self.cursor.fetchall()
    
    def read_pics_api(self, img_names):
        imgs = []

        for name in img_names:
            im = Image.open("./FRAMES/" + name[0] + self.image_extension)
            im = (np.array(im)).reshape(256, 256, 3)
            imgs.append(im)

        return imgs
    
    def predict_api(self, imageNames):
        # """file = open('/home/karan/conv/foo.b64', 'rb')

        # temp = file.read()

        # """
        imgs = self.read_pics_api(imageNames)

        l = []

        print(len(imgs))

        for i in range(len(imgs)):

            dictionary = {}
            dictionary['name'] = imageNames[i][0]

            dictionary['data'] = [imgs[i]]

            l.append(dictionary)

        temp = pickle.dumps(l)
        temp = base64.b64encode(temp)
        temp = gzip.compress(temp)

        # """with open("imgs.gz", "wb") as f:
        #     f.write(temp)"""

        start = time.time()

        api_endpoint = "https://edh5g0f8h3.execute-api.ap-south-1.amazonaws.com/default/mxnet4"

        headers = {'content-encoding': 'gzip'}

        res = requests.post(url=api_endpoint, data=temp, headers=headers)

        print(time.time()-start)

        return json.loads(res.content.decode('utf-8'))

    def read_pics_local(self, img_names):
        imgs = []
        # print (img_names)
        for name in img_names:
            im = Image.open(
                './FRAMES/'+name[0]+self.image_extension)
            im = (np.array(im)).reshape(256, 256, 3)
            imgs.append(im)

        imgs = np.stack(imgs, axis=0)

        return mx.nd.array(imgs)

    def get_model(self):
        net = gluon.nn.SymbolBlock.imports("new_ssd_512_mobilenet1.0_voc-symbol.json", [
                                           'data'], "new_ssd_512_mobilenet1.0_voc-0000.params", ctx=self.ctx)
        return net

    def predict_local(self, img_names):

        x = self.read_pics_local(img_names)

        # net = get_model()

        idx, prob, bbox = self.net(x)
        idx = idx.asnumpy()
        prob = prob.asnumpy()
        bbox = bbox.asnumpy()
        detection = idx.shape[1]
        pred = {}

        for i in range(len(img_names)):
            ctr = 0
            temp = []
            for k in range(detection):
                if idx[i][k][0] == 14.0 and ctr < 10 and prob[i][k][0] >= 0.4:
                    ctr += 1
                    cords = bbox[i][k].tolist()
                    temp.append((int((cords[0]+cords[2])/2), int(cords[3])))

            pred.update({img_names[i][0]: temp})

        return pred

    def getStringFromPoints(self, points):
        pointString = ''
        for point in points:
            mainString = str(point[0])+' '+str(point[1])
            if(len(pointString) != 0):
                pointString = pointString+','+mainString
            else:
                pointString = mainString
        return pointString

    def editDatabase(self, data):
        for name, coords in data.items():
            pointsString = self.getStringFromPoints(coords)
            self.db.reconnect()
            query = """UPDATE """+self.databaseName + """
                    SET 
                        coordinates=%s,
                        process_flag=1
                    WHERE 
                        frameID=%s"""
            values = (pointsString, name)
            self.cursor.execute(query, values)
            self.db.commit()


# if __name__ == "__main__":
#     # local
#     # model=Predict(True)
#     # imageNames=model.getNames()
#     # if(len(imageNames)>10):
#     #     prediction=model.predict_local(imageNames)
#     #     model.editDatabase(prediction)

#     # api
#     model = Predict(False)
#     imageNames = model.getNames()
#     prediction = model.predict_api(imageNames)
#     # model.editDatabase(prediction)
#     print(prediction)


locks = []

def startOnePrediction(imageNames, lambda_number, lockobject):
    # print("LAMBDA NUMBER")
    # print (lambda_number)
    # print("A")
    print(imageNames)
    model=Predict(False)
    prediction=model.predict_api(imageNames)
    model.editDatabase(prediction)
    print("LAMBDA "+str(lambda_number)+" PREDICTION")
    print(prediction)
    lockobject.release()

def create_thread(img_names, lambda_number):
    # Create a lock and acquire it
    a_lock = _thread.allocate_lock()
    a_lock.acquire()

    # Store it in the global locks list
    locks.append(a_lock)

    # Pass it to the newly created thread which can release the lock once done
    _thread.start_new_thread(startOnePrediction, (img_names, lambda_number, a_lock))

num_lambda = 2
batch_size = 3
def beginPrediction():
    global locks
    model=Predict(True)
    while True:
        imageNames=model.getNames()
        # print("IMAGE NAMES")
        # print(imageNames)
        
        if(len(imageNames)>=batch_size*num_lambda):
            locks=[]
            # print (imageNames)
            for i in range(num_lambda):
                section = imageNames[i*batch_size:(i+1)*batch_size]
                create_thread(section, i)

            # Acquire all the locks, which means all the threads have released the locks
            all(lock.acquire() for lock in locks)
            
if __name__ == "__main__":
    beginPrediction()
        

