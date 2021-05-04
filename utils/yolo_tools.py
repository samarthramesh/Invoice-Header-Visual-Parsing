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
#from model.yolo_loss import bbox_iou
import math

def non_max_sup_iou(pred_boxes,thresh_conf=0.5, thresh_inter=0.5, hard_limit=300):
    return non_max_sup_(pred_boxes,thresh_conf, thresh_inter, max_intersection, hard_limit)
def non_max_sup_dist(pred_boxes,thresh_conf=0.5, thresh_dist=0.9, hard_limit=300):
    return non_max_sup_(pred_boxes,thresh_conf, thresh_dist*-1, dist_neg, hard_limit)
def non_max_sup_(pred_boxes,thresh_conf, thresh_loc, loc_metric, hard_limit):
    #rearr = [0,1,2,5,4,3]
    #for i in range(6,pred_boxes.shape[2]):
    #    rearr.append(i)
    #pred_boxes = pred_boxes[:,:,rearr]
    to_return=[]
    for b in range(pred_boxes.shape[0]):
        
        #allIOU = bbox_iou(
        above_thresh = []
        for i in range(pred_boxes.shape[1]):
            if pred_boxes[b,i,0]>thresh_conf:
                above_thresh.append( (pred_boxes[b,i,0], i) )
        above_thresh.sort(key=lambda a: a[0], reverse=True)
        above_thresh = above_thresh[:hard_limit]
        li = 0
        while li<len(above_thresh)-1:
            i=above_thresh[li][1]
            loc_measures = loc_metric(pred_boxes[b,i,1:6],pred_boxes[b,[x[1] for x in above_thresh[li+1:]],1:6])
            #ious = bbox_iou(pred_boxes[b,i:i+1,1:5],pred_boxes[b,[x[1] for x in above_thresh[li+1:]],1:5], x1y1x2y2=False)
            to_remove=[]
            for lj in range(len(above_thresh)-1,li,-1):
                j=above_thresh[lj][1]
                #if bbox_iou( pred_boxes[b,i:i+1,1:5], pred_boxes[b,j:j+1,1:5], x1y1x2y2=False) > thresh_iou:
                if loc_measures[lj-(li+1)] > thresh_loc:
                    to_remove.append(lj)
            #to_remove.reverse()
            for index in to_remove:
                del above_thresh[index]
            li+=1

        best = pred_boxes[b,[x[1] for x in above_thresh],:]
        to_return.append(best)#[:,rearr])
    return to_return


def max_intersection(query_box, candidate_boxes):
    q_x1, q_x2 = query_box[0]-query_box[4], query_box[0]+query_box[4]
    q_y1, q_y2 = query_box[1]-query_box[3], query_box[1]+query_box[3]
    c_x1, c_x2 = candidate_boxes[:,0]-candidate_boxes[:,4], candidate_boxes[:,0]+candidate_boxes[:,4]
    c_y1, c_y2 = candidate_boxes[:,1]-candidate_boxes[:,3], candidate_boxes[:,1]+candidate_boxes[:,3]

    inter_rect_x1 = torch.max(q_x1, c_x1)
    inter_rect_x2 = torch.min(q_x2, c_x2)
    inter_rect_y1 = torch.max(q_y1, c_y1)
    inter_rect_y2 = torch.min(q_y2, c_y2)

    inter_area = torch.clamp(inter_rect_x2 - inter_rect_x1 + 1, min=0) * torch.clamp(
            inter_rect_y2 - inter_rect_y1 + 1, min=0 )

    q_area = (q_x2 - q_x1 + 1) * (q_y2 - q_y1 + 1)
    c_area = (c_x2 - c_x1 + 1) * (c_y2 - c_y1 + 1)
    min_area = torch.min(q_area,c_area)
    #import pdb; pdb.set_trace()

    return inter_area/min_area

