from __future__ import print_function
import os
from timeit import default_timer as timer
from dataset.testdb import TestDB
from dataset.test_iter import TestIter
from mutable_module import MutableModule
import mxnet as mx
import numpy as np

class FaceDetector(object):
    """
    SSD detector which hold a detection network and wraps detection API

    Parameters:
    ----------
    symbol : mx.Symbol
        detection network Symbol
    model_prefix : str
        name prefix of trained model
    epoch : int
        load epoch of trained model
    data_shape : int
        input data resize shape
    mean_pixels : tuple of float
        (mean_r, mean_g, mean_b)
    batch_size : int
        run detection with batch size
    ctx : mx.ctx
        device to use, if None, use mx.cpu() as default context
    """

    def __init__(self,
                 symbol,
                 model_prefix,
                 epoch,
                 max_data_shapes,
                 mean_pixels,
                 img_stride=32,
                 min_size=0,
                 th_nms=0.3333,
                 ctx=None):
        self.ctx = ctx
        if self.ctx is None:
            self.ctx = mx.cpu()
        _, self.args, self.auxs = mx.model.load_checkpoint(model_prefix, epoch)
        assert max_data_shapes[0] % img_stride == 0 and max_data_shapes[1] % img_stride == 0
        self.max_data_shapes = max_data_shapes
        max_data_shapes = {
            'data': (1, 3, max_data_shapes[0], max_data_shapes[1])
        }
        # self.mod = mx.mod.Module(
        #     symbol,
        #     data_names=('data', 'im_scale'),
        #     label_names=None,
        #     context=ctx)
        self.mod = MutableModule(
            symbol,
            data_names = ('data', ),
            label_names=None,
            context=ctx,
            max_data_shapes=max_data_shapes)
        # self.data_shape = provide_data
        # self.mod.bind(data_shapes=max_data_shapes)
        # self.mod.set_params(args, auxs)
        self.mean_pixels = mean_pixels
        self.img_stride = img_stride
        self.min_size = min_size
        self.th_nms = th_nms

    def detect(self, det_iter, thresh=0.0, show_timer=False):
        """
        detect all images in iterator

        Parameters:
        ----------
        det_iter : DetIter
            iterator for all testing images
        show_timer : Boolean
            whether to print out detection exec time

        Returns:
        ----------
        list of detection results
        """
        num_images = det_iter._size
        # if not isinstance(det_iter, mx.io.PrefetchingIter):
        #     det_iter = mx.io.PrefetchingIter(det_iter)
        if not self.mod.binded:
            self.mod.bind(
                data_shapes=[det_iter.provide_data[0]],
                label_shapes=[],
                for_training=False,
                force_rebind=True)
            self.mod.set_params(self.args, self.auxs, allow_missing=True)
            # _, self.auxs = self.mod.get_params()
            # for k, v in self.auxs.items():
            #     if k.endswith('_moving_mean'):
            #         v[:] = 0.0
            #     if k.endswith('_moving_var'):
            #         v[:] = 0.99999
            # self.mod.set_params(self.args, self.auxs)

        # start = timer()
        result = []
        im_paths = []
        detections = []
        for i, (datum, im_info) in enumerate(det_iter):
            im_scale = im_info['im_scale'][0].asnumpy()
            im_paths.append(im_info['im_path'])

            start = timer()
            self.mod.forward(datum)
            out = self.mod.get_outputs()

            dets = out[0][0].asnumpy()
            iidx = np.where(np.logical_and(dets[0] > 0, dets[1] > thresh))[0]
            # time_elapsed = timer() - start
            if len(iidx) == 0:
                result.append(np.zeros((0, 6)))
                time_elapsed = timer() - start
                continue
            dets = np.transpose(dets[:, iidx])
            sidx = np.argsort(dets[:, 1])[::-1]
            dets = dets[sidx, :]
            dets[:, 2] *= im_scale[1]
            dets[:, 3] *= im_scale[0]
            dets[:, 4] *= im_scale[1]
            dets[:, 5] *= im_scale[0]
            overlap = self._comp_overlap(dets[:, 2:], im_info['im_shape'])
            iidx = overlap > 0.6
            n_oob = np.where(iidx == False)[0].size
            # if n_oob > 0:
            #     print('n_oob = {}'.format(n_oob))
            dets = dets[iidx, :]
            dets[:, 2] = np.maximum(dets[:, 2], 0.0)
            dets[:, 3] = np.maximum(dets[:, 3], 0.0)
            dets[:, 4] = np.minimum(dets[:, 4], im_info['im_shape'][1])
            dets[:, 5] = np.minimum(dets[:, 5], im_info['im_shape'][0])
            vidx = self._do_nms(dets)
            dets = dets[vidx, :]
            result.append(dets)
            time_elapsed = timer() - start
            # print(dets)

            if i % 10 == 0:
                n_dets = dets.shape[0]
                print('Processing image {}/{}, {} objects detected.'.format(i+1, num_images, n_dets))
        # time_elapsed = timer() - start
        if show_timer:
            print("Detection time for {} images: {:.4f} sec".format(
                num_images, time_elapsed))
        return result, im_paths

    def im_detect(self,
                  im_list,
                  root_dir=None,
                  extension=None,
                  thresh=0.0,
                  show_timer=False):
        """
        wrapper for detecting multiple images

        Parameters:
        ----------
        im_list : list of str
            image path or list of image paths
        root_dir : str
            directory of input images, optional if image path already
            has full directory information
        extension : str
            image extension, eg. ".jpg", optional

        Returns:
        ----------
        list of detection results in format [det0, det1...], det is in
        format np.array([id, score, xmin, ymin, xmax, ymax]...)
        """
        test_db = TestDB(im_list, root_dir=root_dir, extension=extension)
        test_iter = TestIter(test_db, self.max_data_shapes,
                                 self.mean_pixels, self.img_stride, self.min_size)
        return self.detect(test_iter, thresh, show_timer)

    def visualize_detection(self, img, dets, classes=[], thresh=0.6):
        """
        visualize detections in one image

        Parameters:
        ----------
        img : numpy.array
            image, in bgr format
        dets : numpy.array
            ssd detections, numpy.array([[id, score, x1, y1, x2, y2]...])
            each row is one object
        classes : tuple or list of str
            class names
        thresh : float
            score threshold
        """
        import matplotlib.pyplot as plt
        import random
        plt.imshow(img)
        # height = img.shape[0]
        # width = img.shape[1]
        # wr = width / float(self.data_shape[1])
        # hr = height / float(self.data_shape[0])
        colors = dict()
        for i in range(dets.shape[0]):
            cls_id = int(dets[i, 0])
            if cls_id >= 0:
                score = dets[i, 1]
                if score > thresh:
                    if cls_id not in colors:
                        colors[cls_id] = (1, 1, 0) #(random.random(), random.random(), random.random())
                    # xmin = int(dets[i, 2] * width)
                    # ymin = int(dets[i, 3] * height)
                    # xmax = int(dets[i, 4] * width)
                    # ymax = int(dets[i, 5] * height)
                    xmin = int(dets[i, 2])
                    ymin = int(dets[i, 3])
                    xmax = int(dets[i, 4])
                    ymax = int(dets[i, 5])
                    rect = plt.Rectangle(
                        (xmin, ymin),
                        xmax - xmin,
                        ymax - ymin,
                        fill=False,
                        edgecolor=colors[cls_id],
                        linewidth=1.5)
                    plt.gca().add_patch(rect)
                    class_name = str(cls_id)
                    if classes and len(classes) > cls_id:
                        class_name = classes[cls_id]
                    # plt.gca().text(
                    #     xmin,
                    #     ymin - 2,
                    #     '{:.3f}'.format(score),
                    #     bbox=dict(facecolor=colors[cls_id], alpha=0.5),
                    #     fontsize=7,
                    #     color='white')
                    plt.gca().text(
                        xmin,
                        ymin - 2,
                        '{:s} {:.3f}'.format(class_name, score),
                        bbox=dict(facecolor=colors[cls_id], alpha=0.5),
                        fontsize=10,
                        color='red')
        # plt.gcf().savefig('res.png')
        plt.show()

    def detect_and_visualize(self,
                             im_list,
                             root_dir=None,
                             extension=None,
                             classes=[],
                             thresh=0.6,
                             show_timer=False):
        """
        wrapper for im_detect and visualize_detection

        Parameters:
        ----------
        im_list : list of str or str
            image path or list of image paths
        root_dir : str or None
            directory of input images, optional if image path already
            has full directory information
        extension : str or None
            image extension, eg. ".jpg", optional

        Returns:
        ----------

        """
        import cv2
        dets, _ = self.im_detect(
            im_list, root_dir, extension, thresh=thresh, show_timer=show_timer)
        root_dir = '' if not root_dir else root_dir
        extension = '' if not extension else extension
        if not isinstance(im_list, list):
            im_list = [im_list]
        assert len(dets) == len(im_list)
        for k, det in enumerate(dets):
            fn_img = os.path.join(root_dir, im_list[k] + extension)
            img = cv2.imread(fn_img)
            img[:, :, (0, 1, 2)] = img[:, :, (2, 1, 0)]
            self.visualize_detection(img, det, classes, thresh)

    # def _transform_roi(self, dets, anchors, variances=(0.1, 0.1, 0.2, 0.2), ratio=0.8):
    #     #
    #     cx = (anchors[:, 0] + anchors[:, 2]) * 0.5
    #     cy = (anchors[:, 1] + anchors[:, 3]) * 0.5
    #     aw = (anchors[:, 2] - anchors[:, 0])
    #     aw *= ratio
    #     ah = (anchors[:, 3] - anchors[:, 1])
    #     cx += dets[:, 2] * aw * variances[0]
    #     cy += dets[:, 3] * ah * variances[1]
    #     w = (2.0**(dets[:, 4] * variances[2])) * aw * 0.5
    #     h = (2.0**(dets[:, 5] * variances[3])) * ah * 0.5
    #     dets[:, 2] = cx - w
    #     dets[:, 3] = cy - h
    #     dets[:, 4] = cx + w
    #     dets[:, 5] = cy + h
    #     return dets

    def _do_nms(self, dets):
        #
        vidx = []
        if dets.size == 0:
            return vidx
        areas = (dets[:, 4] - dets[:, 2]) * (dets[:, 5] - dets[:, 3])
        n_cls = int(np.max(dets[:, 0])) + 1
        for k in range(n_cls):
            cidx = np.where(dets[:, 0].astype(int) == k)[0]
            if cidx.size == 0:
                continue
            dets_cls = dets[cidx, :]
            areas_cls = areas[cidx]
            vmask = np.ones((dets_cls.shape[0],), dtype=int)
            for i, d in enumerate(dets_cls):
                if vmask[i] == 0:
                    continue
                iw = np.minimum(d[4], dets_cls[i:, 4]) - np.maximum(d[2], dets_cls[i:, 2])
                ih = np.minimum(d[5], dets_cls[i:, 5]) - np.maximum(d[3], dets_cls[i:, 3])
                I = np.maximum(iw, 0) * np.maximum(ih, 0)
                iou = I / np.maximum(areas_cls[i:] + areas_cls[i] - I, 1e-08)
                nidx = np.where(iou > self.th_nms)[0] + i
                vmask[nidx] = 0
                vidx.append(cidx[i])
        return vidx


    def _comp_overlap(self, dets, im_shape):
        #
        area_dets = (dets[:, 2] - dets[:, 0]) * (dets[:, 3] - dets[:, 1])
        # if np.min(area_dets) < 16 or np.max(area_dets) > im_shape[0]*im_shape[1]*2.0:
        #     import ipdb
        #     ipdb.set_trace()
        iw = np.minimum(dets[:, 2], im_shape[1]) - np.maximum(dets[:, 0], 0)
        ih = np.minimum(dets[:, 3], im_shape[0]) - np.maximum(dets[:, 1], 0)

        overlap = (iw * ih) / (area_dets + 1e-04)
        return overlap
