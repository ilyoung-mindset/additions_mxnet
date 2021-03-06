import os
import mxnet as mx
import numpy as np
# MXNET_CPU_WORKER_NTHREADS must be greater than 1 for custom op to work on CPU
os.environ["MXNET_CPU_WORKER_NTHREADS"] = "4"
from ast import literal_eval as make_tuple


class MultiBoxDetection(mx.operator.CustomOp):
    '''
    python implementation of MultiBoxDetection layer.
    '''

    def __init__(self, n_class, max_detection, th_pos, th_nms, per_cls_reg, variances):
        #
        super(MultiBoxDetection, self).__init__()
        self.n_class = n_class
        self.th_pos = th_pos
        self.th_nms = th_nms
        self.variances = variances
        self.per_cls_reg = per_cls_reg
        self.max_detection = max_detection

    def forward(self, is_train, req, in_data, out_data, aux):
        '''
        pick positives, transform bbs, apply nms
        '''
        n_batch = in_data[1].shape[0]
        n_anchor = in_data[1].shape[1]
        n_class = in_data[0].shape[1]

        probs_cls = mx.nd.reshape(in_data[0], (n_batch, n_anchor, n_class))
        preds_reg = in_data[1]  # (n_batch, n_anchors, 4)
        anchors = in_data[2]  # (n_anchors, 4)
        # im_scale = in_data[3]
        
        for nn in range(n_batch):
            out_i = out_data[0][nn]
            # out_i[:] = 0
            pcls = probs_cls[nn]  # (n_anchors, n_classes)
            preg = preds_reg[nn]  # (n_anchor, 4) or (n_anchor, 4 * n_class)

            if n_class == 1:
                iidx = mx.nd.reshape(pcls > self.th_pos, (-1,))
                out_i[0] = iidx
                out_i[1][:] = mx.nd.reshape(pcls, (-1,))
            else:
                max_pcls = mx.nd.max(pcls, axis=1)
                iidx = mx.nd.reshape(max_pcls > self.th_pos, (-1,))
                max_cid = mx.nd.argmax(pcls, axis=1) + 1
                out_i[0] = iidx * max_cid
                out_i[1] = max_pcls
            if not self.per_cls_reg:
                out_i[2:] = _transform_roi( \
                        mx.nd.transpose(preg), mx.nd.transpose(anchors), self.variances, 1.0)
            elif n_class > 1:
                preg_cls = _pack_reg(preg, max_cid)
                out_i[2:] = _transform_roi( \
                        mx.nd.transpose(preg_cls), mx.nd.transpose(anchors), self.variances, 1.0)

        # for nn in range(n_batch):
        #     out_i = out_data[0][nn]
        #     out_i[:] = 0
        #     pcls = probs_cls[nn]  # (n_anchors, n_classes)
        #     preg = preds_reg[nn]  # (n_anchor, 4)
        #     pcls_t = mx.nd.transpose(pcls, axes=(1, 0))
        #     if n_class == 1:
        #         max_probs = mx.nd.reshape(pcls_t, (-1,))
        #         # max_cid = pcls_t
        #     else:
        #         max_probs = mx.nd.max(pcls_t, axis=0) #.asnumpy()
        #         max_cid = mx.nd.argmax(pcls_t, axis=0) #.asnumpy()
        #
        #     n_detection = int(mx.nd.sum(max_probs > self.th_pos).asscalar())
        #     if n_detection == 0:
        #         continue
        #
        #     sidx = mx.nd.argsort(max_probs, is_ascend=False)
        #     sidx = sidx[:n_detection]
        #
        #     oreg_t = mx.nd.transpose(mx.nd.take(preg, sidx))
        #     oanc_t = mx.nd.transpose(mx.nd.take(anchors, sidx))
        #     ocls = mx.nd.take(max_probs, sidx)
        #     if n_class > 1:
        #         ocid = mx.nd.take(max_cid, sidx)
        #     oreg_t = _transform_roi(oreg_t, oanc_t, self.variances, 0.8)
        #     oreg = mx.nd.transpose(oreg_t)
        #
        #     vidx = _nms(oreg_t, self.th_nms)
        #     n_valid = len(vidx)
        #     n_detection = np.minimum(n_valid, self.max_detection)
        #     vidx = vidx[:n_detection]
        #
        #     for i, vid in enumerate(vidx):
        #         if n_class > 1:
        #             out_i[i][0] = ocid[vid]
        #         out_i[i][1] = ocls[vid]
        #         out_i[i][2:] = oreg[vid]
            # out_data[1][nn] = n_detection

    def backward(self, req, out_grad, in_data, out_data, in_grad, aux):
        pass


