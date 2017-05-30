# pylint: skip-file
import os
# MXNET_CPU_WORKER_NTHREADS must be greater than 1 for custom op to work on CPU
os.environ["MXNET_CPU_WORKER_NTHREADS"] = "2"
import mxnet as mx
import numpy as np
import logging

class MultiBoxTarget(mx.operator.CustomOp):
    """ 
    Python implementation of MultiBoxTarget layer. 
    """
    def __init__(self, n_class, th_iou, th_neg_iou, hard_neg_ratio, ignore_label, variances):
        super(MultiBoxTarget, self).__init__()
        self.n_class = int(n_class)
        self.th_iou = float(th_iou)
        self.th_neg_iou = float(th_neg_iou)
        self.hard_neg_ratio = float(hard_neg_ratio)
        self.ignore_label = float(ignore_label)
        self.variances = variances

    def forward(self, is_train, req, in_data, out_data, aux):
        """ 
        Compute IOUs between valid labels and anchors.
        Then sample positive and negatives.
        """
        assert len(in_data) == 2
        anchors = in_data[0].asnumpy() # (batch, num_anchor, 4)
        labels_all = in_data[1].asnumpy() # (batch, num_label, 5)

        n_batch = labels_all.shape[0]
        n_anchors = labels_all.shape[1]
        cls_targets = np.array((n_batch, n_anchors), dtype=np.float32)
        loc_targets = np.array((n_batch, n_anchors, 4), dtype=np.float32)
        loc_masks = np.array((n_batch, n_anchors), dtype=np.float32)
        # compute IOUs
        for i in range(n_batch):
            labels = labels_all[i, :, :]
            cls_target, loc_target, loc_mask = self._forward_batch(anchors[0, :, :], labels)
            cls_targets[i, :] = cls_target
            loc_targets[i, :, :] = loc_target
            loc_masks[i, :] = loc_mask
        
        self.assign(out_data[0], req[0], mx.nd.reshape(loc_targets, (n_batch, n_anchors, 4)))
        self.assign(out_data[1], req[1], mx.nd.reshape(loc_masks, (n_batch, n_anchors, )))
        self.assign(out_data[2], req[2], mx.nd.reshape(cls_targets, (n_batch, n_anchors, self.n_class+1)))

    def backward(self, req, out_grad, in_data, out_data, in_grad, aux):
        pass

    def _forward_batch(self, anchors, labels):
        """ 
        I will process each batch sequentially.
        Note that anchors are transposed, so (4, num_anchors).
        """
        import ipdb
        ipdb.set_trace()
        n_anchors = anchors.shape[0]
        anchors_t = np.transpose(anchors, (1, 0))
        # outputs: cls_target, loc_target, loc_mask
        cls_target = self.ignore_label * np.ones((n_anchors,), dtype=np.float32)
        loc_target = np.zeros((n_anchors, 4), dtype=np.flaot32)
        loc_mask = np.zeros((n_anchors,), ctx=anchors.context)

        # valid gt labels
        n_valid_label = 0
        for i in range(labels.shape[0]):
            label = labels[i]
            mx.nd.waitall()
            if label[0].asscalar() == -1.0: 
                break
            n_valid_label += 1

        if self.hard_neg_ratio == 0:
            cls_target *= 0

        neg_iou = mx.nd.zeros((n_anchors,), ctx=anchors.context)
        n_valid_pos = 0
        for i in range(n_valid_label):
            label = labels[i]
            # cls_inx = int(label[0].asscalar())
            iou = _compute_IOU(label, anchors_t) 
            # pick positive
            midx = int(mx.nd.argmax(iou, axis=0).asscalar())
            if iou[midx] > self.th_iou:
                cls_target[midx] = label[0] + 1 # since 0 is the background
                loc_target[midx] = _compute_loc_target(label[1:], anchors[midx], self.variances)
                loc_mask[midx] = 1
                iou[midx] = 1
                n_valid_pos += 1
            neg_iou = mx.nd.maximum(iou, neg_iou)
        # pick negatives, if hard sample mining needed
        if self.hard_neg_ratio > 0:
            neg_iou *= neg_iou < th_neg_iou
            neg_iou += mx.nd.uniform(0.0, 0.01, shape=neg_iou.shape, ctx=anchors.context)
            n_neg_sample = mx.nd.minimum(n_anchors - n_valid_pos, n_valid_pos * self.hard_neg_ratio)
            sidx = mx.nd.argsort(neg_iou, is_ascend=False)
            nidx = int(sidx[n_neg_sample-1].asscalar())
            neg_mask = neg_iou < neg_iou[nidx]
            cls_target *= neg_mask

        return cls_target, loc_target, loc_mask

def _compute_IOU(label, anchors):
    # label: (5, )
    # anchors: (4, num_anchors)
    iw = mx.nd.maximum(0, \
            mx.nd.minimum(label[3], anchors[2]) - mx.nd.maximum(label[1], anchors[0]))
    ih = mx.nd.maximum(0, \
            mx.nd.minimum(label[4], anchors[3]) - mx.nd.maximum(label[2], anchors[1]))
    I = iw * ih
    U = (label[4] - label[2]) * (label[3] - label[1]) + \
            (anchors[2] - anchors[0]) * (anchors[3] - anchors[1])
    
    iou = I / mx.nd.maximum((U - I), 0.000001)

    return iou # (num_anchors, )

def _compute_loc_target(gt_bb, bb, variances):
    loc_target = mx.nd.array((4, ), ctx=bb.context)
    loc_target[0] = ((gt_bb[2]+gt_bb[0]) / 2.0 - (bb[2]-bb[0]) / 2.0) / variances[0]
    loc_target[1] = ((gt_bb[3]+gt_bb[1]) / 2.0 - (bb[3]-bb[1]) / 2.0) / variances[1]
    loc_target[2] = mx.nd.log((gt_bb[2]-gt_bb[0]) / (bb[2]-bb[0])) / variances[2]
    loc_target[3] = mx.nd.log((gt_bb[3]-gt_bb[1]) / (bb[3]-bb[1])) / variances[2]

    return loc_target

@mx.operator.register("multibox_target")
class MultiBoxTargetProp(mx.operator.CustomOpProp):
    def __init__(self, n_class, 
            th_iou=0.5, th_neg_iou=0.5, hard_neg_ratio=3., ignore_label=-1, variances=(0.1, 0.1, 0.2, 0.2)):
        super(MultiBoxTargetProp, self).__init__(need_top_grad=False)
        self.n_class = int(n_class)
        self.th_iou = float(th_iou)
        self.th_neg_iou = float(th_neg_iou)
        self.hard_neg_ratio = float(hard_neg_ratio)
        self.ignore_label = float(ignore_label)
        self.variances = mx.nd.array(np.array(variances).astype(float))

    def list_arguments(self):
        return ['anchors', 'label']

    def list_outputs(self):
        return ['cls_target', 'loc_target', 'loc_mask']

    def infer_shape(self, in_shape):
        n_anchors = in_shape[0][1]
        n_batch = in_shape[0][0] 

        cls_target_shape = (n_batch, n_anchors, self.n_class+1)
        loc_target_shape = (n_batch, n_anchors, 4)
        loc_mask_shape = (n_batch, n_anchors)

        return [in_shape[0], in_shape[1]], \
                [loc_target_shape, loc_mask_shape, cls_target_shape], \
                []

    def create_operator(self, ctx, shapes, dtypes):
        return MultiBoxTarget( \
                self.n_class, self.th_iou, self.th_neg_iou, self.hard_neg_ratio, self.ignore_label, self.variances)
