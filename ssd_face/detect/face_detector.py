from __future__ import print_function
import mxnet as mx
import numpy as np
from timeit import default_timer as timer
from dataset.testdb import TestDB
from dataset.face_test_iter import FaceTestIter
from mutable_module import MutableModule
import os


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
                 ctx=None):
        self.ctx = ctx
        if self.ctx is None:
            self.ctx = mx.cpu()
        _, self.args, self.auxs = mx.model.load_checkpoint(model_prefix, epoch)
        assert max_data_shapes[0] % img_stride == 0 and max_data_shapes[1] % img_stride == 0
        self.max_data_shapes = max_data_shapes
        max_data_shapes = {
            'data': (1, 3, max_data_shapes[0], max_data_shapes[1]), 
            'im_scale': (1, 2)
        }
        # self.mod = mx.mod.Module(
        #     symbol,
        #     data_names=('data', 'im_scale'),
        #     label_names=None,
        #     context=ctx)
        self.mod = MutableModule(
            symbol,
            data_names = ('data', 'im_scale'),
            label_names=None,
            context=ctx,
            max_data_shapes=max_data_shapes)
        # self.data_shape = provide_data
        # self.mod.bind(data_shapes=max_data_shapes)
        # self.mod.set_params(args, auxs)
        self.mean_pixels = mean_pixels
        self.img_stride = img_stride

    def detect(self, det_iter, show_timer=False):
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
        if not isinstance(det_iter, mx.io.PrefetchingIter):
            det_iter = mx.io.PrefetchingIter(det_iter)
        if not self.mod.binded:
            self.mod.bind(
                data_shapes=det_iter.provide_data,
                label_shapes=None,
                for_training=False,
                force_rebind=True)
            self.mod.set_params(self.args, self.auxs)
        start = timer()
        detections = self.mod.predict(det_iter).asnumpy()
        time_elapsed = timer() - start
        if show_timer:
            print("Detection time for {} images: {:.4f} sec".format(
                num_images, time_elapsed))
        result = []
        for i in range(detections.shape[0]):
            det = detections[i, :, :]
            res = det[np.where(det[:, 0] >= 0)[0]]
            result.append(res)
        return result

    def im_detect(self,
                  im_list,
                  root_dir=None,
                  extension=None,
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
        test_iter = FaceTestIter(test_db, self.max_data_shapes,
                                 self.mean_pixels, self.img_stride)
        return self.detect(test_iter, show_timer)

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
                        colors[cls_id] = (random.random(), random.random(),
                                          random.random())
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
                        linewidth=2.5)
                    plt.gca().add_patch(rect)
                    class_name = str(cls_id)
                    if classes and len(classes) > cls_id:
                        class_name = classes[cls_id]
                    plt.gca().text(
                        xmin,
                        ymin - 2,
                        '{:.3f}'.format(score),
                        bbox=dict(facecolor=colors[cls_id], alpha=0.5),
                        fontsize=7,
                        color='white')
                    # plt.gca().text(
                    #     xmin,
                    #     ymin - 2,
                    #     '{:s} {:.3f}'.format(class_name, score),
                    #     bbox=dict(facecolor=colors[cls_id], alpha=0.5),
                    #     fontsize=7,
                    #     color='white')
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
        dets = self.im_detect(
            im_list, root_dir, extension, show_timer=show_timer)
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