def _nms(out_t, th_nms):
    n_detection = out_t.shape[1]
    nms_mask = np.zeros((n_detection,), dtype=np.bool)
    out = mx.nd.transpose(out_t)
    area_out_t = (out_t[2] - out_t[0]) * (out_t[3] - out_t[1])
    for i in range(n_detection-1):
        if nms_mask[i]: 
            continue
        iw = mx.nd.minimum(out_t[2][i], out_t[2]) - \
                mx.nd.maximum(out_t[0][i], out_t[0])
        ih = mx.nd.minimum(out_t[3][i], out_t[3]) - \
                mx.nd.maximum(out_t[1][i], out_t[1])
        I = mx.nd.maximum(iw, 0) * mx.nd.maximum(ih, 0)
        iou_mask = (I / mx.nd.maximum(area_out_t + area_out_t[i] - I, 1e-06)) > th_nms
        nidx = np.where(iou_mask.asnumpy())[0]
        nms_mask[nidx] = True
        nms_mask[i] = False
        # iw = mx.nd.minimum(out_t[2][i], out_t[2][(i+1):]) - \
        #         mx.nd.maximum(out_t[0][i], out_t[0][(i+1):])
        # ih = mx.nd.minimum(out_t[3][i], out_t[3][(i+1):]) - \
        #         mx.nd.maximum(out_t[1][i], out_t[1][(i+1):])
        # I = mx.nd.maximum(iw, 0) * mx.nd.maximum(ih, 0)
        # iou_mask = (I / mx.nd.maximum(area_out_t[(i+1):] + area_out_t[i] - I, 1e-06)) > th_nms
        # nidx = np.where(iou_mask.asnumpy())[0] + i + 1
        # nms_mask[nidx] = True
    return np.where(nms_mask == False)[0]


def _pack_reg(reg, max_cid):
    # packed = mx.nd.zeros((reg.shape[0], 4), ctx=reg.context)
    max_cid = mx.nd.tile(mx.nd.reshape(max_cid, (-1, 1)), (1, 4))
    packed = mx.nd.pick(mx.nd.reshape(reg, (0, -1, 4)), max_cid, axis=1)
    # max_cid = max_cid.asnumpy().astype(int)
    # for i, (r, c) in enumerate(zip(reg, max_cid)):
    #     packed[i] = r[c*4:(c+1)*4]
    return packed


def _transform_roi(reg_t, anc_t, variances, ratio=1.0):
    #
    # reg_t = mx.nd.transpose(reg)
    # anc_t = mx.nd.transpose(anc)
    for i in range(4):
        reg_t[i] *= variances[i]

    cx = (anc_t[0] + anc_t[2]) * 0.5
    cy = (anc_t[1] + anc_t[3]) * 0.5

    aw = anc_t[2] - anc_t[0]
    ah = anc_t[3] - anc_t[1]
    aw *= ratio
    cx += reg_t[0] * aw
    cy += reg_t[1] * ah
    w = (2.0**reg_t[2]) * aw * 0.5
    h = (2.0**reg_t[3]) * ah * 0.5
    reg_t[0] = cx - w
    reg_t[1] = cy - h
    reg_t[2] = cx + w
    reg_t[3] = cy + h
    return reg_t


@mx.operator.register("multibox_detection")
class MultiBoxDetectionProp(mx.operator.CustomOpProp):
    def __init__(self,
                 n_class,
                 max_detection=1000,
                 th_pos=0.5,
                 th_nms=0.3333,
                 per_cls_reg=False,
                 variances=(0.1, 0.1, 0.2, 0.2)):
        #
        super(MultiBoxDetectionProp, self).__init__(need_top_grad=True)
        self.n_class = int(n_class)
        self.max_detection = int(max_detection)
        self.th_pos = float(th_pos)
        self.th_nms = float(th_nms)
        self.per_cls_reg = bool(make_tuple(str(per_cls_reg)))
        if isinstance(variances, str):
            variances = make_tuple(variances)
        self.variances = np.array(variances)

    def list_arguments(self):
        return ['probs_cls', 'preds_reg', 'anchors']

    def list_outputs(self):
        return ['output']

    def infer_shape(self, in_shape):
        n_batch = in_shape[1][0]
        # if self.n_class == 1:
        #     out_shape = [(n_batch, in_shape[2][0], 5), in_shape[2]]
        # else:
        #     out_shape = [(n_batch, in_shape[2][0], 6), in_shape[2]]
        out_shape = [(n_batch, 6, in_shape[2][0])]
        # out_shape = [(n_batch, self.max_detection, 6), (n_batch, )]
        aux_shape = []
        return in_shape, out_shape, aux_shape

    def create_operator(self, ctx, shapes, dtypes):
        return MultiBoxDetection(self.n_class, self.max_detection, self.th_pos,
                                 self.th_nms, self.per_cls_reg, self.variances)