def dist_neg(query_box, candidate_boxes):
    #convert boxes to points
    sin_r = torch.sin(query_box[2])
    cos_r = torch.cos(query_box[2])
    qlx = query_box[0] - cos_r*query_box[4]
    qly = query_box[1] + sin_r*query_box[3]
    qrx = query_box[0] + cos_r*query_box[4]
    qry = query_box[1] - sin_r*query_box[3]
    qtx = query_box[0] - cos_r*query_box[4]
    qty = query_box[1] - sin_r*query_box[3]
    qbx = query_box[0] + cos_r*query_box[4]
    qby = query_box[1] + sin_r*query_box[3]
    query_points = torch.tensor([[qlx,qly,qrx,qry,qtx,qty,qbx,qby]])
    queryHW = (query_box[4]+query_box[3])/2
    #queryHW = torch.min(query_box[3:5])

    query_points = query_points.expand(candidate_boxes.size(0),8)
    queryHW = queryHW.expand(candidate_boxes.size(0))

    sin_r = torch.sin(candidate_boxes[:,2])
    cos_r = torch.cos(candidate_boxes[:,2])
    clx = candidate_boxes[:,0] - cos_r*candidate_boxes[:,4]
    cly = candidate_boxes[:,1] + sin_r*candidate_boxes[:,3]
    crx = candidate_boxes[:,0] + cos_r*candidate_boxes[:,4]
    cry = candidate_boxes[:,1] - sin_r*candidate_boxes[:,3]
    ctx = candidate_boxes[:,0] - cos_r*candidate_boxes[:,4]
    cty = candidate_boxes[:,1] - sin_r*candidate_boxes[:,3]
    cbx = candidate_boxes[:,0] + cos_r*candidate_boxes[:,4]
    cby = candidate_boxes[:,1] + sin_r*candidate_boxes[:,3]
    cand_points = torch.stack([clx,cly,crx,cry,ctx,cty,cbx,cby],dim=1)
    candHW = (candidate_boxes[:,4]+candidate_boxes[:,3])/2
    #candHW,_ = torch.min(candidate_boxes[:,3:5],dim=1)
    #compute distances
    normalization = (queryHW+candHW)/2.0

    deltas = query_points - cand_points
    dist = ((
            torch.norm(deltas[:,0:2],2,1) +
            torch.norm(deltas[:,2:4],2,1) +
            torch.norm(deltas[:,4:6],2,1) +
            torch.norm(deltas[:,6:8],2,1)
           )/normalization)**2
    return dist*-1

def allIOU(boxes1,boxes2, boxes1XYWH=[0,1,4,3]):
    b1_x1, b1_x2 = boxes1[:,boxes1XYWH[0]]-boxes1[:,boxes1XYWH[2]], boxes1[:,boxes1XYWH[0]]+boxes1[:,boxes1XYWH[2]]
    b1_y1, b1_y2 = boxes1[:,boxes1XYWH[1]]-boxes1[:,boxes1XYWH[3]], boxes1[:,boxes1XYWH[1]]+boxes1[:,boxes1XYWH[3]]
    b2_x1, b2_x2 = boxes2[:,0]-boxes2[:,4], boxes2[:,0]+boxes2[:,4]
    b2_y1, b2_y2 = boxes2[:,1]-boxes2[:,3], boxes2[:,1]+boxes2[:,3]

    #expand to make two dimensional, allowing every instance of boxes1
    #to be compared with every intsance of boxes2
    b1_x1 = b1_x1[:,None].expand(boxes1.size(0), boxes2.size(0))
    b1_y1 = b1_y1[:,None].expand(boxes1.size(0), boxes2.size(0))
    b1_x2 = b1_x2[:,None].expand(boxes1.size(0), boxes2.size(0))
    b1_y2 = b1_y2[:,None].expand(boxes1.size(0), boxes2.size(0))
    b2_x1 = b2_x1[None,:].expand(boxes1.size(0), boxes2.size(0))
    b2_y1 = b2_y1[None,:].expand(boxes1.size(0), boxes2.size(0))
    b2_x2 = b2_x2[None,:].expand(boxes1.size(0), boxes2.size(0))
    b2_y2 = b2_y2[None,:].expand(boxes1.size(0), boxes2.size(0))

    inter_rect_x1 = torch.max(b1_x1, b2_x1)
    inter_rect_x2 = torch.min(b1_x2, b2_x2)
    inter_rect_y1 = torch.max(b1_y1, b2_y1)
    inter_rect_y2 = torch.min(b1_y2, b2_y2)

    inter_area = torch.clamp(inter_rect_x2 - inter_rect_x1 + 1, min=0) * torch.clamp(
            inter_rect_y2 - inter_rect_y1 + 1, min=0 )

    b1_area = (b1_x2 - b1_x1 + 1) * (b1_y2 - b1_y1 + 1)
    b2_area = (b2_x2 - b2_x1 + 1) * (b2_y2 - b2_y1 + 1)
    iou = inter_area / (b1_area + b2_area - inter_area + 1e-16)
    return iou

