"""
    Copyright 2019 Brian Davis
    Visual-Template-free-Form-Parsting is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Visual-Template-free-Form-Parsting is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Visual-Template-free-Form-Parsting.  If not, see <https://www.gnu.org/licenses/>.
"""
import torch
import torch.utils.data
import numpy as np
import json


#import skimage.transform as sktransform
import os
import math
import cv2
from collections import defaultdict
import random
from random import shuffle


from utils.forms_annotations import fixAnnotations, getBBInfo
SKIP=['121','174']



def collate(batch):

    ##tic=timeit.default_timer()
    batch_size = len(batch)
    if batch_size==1 and 'imgPath' in batch[0]:
        return batch[0]#special evaluation mode that puts a whole image in a batch
    imageNames=[]
    data=[]
    labels=torch.ByteTensor(batch_size)
    NNs=[]
    bi=0
    for b in batch:
        imageNames.append(b['imgName'])
        data.append(b['data'])
        labels[bi] = int(b['label'])
        NNs.append(b['numNeighbors'])
        bi+=1

    return {
        "imgName": imageNames,
        'data': torch.cat(data,dim=0),
        'label': labels,
        'numNeighbors' : torch.cat(NNs,dim=0)
    }

class FormsFeaturePair(torch.utils.data.Dataset):
    """
    Class for reading Forms dataset and creating instances of pair features.
    """

    def __getResponseBBList(self,queryId,annotations):
        responseBBList=[]
        for pair in annotations['pairs']: #done already +annotations['samePairs']:
            if queryId in pair:
                if pair[0]==queryId:
                    otherId=pair[1]
                else:
                    otherId=pair[0]
                if otherId in annotations['byId']: #catch for gt error
                    responseBBList.append(annotations['byId'][otherId])
                #if not self.isSkipField(annotations['byId'][otherId]):
                #    poly = np.array(annotations['byId'][otherId]['poly_points']) #self.__getResponseBB(otherId,annotations)  
                #    responseBBList.append(poly)
        return responseBBList


    def __init__(self, dirPath=None, split=None, config=None, instances=None, test=False):
        if split=='valid':
            valid=True
            amountPer=0.25
        else:
            valid=False
        self.cache_resized=False
        if 'augmentation_params' in config:
            self.augmentation_params=config['augmentation_params']
        else:
            self.augmentation_params=None
        if 'no_blanks' in config:
            self.no_blanks = config['no_blanks']
        else:
            self.no_blanks = False
        if 'no_print_fields' in config:
            self.no_print_fields = config['no_print_fields']
        else:
            self.no_print_fields = False
        numFeats=10
        self.use_corners = config['corners'] if 'corners' in config else False
        self.no_graphics =  config['no_graphics'] if 'no_graphics' in config else False
        if self.use_corners=='xy':
            numFeats=18
        elif self.use_corners:
            numFeats=14
        self.swapCircle = config['swap_circle'] if 'swap_circle' in config else True
        self.onlyFormStuff = config['only_form_stuff'] if 'only_form_stuff' in config else False
        self.only_opposite_pairs = config['only_opposite_pairs'] if 'only_opposite_pairs' in config else False
        self.color = config['color'] if 'color' in config else True
        self.rotate = config['rotation'] if 'rotation' in config else True

        #self.simple_dataset = config['simple_dataset'] if 'simple_dataset' in config else False
        self.special_dataset = config['special_dataset'] if 'special_dataset' in config else None
        if 'simple_dataset' in config and config['simple_dataset']:
            self.special_dataset='simple'
        self.balance = config['balance'] if 'balance' in config else False

        self.eval = config['eval'] if 'eval' in config else False

        self.altJSONDir = config['alternate_json_dir'] if 'alternate_json_dir' in config else None
        

        #width_mean=400.006887263
        #height_mean=47.9102279201
        xScale=400
        yScale=50
        xyScale=(xScale+yScale)/2

        if instances is not None:
            self.instances=instances
        else:
            if self.special_dataset is not None:
                splitFile = self.special_dataset+'_train_valid_test_split.json'
            else:
                splitFile = 'train_valid_test_split.json'
            with open(os.path.join(dirPath,splitFile)) as f:
                readFile = json.loads(f.read())
                if type(split) is str:
                    groupsToUse = readFile[split]
                elif type(split) is list:
                    groupsToUse = {}
                    for spstr in split:
                        newGroups = readFile[spstr]
                        groupsToUse.update(newGroups)
                else:
                    print("Error, unknown split {}".format(split))
                    exit()
            groupNames = list(groupsToUse.keys())
            groupNames.sort()
            pair_instances=[]
            notpair_instances=[]
            for groupName in groupNames:
                imageNames=groupsToUse[groupName]
                if groupName in SKIP:
                    print('Skipped group {}'.format(groupName))
                    continue
                
                for imageName in imageNames:
                    org_path = os.path.join(dirPath,'groups',groupName,imageName)
                    #print(org_path)
                    if self.cache_resized:
                        path = os.path.join(self.cache_path,imageName)
                    else:
                        path = org_path
                    jsonPaths = [org_path[:org_path.rfind('.')]+'.json']
                    if self.altJSONDir is not None:
                        jsonPaths = [os.path.join(self.altJSONDir,imageName[:imageName.rfind('.')]+'.json')]
                    for jsonPath in jsonPaths:
                        annotations=None
                        if os.path.exists(jsonPath):
                            if annotations is None:
                                with open(os.path.join(jsonPath)) as f:
                                    annotations = json.loads(f.read())
                                #print(os.path.join(jsonPath))

                                #fix assumptions made in GTing
                                missedCount=fixAnnotations(self,annotations)

                            #print(path)
                            numNeighbors=defaultdict(lambda:0)
                            for id,bb in annotations['byId'].items():
                                if not self.onlyFormStuff or ('paired' in bb and bb['paired']):
                                    responseBBList = self.__getResponseBBList(id,annotations)
                                    responseIds = [bb['id'] for bb in responseBBList]
                                    for id2,bb2 in annotations['byId'].items():
                                        if id!=id2:
                                            pair = id2 in responseIds
                                            if pair:
                                                numNeighbors[id]+=1
                                                #well catch id2 on it's own pass
                            for id,bb in annotations['byId'].items():
                                if not self.onlyFormStuff or ('paired' in bb and bb['paired']):
                                    numN1 = numNeighbors[id]-1
                                    qX, qY, qH, qW, qR, qIsText, qIsField, qIsBlank, qNN = getBBInfo(bb,self.rotate,useBlankClass=not self.no_blanks)
                                    tlX = bb['poly_points'][0][0]
                                    tlY = bb['poly_points'][0][1]
                                    trX = bb['poly_points'][1][0]
                                    trY = bb['poly_points'][1][1]
                                    brX = bb['poly_points'][2][0]
                                    brY = bb['poly_points'][2][1]
                                    blX = bb['poly_points'][3][0]
                                    blY = bb['poly_points'][3][1]
                                    qH /= yScale #math.log( (qH+0.375*height_mean)/height_mean ) #rescaling so 0 height is -1, big height is 1+
                                    qW /= xScale #math.log( (qW+0.375*width_mean)/width_mean ) #rescaling so 0 width is -1, big width is 1+
                                    qR = qR/math.pi
                                    responseBBList = self.__getResponseBBList(id,annotations)
                                    responseIds = [bb['id'] for bb in responseBBList]
                                    for id2,bb2 in annotations['byId'].items():
                                        if id!=id2:
                                            numN2 = numNeighbors[id2]-1
                                            iX, iY, iH, iW, iR, iIsText, iIsField, iIsBlank, iNN  = getBBInfo(bb2,self.rotate,useBlankClass=not self.no_blanks)
                                            tlX2 = bb2['poly_points'][0][0]
                                            tlY2 = bb2['poly_points'][0][1]
                                            trX2 = bb2['poly_points'][1][0]
                                            trY2 = bb2['poly_points'][1][1]
                                            brX2 = bb2['poly_points'][2][0]
                                            brY2 = bb2['poly_points'][2][1]
                                            blX2 = bb2['poly_points'][3][0]
                                            blY2 = bb2['poly_points'][3][1]
                                            iH /=yScale #math.log( (iH+0.375*height_mean)/height_mean ) 
                                            iW /=xScale #math.log( (iW+0.375*width_mean)/width_mean ) 
                                            iR = iR/math.pi
                                            xDiff=iX-qX
                                            yDiff=iY-qY
                                            yDiff /= yScale #math.log( (yDiff+0.375*yDiffScale)/yDiffScale ) 
                                            xDiff /= xScale #math.log( (xDiff+0.375*xDiffScale)/xDiffScale ) 
                                            tlDiff = math.sqrt( (tlX-tlX2)**2 + (tlY-tlY2)**2 )/xyScale
                                            trDiff = math.sqrt( (trX-trX2)**2 + (trY-trY2)**2 )/xyScale
                                            brDiff = math.sqrt( (brX-brX2)**2 + (brY-brY2)**2 )/xyScale
                                            blDiff = math.sqrt( (blX-blX2)**2 + (blY-blY2)**2 )/xyScale
                                            tlXDiff = (tlX2-tlX)/xScale
                                            trXDiff = (trX2-trX)/xScale
                                            brXDiff = (brX2-brX)/xScale
                                            blXDiff = (blX2-blX)/xScale
                                            tlYDiff = (tlY2-tlY)/yScale
                                            trYDiff = (trY2-trY)/yScale
                                            brYDiff = (brY2-brY)/yScale
                                            blYDiff = (blY2-blY)/yScale
                                            pair = id2 in responseIds
                                            if pair or self.eval:
                                                instances = pair_instances
                                            else:
                                                instances = notpair_instances
                                            if self.altJSONDir is None:
                                                data=[qH,qW,qR,qIsText, iH,iW,iR,iIsText, xDiff, yDiff]
                                            else:
                                                data=[qH,qW,qR,qIsText,qIsField, iH,iW,iR,iIsText,iIsField, xDiff, yDiff]
                                            if self.use_corners=='xy':
                                                data+=[tlXDiff,trXDiff,brXDiff,blXDiff,tlYDiff,trYDiff,brYDiff,blYDiff]
                                            elif self.use_corners:
                                                data+=[tlDiff, trDiff, brDiff, blDiff]
                                            if qIsBlank is not None:
                                                data+=[qIsBlank,iIsBlank]
                                            if qNN is not None:
                                                data+=[qNN,iNN]
                                            instances.append( {
                                                'data': torch.tensor([ data ]),
                                                'label': pair,
                                                'imgName': imageName,
                                                'qXY' : (qX,qY),
                                                'iXY' : (iX,iY),
                                                'qHW' : (qH,qW),
                                                'iHW' : (iH,iW),
                                                'ids' : (id,id2),
                                                'numNeighbors': torch.tensor([ [numN1,numN2] ])
                                                } )
                            if self.eval:
                                #if evaluating, pack all instances for an image into a batch
                                datas=[]
                                labels=[]
                                qXYs=[]
                                iXYs=[]
                                qHWs=[]
                                iHWs=[]
                                nodeIds=[]
                                NNs=[]
                                numTrue=0
                                for inst in pair_instances:
                                    datas.append(inst['data'])
                                    labels.append(inst['label'])
                                    numTrue += inst['label']
                                    qXYs.append(inst['qXY'])
                                    iXYs.append(inst['iXY'])
                                    qHWs.append(inst['qHW'])
                                    iHWs.append(inst['iHW'])
                                    nodeIds.append(inst['ids'])
                                    NNs.append(inst['numNeighbors'])
                                if len(datas)>0:
                                    data = torch.cat(datas,dim=0),
                                else:
                                    data = torch.FloatTensor((0,numFeats))
                                if len(NNs)>0:
                                    NNs = torch.cat(NNs,dim=0)
                                else:
                                    NNs = torch.FloatTensor((0,2))
                                #missedCount=0
                                #for id1,id2 in annotations['pairs']:
                                #    if id1 not in annotations['byId'] or id2 not in annotations['byId']:
                                #        missedCount+=1
                                notpair_instances.append( {
                                    'data': data,
                                    'label': torch.ByteTensor(labels),
                                    'imgName': imageName,
                                    'imgPath' : path,
                                    'qXY' : qXYs,
                                    'iXY' : iXYs,
                                    'qHW' : qHWs,
                                    'iHW' : iHWs,
                                    'nodeIds' : nodeIds,
                                    'numNeighbors' : NNs,
                                    'missedRels': missedCount
                                    } )
                                pair_instances=[]
            self.instances = notpair_instances
            if self.balance and not self.eval:
                dif = len(notpair_instances)/float(len(pair_instances))
                print('not: {}, pair: {}. Adding {}x'.format(len(notpair_instances),len(pair_instances),math.floor(dif)))
                for i in range(math.floor(dif)):
                    self.instances += pair_instances
            else:
                self.instances += pair_instances



    def __len__(self):
        return len(self.instances)

    def __getitem__(self,index):
        return self.instances[index]
