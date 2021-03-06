"""
Fast R-CNN:
data =
    {'data': [num_images, c, h, w],
    'rois': [num_rois, 5]}
label =
    {'label': [num_rois],
    'bbox_target': [num_rois, 4 * num_classes],
    'bbox_weight': [num_rois, 4 * num_classes]}
roidb extended format [image_index]
    ['image', 'height', 'width', 'flipped',
     'boxes', 'gt_classes', 'gt_overlaps', 'max_classes', 'max_overlaps', 'bbox_targets']
"""

import numpy as np
import numpy.random as npr

from ..config import config
from ..io.image import get_image, tensor_vstack
from ..processing.bbox_transform import bbox_overlaps, bbox_transform, bbox_transform_part
from ..processing.bbox_regression import expand_bbox_regression_targets


def get_rcnn_testbatch(roidb):
    """
    return a dict of testbatch
    :param roidb: ['image', 'flipped'] + ['boxes']
    :return: data, label, im_info
    """
    assert len(roidb) == 1, 'Single batch only'
    imgs, roidb = get_image(roidb)
    im_array = imgs[0]
    im_info = np.array([roidb[0]['im_info']], dtype=np.float32)

    im_rois = roidb[0]['boxes']
    rois = im_rois
    batch_index = 0 * np.ones((rois.shape[0], 1))
    rois_array = np.hstack((batch_index, rois))[np.newaxis, :]

    data = {'data': im_array,
            'rois': rois_array}
    label = {}

    return data, label, im_info


def get_rcnn_batch(roidb):
    """
    return a dict of multiple images
    :param roidb: a list of dict, whose length controls batch size
    ['images', 'flipped'] + ['gt_boxes', 'boxes', 'gt_overlap'] => ['bbox_targets']
    :return: data, label
    """
    num_images = len(roidb)
    imgs, roidb = get_image(roidb)
    im_array = tensor_vstack(imgs)

    assert config.TRAIN.BATCH_ROIS % config.TRAIN.BATCH_IMAGES == 0, \
        'BATCHIMAGES {} must divide BATCH_ROIS {}'.format(config.TRAIN.BATCH_IMAGES, config.TRAIN.BATCH_ROIS)
    rois_per_image = config.TRAIN.BATCH_ROIS / config.TRAIN.BATCH_IMAGES
    fg_rois_per_image = np.round(config.TRAIN.FG_FRACTION * rois_per_image).astype(int)

    rois_array = list()
    labels_array = list()
    bbox_targets_array = list()
    bbox_weights_array = list()

    for im_i in range(num_images):
        roi_rec = roidb[im_i]

        # infer num_classes from gt_overlaps
        num_classes = roi_rec['gt_overlaps'].shape[1]

        # label = class RoI has max overlap with
        rois = roi_rec['boxes']
        labels = roi_rec['max_classes']
        overlaps = roi_rec['max_overlaps']
        bbox_targets = roi_rec['bbox_targets']

        im_rois, labels, bbox_targets, bbox_weights = \
            sample_rois(rois, fg_rois_per_image, rois_per_image, num_classes,
                        labels, overlaps, bbox_targets)

        # project im_rois
        # do not round roi
        rois = im_rois
        batch_index = im_i * np.ones((rois.shape[0], 1))
        rois_array_this_image = np.hstack((batch_index, rois))
        rois_array.append(rois_array_this_image)

        # add labels
        labels_array.append(labels)
        bbox_targets_array.append(bbox_targets)
        bbox_weights_array.append(bbox_weights)

    rois_array = np.array(rois_array)
    labels_array = np.array(labels_array)
    bbox_targets_array = np.array(bbox_targets_array)
    bbox_weights_array = np.array(bbox_weights_array)

    data = {'data': im_array,
            'rois': rois_array}
    label = {'label': labels_array,
             'bbox_target': bbox_targets_array,
             'bbox_weight': bbox_weights_array}

    return data, label


