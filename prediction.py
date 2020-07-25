from mxnet import gluon
import mysql.connector as mysql
import mxnet as mx
from PIL import Image
# import boto3
import numpy as np
import json

class Predict():
    def __init__(self):
        self.db=mysql.connect(host="localhost",user="root",passwd="Shrinivas#100", database="test")
        self.cursor=self.db.cursor()
        self.databaseName="cameraDatabaseFinal"
        self.ctx = mx.gpu() if mx.context.num_gpus() else mx.cpu()
        self.net=self.get_model()
        
    def getNames(self):
        query="""SELECT frameID
                FROM """ +self.databaseName +"""
                WHERE process_flag=0
                ORDER BY SUBSTRING(frameID, 7) 
                LIMIT 40"""
        self.cursor.execute(query)
        return self.cursor.fetchall()
            
    def read_pics(self,img_names):
        imgs = []

        for name in img_names:
            im = Image.open('e:/SHRINIVAS/KGP/SocialDistancingUIDesktop/'+name[0]+".jpg")
            im = (np.array(im)).reshape(256, 256, 3)
            imgs.append(im)

        imgs = np.stack(imgs, axis=0)

        return mx.nd.array(imgs)


    def get_model(self):
        net = gluon.nn.SymbolBlock.imports("new_ssd_512_mobilenet1.0_voc-symbol.json", ['data'], "new_ssd_512_mobilenet1.0_voc-0000.params", ctx=self.ctx)
        return net

    def predict(self,img_names):

        x = self.read_pics(imageNames)

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
    
    def getStringFromPoints(self,points):
        pointString=''
        for point in points:
            mainString=str(point[0])+' '+str(point[1])
            if(len(pointString)!=0):
                pointString=pointString+','+mainString
            else:
                pointString=mainString
        return pointString

    def editDatabase(self,data):
        for name,coords in data.items():
            pointsString=self.getStringFromPoints(coords)
            query = """UPDATE """+self.databaseName +"""
                    SET 
                        coordinates=%s,
                        process_flag=1
                    WHERE 
                        frameID=%s"""
            values=(pointsString,name)
            self.cursor.execute(query,values)
        self.db.commit()

if __name__ == "__main__":
    model=Predict()
    imageNames=model.getNames()
    if(len(imageNames)>10):
        prediction=model.predict(imageNames)
        model.editDatabase(prediction)