import mxnet as mx
import numpy as np


class MultiBoxMetric(mx.metric.EvalMetric):
    """Calculate metrics for Multibox training """
    def __init__(self, eps=1e-8):
        super(MultiBoxMetric, self).__init__('MultiBox')
        self.eps = eps
        self.num = 4
        self.name = ['Loss', 'SmoothL1', 'Recall', 'Acc']
        self.reset()

    def reset(self):
        """
        override reset behavior
        """
        if getattr(self, 'num', None) is None:
            self.num_inst = 0
            self.sum_metric = 0.0
        else:
            self.num_inst = [0] * self.num
            self.sum_metric = [0.0] * self.num

    def update(self, labels, preds):
        """
        Implementation of updating metrics
        """
        # get generated multi label from network
        cls_prob = preds[0].asnumpy()
        loc_loss = preds[1].asnumpy()
        cls_label = preds[2].asnumpy()
        loc_label = preds[3].asnumpy()

        valid_count = np.sum(cls_label >= 0)
        valid_count += np.sum(np.any(loc_label, axis=-1)) #valid_count
        # overall accuracy & object accuracy
        label = cls_label.flatten()
        mask = np.where(label >= 0)[0]
        indices = np.int64(label[mask])
        if cls_prob.ndim == 3:
            prob_all = cls_prob.transpose((0, 2, 1)).reshape((-1, cls_prob.shape[1]))
        else:
            prob_all = cls_prob
        prob = prob_all[mask, indices]
        self.sum_metric[0] += (-np.log(prob + self.eps)).sum()
        self.num_inst[0] += valid_count
        # smoothl1loss
        self.sum_metric[1] += np.sum(loc_loss)
        self.num_inst[1] += valid_count
        # self.num_inst[1] += np.sum(np.any(loc_label, axis=-1)) #valid_count
        # recall and acc
        acc = np.argmax(prob_all, axis=1) == label
        # recall
        mask = np.where(label > 0)[0]
        self.sum_metric[2] += np.sum(acc[mask])
        self.num_inst[2] += len(mask)
        # acc
        mask = np.where(label >= 0)[0]
        self.sum_metric[3] += np.sum(acc[mask])
        self.num_inst[3] += len(mask)

    def get(self):
        """Get the current evaluation result.
        Override the default behavior

        Returns
        -------
        name : str
           Name of the metric.
        value : float
           Value of the evaluation.
        """
        if self.num is None:
            if self.num_inst == 0:
                return (self.name, float('nan'))
            else:
                return (self.name, self.sum_metric / self.num_inst)
        else:
            names = ['%s'%(self.name[i]) for i in range(self.num)]
            values = [x / y if y != 0 else float('nan') \
                for x, y in zip(self.sum_metric, self.num_inst)]
            return (names, values)