def allDist(boxes1,boxes2):
    b1_x = boxes1[:,0]
    b1_y = boxes1[:,1]
    b2_x = boxes2[:,0]
    b2_y = boxes2[:,1]

    #expand to make two dimensional, allowing every instance of boxes1
    #to be compared with every intsance of boxes2
    b1_x = b1_x[:,None].expand(boxes1.size(0), boxes2.size(0))
    b1_y = b1_y[:,None].expand(boxes1.size(0), boxes2.size(0))
    b2_x = b2_x[None,:].expand(boxes1.size(0), boxes2.size(0))
    b2_y = b2_y[None,:].expand(boxes1.size(0), boxes2.size(0))

    return torch.sqrt( torch.pow(b1_x-b2_x,2) + torch.pow(b1_y-b2_y,2) )

def allBoxDistNeg(boxes1,boxes2):
    #convert boxes to points
    sin_r = torch.sin(boxes1[:,2])
    cos_r = torch.cos(boxes1[:,2])
    clx = boxes1[:,0] - cos_r*boxes1[:,4]
    cly = boxes1[:,1] + sin_r*boxes1[:,3]
    crx = boxes1[:,0] + cos_r*boxes1[:,4]
    cry = boxes1[:,1] - sin_r*boxes1[:,3]
    ctx = boxes1[:,0] - cos_r*boxes1[:,4]
    cty = boxes1[:,1] - sin_r*boxes1[:,3]
    cbx = boxes1[:,0] + cos_r*boxes1[:,4]
    cby = boxes1[:,1] + sin_r*boxes1[:,3]
    boxes1_points = torch.stack([clx,cly,crx,cry,ctx,cty,cbx,cby],dim=1)
    boxes1HW = (boxes1[:,4]+boxes1[:,3])/2


    sin_r = torch.sin(boxes2[:,2])
    cos_r = torch.cos(boxes2[:,2])
    clx = boxes2[:,0] - cos_r*boxes2[:,4]
    cly = boxes2[:,1] + sin_r*boxes2[:,3]
    crx = boxes2[:,0] + cos_r*boxes2[:,4]
    cry = boxes2[:,1] - sin_r*boxes2[:,3]
    ctx = boxes2[:,0] - cos_r*boxes2[:,4]
    cty = boxes2[:,1] - sin_r*boxes2[:,3]
    cbx = boxes2[:,0] + cos_r*boxes2[:,4]
    cby = boxes2[:,1] + sin_r*boxes2[:,3]
    boxes2_points = torch.stack([clx,cly,crx,cry,ctx,cty,cbx,cby],dim=1)
    boxes2HW = (boxes2[:,4]+boxes2[:,3])/2
    #candHW,_ = torch.min(candidate_boxes[:,3:5],dim=1)
    #compute distances

    boxes1_points = boxes1_points[:,None,:].expand(boxes1.size(0),boxes2.size(0),8)
    boxes2_points = boxes2_points[None,:,:].expand(boxes1.size(0),boxes2.size(0),8)
    boxes1HW = boxes1HW[:,None].expand(boxes1.size(0),boxes2.size(0))
    boxes2HW = boxes2HW[None,:].expand(boxes1.size(0),boxes2.size(0))
    normalization = (boxes1HW+boxes2HW)/2.0

    deltas = boxes1_points - boxes2_points
    dist = ((
        torch.norm(deltas[:,:,0:2],2,2) +
        torch.norm(deltas[:,:,2:4],2,2) +
        torch.norm(deltas[:,:,4:6],2,2) +
        torch.norm(deltas[:,:,6:8],2,2)
           )/normalization)**2
    return dist*-1
 