def sample_rois(rois, fg_rois_per_image, rois_per_image, num_classes,
                labels=None, overlaps=None, bbox_targets=None, gt_boxes=None, gt_part_boxes=None):
    """
    generate random sample of ROIs comprising foreground and background examples
    :param rois: all_rois [n, 4]; e2e: [n, 5] with batch_index
    :param fg_rois_per_image: foreground roi number
    :param rois_per_image: total roi number
    :param num_classes: number of classes
    :param labels: maybe precomputed
    :param overlaps: maybe precomputed (max_overlaps)
    :param bbox_targets: maybe precomputed
    :param gt_boxes: optional for e2e [n, 5] (x1, y1, x2, y2, cls)
    :param gt_part_boxes: optional for e2e [n, 4] (x1, y1, x2, y2)
    :return: (labels, rois, bbox_targets, bbox_weights)
    """
    if labels is None:
        overlaps = bbox_overlaps(rois[:, 1:].astype(np.float), gt_boxes[:, :4].astype(np.float))
        gt_assignment = overlaps.argmax(axis=1)
        overlaps = overlaps.max(axis=1)
        labels = gt_boxes[gt_assignment, 4]

    fg_mask = overlaps >= config.TRAIN.FG_THRESH
    fg_assignment = gt_assignment.copy()
    fg_assignment[fg_mask == False] = -1
    labels[fg_mask == False] = 0

    # for each gt_box
    fg_indexes = []
    re_indexes = []
    for i in range(gt_boxes.shape[0]):
        idx = np.where(fg_assignment == i)[0]
        if len(idx) > 5:
            fidx = npr.choice(idx, 5, replace=False)
            ridx = np.setdiff1d(idx, fidx)
            fg_indexes += fidx.tolist()
            re_indexes += ridx.tolist()
        else:
            fg_indexes += idx.tolist()
    fg_indexes = np.array(fg_indexes)
    re_indexes = np.array(re_indexes)

    # foreground RoI with FG_THRESH overlap
    # fg_indexes = np.where(fg_mask)[0]
    # guard against the case when an image has fewer than fg_rois_per_image foreground RoIs
    fg_rois_per_this_image = np.minimum(fg_rois_per_image, fg_indexes.size)
    # Sample foreground regions without replacement
    if len(fg_indexes) > fg_rois_per_this_image:
        fg_indexes = npr.choice(fg_indexes, size=fg_rois_per_this_image, replace=False)

    # Select background RoIs as those within [BG_THRESH_LO, BG_THRESH_HI)
    bg_indexes = np.where((overlaps < config.TRAIN.BG_THRESH_HI) & (overlaps >= config.TRAIN.BG_THRESH_LO))[0]
    # Compute number of background RoIs to take from this image (guarding against there being fewer than desired)
    bg_rois_per_this_image = np.maximum(1, fg_rois_per_this_image * 3)
    bg_rois_per_this_image = np.minimum(bg_rois_per_this_image, rois_per_image - fg_rois_per_this_image)
    bg_rois_per_this_image = np.minimum(bg_rois_per_this_image, bg_indexes.size)
    # Sample foreground regions without replacement
    if len(bg_indexes) > bg_rois_per_this_image:
        bg_indexes = npr.choice(bg_indexes, size=bg_rois_per_this_image, replace=False)

    # regression target
    re_rois_per_this_image = np.maximum(0, rois_per_image - fg_rois_per_this_image - bg_rois_per_this_image)
    if len(re_indexes) > re_rois_per_this_image:
        re_indexes = npr.choice(re_indexes, size=re_rois_per_this_image, replace=False)
    
    # indexes selected
    keep_indexes = np.append(fg_indexes, bg_indexes)

    # pad more to ensure a fixed minibatch size
    # while keep_indexes.shape[0] < rois_per_image:
    #     gap = np.minimum(len(rois), rois_per_image - keep_indexes.shape[0])
    #     gap_indexes = npr.choice(range(len(rois)), size=gap, replace=False)
    #     keep_indexes = np.append(keep_indexes, gap_indexes)

    # select labels
    labels_orig = labels.copy()
    rois_orig = rois.copy()

    labels = labels[keep_indexes]
    # set labels of bg_rois to be 0
    # labels[fg_rois_per_this_image:] = 0
    rois = rois[keep_indexes]

    assert bbox_targets is None
    bbox_targets, bbox_weights = _compute_bbox_targets( \
            rois[:, 1:], gt_boxes[gt_assignment[keep_indexes], :4], labels, num_classes)

    # append regression targets
    if re_indexes.size > 0:
        labels_re = labels_orig[re_indexes]
        rois_re = rois_orig[re_indexes]
        bbox_targets_re, bbox_weights_re = _compute_bbox_targets( \
                rois_re[:, 1:], gt_boxes[gt_assignment[re_indexes], :4], labels_re, num_classes)
        rois = np.vstack((rois, rois_re))
        bbox_targets = np.vstack((bbox_targets, bbox_targets_re))
        bbox_weights = np.vstack((bbox_weights, bbox_weights_re))
        labels = np.append(labels, np.full_like(labels_re, -1))

    # pad to fit rois_per_image
    if labels.size < rois_per_image:
        pad_sz = rois_per_image - labels.size
        rois_pad = np.zeros((pad_sz, rois.shape[1]), dtype=rois.dtype)
        bbox_targets_pad = np.zeros((pad_sz, bbox_targets.shape[1]), dtype=bbox_targets.dtype)
        bbox_weights_pad = np.zeros((pad_sz, bbox_weights.shape[1]), dtype=bbox_weights.dtype)

        labels = np.append(labels, np.full((pad_sz,), -1, dtype=labels.dtype))
        rois = np.vstack((rois, rois_pad))
        bbox_targets = np.vstack((bbox_targets, bbox_targets_pad))
        bbox_weights = np.vstack((bbox_weights, bbox_weights_pad))

    # load or compute bbox_target
    # if bbox_targets is not None:
    #     bbox_target_data = bbox_targets[keep_indexes, :]
    # else:
    #     targets = bbox_transform(rois[:, 1:], gt_boxes[gt_assignment[keep_indexes], :4])
    #     if config.TRAIN.BBOX_NORMALIZATION_PRECOMPUTED:
    #         targets = ((targets - np.array(config.TRAIN.BBOX_MEANS))
    #                    / np.array(config.TRAIN.BBOX_STDS))
    #     bbox_target_data = np.hstack((labels[:, np.newaxis], targets))
    #
    # bbox_targets, bbox_weights = \
    #     expand_bbox_regression_targets(bbox_target_data, num_classes)

    '''
    # compute part classification and regression target
    part_targets = None
    part_weights = None
    part_lidx = None
    if gt_part_boxes is not None:
        part_boxes = gt_part_boxes[gt_assignment[keep_indexes], :]
        pidx = np.any(part_boxes != -1, axis=1)
        if pidx.size > 0:
            part_targets, part_lidx = bbox_transform_part(rois[pidx, 1:], part_boxes[pidx, :])
            if config.TRAIN.BBOX_NORMALIZATION_PRECOMPUTED:
                part_targets = ((part_targets - np.array(config.TRAIN.BBOX_MEANS))
                           / np.array(config.TRAIN.BBOX_STDS))
            part_target_data = np.hstack((labels[pidx, np.newaxis], targets))

            part_targets_pidx, part_weights_pidx = \
                    expand_bbox_regression_targets(part_target_data, num_classes)

            part_lidx = np.zeros_like(labels)
            part_targets = np.zeros_like(bbox_targets)
            part_weights = np.zeros_like(bbox_weights)
            part_lidx[pidx] = part_lidx
            part_targets[pidx, :] = part_targets_pidx
            part_weights[pidx, :] = part_weights_pidx
    '''
    # if bg_rois_per_this_image > fg_rois_per_this_image * 3:
    #     labels[(fg_rois_per_this_image*4):] = -1

    return rois, labels, bbox_targets, bbox_weights #, part_lidx, part_targets, part_weights


def _compute_bbox_targets(rois, gt_boxes, labels, num_classes):
    targets = bbox_transform(rois, gt_boxes)
    if config.TRAIN.BBOX_NORMALIZATION_PRECOMPUTED:
        targets = ((targets - np.array(config.TRAIN.BBOX_MEANS))
                   / np.array(config.TRAIN.BBOX_STDS))
    bbox_target_data = np.hstack((labels[:, np.newaxis], targets))

    bbox_targets, bbox_weights = \
        expand_bbox_regression_targets(bbox_target_data, num_classes)

    return bbox_targets, bbox_weights