class RONMetric(mx.metric.EvalMetric):
    """Calculate metrics for Multibox training """
    def __init__(self, eps=1e-8):
        super(RONMetric, self).__init__('RON')
        self.eps = eps
        self.name = ['Loss', 'SmoothL1', 'RPNLoss', 'Recall', 'Acc', 'RPNAcc']
        self.num = len(self.name)
        self.reset()

    def reset(self):
        """
        override reset behavior
        """
        if getattr(self, 'num', None) is None:
            self.num_inst = 0
            self.sum_metric = 0.0
        else:
            self.num_inst = [0] * self.num
            self.sum_metric = [0.0] * self.num

    def update(self, labels, preds):
        """
        Implementation of updating metrics
        """
        # get generated multi label from network
        cls_prob = preds[0].asnumpy()
        loc_loss = preds[1].asnumpy()
        rpn_prob = preds[2].asnumpy()
        cls_label = preds[3].asnumpy()
        loc_label = preds[4].asnumpy()
        rpn_label = preds[5].asnumpy()

        # rpn related
        label = rpn_label.flatten()
        mask = np.where(label >= 0)[0]
        indices = np.int64(label[mask])
        if rpn_prob.ndim == 3:
            prob_all = rpn_prob.transpose((0, 2, 1)).reshape((-1, rpn_prob.shape[1]))
        else:
            prob_all = rpn_prob
        mask = np.where(label >= 0)[0]
        prob = prob_all[mask, indices]
        self.sum_metric[2] += (-np.log(prob + self.eps)).sum()
        self.num_inst[2] += np.sum(label >= 0)

        acc = np.argmax(prob_all, axis=1) == label
        self.sum_metric[5] += np.sum(acc[mask])
        self.num_inst[5] += len(mask)

        # rcnn related
        mask = np.where(label > 0)[0]
        prob_obj = prob_all[:, 1]
        prob_obj[mask] = 1
        valid_count = np.sum(cls_label >= 0)
        valid_count += np.sum(np.any(loc_label, axis=-1)) #valid_count
        # overall accuracy & object accuracy
        label = cls_label.flatten()
        mask = np.where(label >= 0)[0]
        indices = np.int64(label[mask])
        if cls_prob.ndim == 3:
            prob_all = cls_prob.transpose((0, 2, 1)).reshape((-1, cls_prob.shape[1]))
        else:
            prob_all = cls_prob
        prob = prob_all[mask, indices]
        cls_loss = -np.log(prob + self.eps)
        cls_loss *= prob_obj[mask]
        self.sum_metric[0] += np.sum(cls_loss)
        self.num_inst[0] += valid_count
        # smoothl1loss
        self.sum_metric[1] += np.sum(loc_loss * np.reshape(prob_obj, (-1, 1)))
        self.num_inst[1] += valid_count
        # self.num_inst[1] += np.sum(np.any(loc_label, axis=-1)) #valid_count
        # recall and acc
        acc = np.argmax(prob_all, axis=1) == label
        # recall
        mask = np.where(label > 0)[0]
        self.sum_metric[3] += np.sum(acc[mask])
        self.num_inst[3] += len(mask)
        # acc
        mask = np.where(label >= 0)[0]
        self.sum_metric[4] += np.sum(acc[mask])
        self.num_inst[4] += len(mask)

        

    def get(self):
        """Get the current evaluation result.
        Override the default behavior

        Returns
        -------
        name : str
           Name of the metric.
        value : float
           Value of the evaluation.
        """
        if self.num is None:
            if self.num_inst == 0:
                return (self.name, float('nan'))
            else:
                return (self.name, self.sum_metric / self.num_inst)
        else:
            names = ['%s'%(self.name[i]) for i in range(self.num)]
            values = [x / y if y != 0 else float('nan') \
                for x, y in zip(self.sum_metric, self.num_inst)]
            return (names, values)
class FacePatchMetric(mx.metric.EvalMetric):
    """Calculate metrics for Multibox training """
    def __init__(self, num=4, postfix_names=['Loss', 'SmoothL1', 'Acc', 'Recall']):
        # super(FacePatchMetric, self).__init__(['Loss', 'SmoothL1', 'Recall'], 3)
        self.sum_metric = np.zeros((num,))
        self.num_inst = np.zeros((num,), dtype=int)
        super(FacePatchMetric, self).__init__(name='')
        self.postfix_names = postfix_names
        self.num = num

    def update(self, labels, preds):
        """
        Implementation of updating metrics
        labels are not used here.
        """
        # get generated multi label from network
        cls_loss = preds[0].asnumpy()
        reg_loss = preds[1].asnumpy()
        cls_label = preds[2].asnumpy()
        reg_label = preds[3].asnumpy()
        cls_prob = preds[4].asnumpy()

        cls_acc = np.argmax(cls_prob, axis=1) == cls_label

        mask = np.where(cls_label >= 0)[0]
        n_valid_sample = mask.size
        if mask.size > 0:
            self.sum_metric[0] += sum(cls_loss)
            self.sum_metric[2] += sum(cls_acc[mask])
            self.num_inst[2] += mask.size

        mask_r = np.sum(np.any(reg_label, axis=1))
        # mask_r = np.where(np.any(reg_label != -1, axis=1))[0]
        n_valid_sample += mask_r
        if mask_r > 0:
            self.sum_metric[1] += sum(reg_loss)
        self.num_inst[0] += n_valid_sample
        self.num_inst[1] += n_valid_sample

        mask_p = np.where(cls_label > 0)[0]
        if mask_p.size > 0:
            self.sum_metric[3] += sum(cls_acc[mask_p])
            self.num_inst[3] += mask_p.size

    def update_dict(self, labels, preds):
        label = []
        pred = []
        for l, v in labels.items():
            label.append(v)
        for p, v in preds.items():
            pred.append(v)

        self.update(label, pred)

    def reset(self):
        self.sum_metric[:] = 0.0
        self.num_inst[:] = 0

    def get(self):
        """Get the current evaluation result.
        Override the default behavior

        Returns
        -------
        name : str
           Name of the metric.
        value : float
           Value of the evaluation.
        """
        names = ['%s'%(self.name+self.postfix_names[i]) for i in range(self.num)]
        values = [x / y if y != 0 else float('nan') \
            for x, y in zip(self.sum_metric, self.num_inst)]
        return (names, values)