#input is tensors of shape [instance,(conf,x,y,rot,h,w)]
def AP_iou(target,pred,iou_thresh,numClasses=2,ignoreClasses=False,beforeCls=0,getClassAP=False):
    return AP_(target,pred,iou_thresh,numClasses,ignoreClasses,beforeCls,allIOU,getClassAP)
def AP_dist(target,pred,dist_thresh,numClasses=2,ignoreClasses=False,beforeCls=0,getClassAP=False):
    return AP_(target,pred,-dist_thresh,numClasses,ignoreClasses,beforeCls,allBoxDistNeg,getClassAP)
def AP_(target,pred,iou_thresh,numClasses,ignoreClasses,beforeCls,getLoc,getClassAP):
    #mAP=0.0
    #aps=[]
    precisions=[]
    recalls=[]

    #how many classes are there?
    if ignoreClasses:
        numClasses=1
    if len(target.size())>1:
        #numClasses=target.size(1)-13
        pass
    elif len(pred.size())>1 and pred.size(0)>0:
        #if there are no targets, we shouldn't be pred anything
        if ignoreClasses:
            #aps.append(0)
            ap=0
            precisions.append(0)
            recalls.append(1)
        else:
            #numClasses=pred.size(1)-6
            ap=0
            class_ap=[]
            for cls in range(numClasses):
                if (torch.argmax(pred[:,beforeCls+6:],dim=1)==cls).any():
                    #aps.append(0) #but we did for this class :(
                    ap+=0
                    precisions.append(0)
                    class_ap.append(0)
                else:
                    #aps.append(1) #we didn't for this class :)
                    ap+=1
                    precisions.append(1)
                    class_ap.append(1)
                recalls.append(1)
        if getClassAP:
            return ap/numClasses, precisions, recalls, class_ap
        else:
            return ap/numClasses, precisions, recalls
    else:
        if getClassAP:
            return 1, [1]*numClasses, [1]*numClasses, [1]*numClasses #we didn't for all classes :)
        else:
            return 1, [1]*numClasses, [1]*numClasses

    allScores=[]
    classScores=[[] for i in range(numClasses)]
    if len(pred.size())>1 and pred.size(0)>0:
        #This is an alternate metric that computes AP of all classes together
        #Your only a hit if you have the same class
        allIOUs = getLoc(target[:,0:],pred[:,1:])
        allHits = allIOUs>iou_thresh
        #evalute hits to see if they're valid (matching class)
        targetClasses_index = torch.argmax(target[:,13:13+numClasses],dim=1)
        predClasses = pred[:,beforeCls+6:beforeCls+6+numClasses]
        if predClasses.size(0)==0 or predClasses.size(1)==0:
            print('ERROR, zero sized predClasses: {}. pred is {}'.format(predClasses.size(),pred.size()))
        predClasses_index = torch.argmax(predClasses,dim=1)
        targetClasses_index_ex = targetClasses_index[:,None].expand(targetClasses_index.size(0),predClasses_index.size(0))
        predClasses_index_ex = predClasses_index[None,:].expand(targetClasses_index.size(0),predClasses_index.size(0))
        matchingClasses = targetClasses_index_ex==predClasses_index_ex
        validHits = allHits*matchingClasses

        #add all the preds that didn't have a hit
        hasHit,_ = validHits.max(dim=0) #which preds have hits
        notHitScores = pred[~hasHit,0]
        notHitClass = predClasses_index[~hasHit]
        for i in range(notHitScores.shape[0]):
            allScores.append( (notHitScores[i].item(), False) )
            cls = notHitClass[i]
            classScores[cls].append( (notHitScores[i].item(), False) )

        # if something has multiple hits, it gets paired to the closest (with matching class)
        allIOUs[~validHits] -= 9999999 #Force these to be smaller
        maxValidHitIndexes = torch.argmax(allIOUs,dim=0)
        for i in range(maxValidHitIndexes.size(0)):
            if validHits[maxValidHitIndexes[i],i]:
                allScores.append( (pred[i,0].item(),True) )
                #but now we've consumed this pred, so we'll zero its hit
                validHits[maxValidHitIndexes[i],i]=0
                cls = predClasses_index[i]
                classScores[cls].append( (pred[i,0].item(),True) )

        #add nan scores for missed targets
        gotHit,gotHitIndex = torch.max(validHits,dim=1)
        for i in range((gotHit==0).sum()):
            allScores.append( (float('nan'),True) )
            cls = targetClasses_index[i]
            classScores[cls].append( (float('nan'),True) )
    else:
        allScores.append( (float('nan'),True) )
        classScores=[[(float('nan'),True)]]*numClasses


    if ignoreClasses:
        numClasses=1
    #by class
    #import pdb; pdb.set_trace()
    for cls in range(numClasses):
        clsTargInd = target[:,cls+13]==1
        if len(pred.size())>1 and pred.size(0)>0:
            #print(pred.size())
            clsPredInd = torch.argmax(pred[:,beforeCls+6:beforeCls+6+numClasses],dim=1)==cls
        else:
            clsPredInd = torch.empty(0,dtype=torch.uint8)
        if (ignoreClasses and pred.size(0)>0) or (clsTargInd.any() and clsPredInd.any()):
            if ignoreClasses:
                clsTarg=target
                clsPred=pred
            else:
                clsTarg = target[clsTargInd]
                clsPred = pred[clsPredInd]
            clsIOUs = getLoc(clsTarg[:,0:],clsPred[:,1:])
            hits = clsIOUs>iou_thresh

            clsIOUs *= hits.float()
            ps = torch.argmax(clsIOUs,dim=1)
            left_ps = torch.ones(clsPred.size(0),dtype=torch.uint8)
            left_ps[ps]=0
            truePos=0
            for t in range(clsTarg.size(0)):
                p=ps[t]
                if hits[t,p]:
                    #scores.append( (clsPred[p,0],True) )
                    #hits[t,p]=0
                    truePos+=1
                #else:
                    #scores.append( (float('nan'),True) )
            
            left_conf = clsPred[left_ps,0]
            #for i in range(left_conf.size(0)):
                #scores.append( (left_conf[i],False) )
            
            #ap = computeAP(scores)
            #if ap is not None:
            #    aps.append(ap)

            precisions.append( truePos/max(clsPred.size(0),truePos) )
            if precisions[-1]>1:
                import pdb;pdb.set_trace()
            recalls.append( truePos/clsTarg.size(0) )
        elif ignoreClasses:
            #no pred
            #aps.append(0)
            precisions.append(0)
            recalls.append(0)
        elif clsPredInd.any() or clsTargInd.any():
            #aps.append(0)
            if clsPredInd.any():
                recalls.append(1)
                precisions.append(0)
            else:
                precisions.append(0)
                recalls.append(0)
        else:
            #aps.append(1)
            precisions.append(1)
            recalls.append(1)
    
    if getClassAP:
        classAPs=[computeAP(scores) for scores in classScores]
        #for i in range(len(classAPs)):
        #    if classAPs[i] is None:
        #        classAPs[i]=1
        return computeAP(allScores), precisions, recalls, classAPs
    else:
        return computeAP(allScores), precisions, recalls


def getTargIndexForPreds_iou(target,pred,iou_thresh,numClasses,beforeCls=0,hard_thresh=True,fixed=True):
    return getTargIndexForPreds(target,pred,iou_thresh,numClasses,beforeCls,allIOU,hard_thresh,fixed)
def getTargIndexForPreds_dist(target,pred,iou_thresh,numClasses,beforeCls=0,hard_thresh=True,fixed=True):
    raise NotImplemented('Checking if preds with no intersection not implemented for dist')
    return getTargIndexForPreds(target,pred,iou_thresh,numClasses,beforeCls,allBoxDistNeg,hard_thresh,fixed)

def getTargIndexForPreds(target,pred,iou_thresh,numClasses,beforeCls,getLoc, hard_thresh,fixed):
    targIndex = torch.LongTensor((pred.size(0)))
    targIndex[:] = -1
    #mAP=0.0
    aps=[]
    precisions=[]
    recalls=[]

    if len(target.size())<=1:
        return None, None

    #by class
    #import pdb; pdb.set_trace()
    #first get all IOUs, then process by class
    allIOUs = getLoc(target[:,0:],pred[:,1:])
    #This isn't going to work of dist as 0 is perfect
    maxIOUsForPred,_ = allIOUs.max(dim=0)
    predsWithNoIntersection=maxIOUsForPred==0

    hits = allIOUs>iou_thresh
    if hard_thresh:
        allIOUs *= hits.float()


    for cls in range(numClasses):
        scores=[]
        clsTargInd = target[:,cls+13]==1
        notClsTargInd = target[:,cls+13]!=1
        if len(pred.size())>1 and pred.size(0)>0:
            #print(pred.size())
            #clsPredInd = torch.argmax(pred[:,beforeCls+6:],dim=1)==cls
            clsPredInd = torch.argmax(pred[:,-numClasses:],dim=1)==cls
        else:
            clsPredInd = torch.empty(0,dtype=torch.uint8)
        if  clsPredInd.any():
            if notClsTargInd.any() and fixed:
                notClsTargIndX = notClsTargInd[:,None].expand(allIOUs.size())
                clsPredIndX = clsPredInd[None,:].expand(allIOUs.size())
                allIOUs[notClsTargIndX*clsPredIndX]=0 #set IOU for instances that are from different class than predicted to 0 (different class so no intersection)
                #allIOUs[notClsTargInd][:,clsPredInd]=0 this doesn't work for some reason
            val,targIndexes = torch.max(allIOUs[:,clsPredInd],dim=0)
            #targIndexes has the target indexes for the predictions of cls

            #assign -1 index to places that don't really have a match
            #targIndexes[:] = torch.where(val==0,-torch.ones_like(targIndexes),targIndexes)
            targIndexes[val==0] = -1
            #targIndexes[notClsTargInd] = -1
            #assert(notClsTargInd[targIndexes].sum()==0)
            targIndex[clsPredInd] =  targIndexes

    #debug
    #for i in range(targIndex.size(0)):
        #if targIndex[i]>=0:
    #         assert(torch.argmax(pred[i,-numClasses:],dim=0) == torch.argmax(target[targIndex[i],-numClasses:],dim=0))
            
    #import pdb;pdb.set_trace()
    if hard_thresh:
        return targIndex, predsWithNoIntersection
    else:
        hits,_ = hits.max(dim=0) #since we always take max pred
        return targIndex, hits

def computeAP(scores):
    rank=[]
    missed=0
    for conf,rel in scores:
        if rel:
            if math.isnan(conf):
                missed+=1
            else:
                better=0
                equal=-1 # as we'll iterate over this instance here
                for conf2,rel2 in scores:
                    if conf2>conf:
                        better+=1
                    elif conf2==conf:
                        equal+=1
                rank.append(better+math.ceil(equal/2.0))
    if len(rank)==0:
        if missed>0:
            return 0
        return None
    rank.sort()
    ap=0.0
    for i in range(len(rank)):
        ap += float(i+1)/(rank[i]+1)
    ap/=(len(rank)+missed)
    if ap>1.0001:
        raise ValueError('ap greater than 1({}), from {}'.format(ap,scores))
    return ap
