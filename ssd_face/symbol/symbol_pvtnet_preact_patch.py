from pvtnet_preact import get_pvtnet_preact
from net_block_clone import bn_relu_conv, clone_bn_relu_conv
from multibox_prior_layer import *
from anchor_target_layer import *
import numpy as np

def build_hyperfeature(data, ctx_data, name, num_filter_proj, num_filter_hyper, scale, use_global_stats):
    """
    """
    ctx_proj = bn_relu_conv(data=ctx_data, prefix_name=name+'/proj/', 
            num_filter=num_filter_proj, kernel=(3,3), pad=(1,1), 
            use_global_stats=use_global_stats, fix_gamma=False)
    ctx_up = mx.symbol.UpSampling(ctx_proj, num_args=1, name=name+'/up', scale=scale, sample_type='nearest')
    data_ = bn_relu_conv(data, prefix_name=name+'/conv/', 
            num_filter=num_filter_hyper-num_filter_proj, kernel=(3,3), pad=(1,1),
            use_global_stats=use_global_stats, fix_gamma=False)
    hyper = mx.symbol.Concat(data_, ctx_up, name=name+'/concat')
    return hyper

def multibox_layer(from_layers, num_classes, sizes, ratios, use_global_stats, clip=True):
    ''' multibox layer '''
    # parameter check
    assert len(from_layers) > 0, "from_layers must not be empty list"
    assert num_classes > 1, "num_classes {} must be larger than 1".format(num_classes)
    assert len(ratios) == len(from_layers), "ratios and from_layers must have same length"
    assert len(sizes) == len(from_layers), "sizes and from_layers must have same length"

    loc_pred_layers = []
    cls_pred_layers = []
    pred_layers = []
    anchor_layers = []
    # num_classes += 1 # always use background as label 0
    #

    for k, from_layer in enumerate(from_layers):
        from_name = from_layer.name
        num_anchors = len(sizes[k]) * len(ratios[k])
        num_loc_pred = num_anchors * 4
        num_cls_pred = num_anchors * num_classes

        pred_conv = bn_relu_conv(from_layer, prefix_name='{}_pred/'.format(from_name), 
                num_filter=num_loc_pred+num_cls_pred, kernel=(1,1), pad=(0,0), no_bias=False, 
                use_global_stats=use_global_stats, fix_gamma=False) # (n ac h w)
        pred_conv = mx.sym.transpose(pred_conv, axes=(0, 2, 3, 1)) # (n h w ac), a=num_anchors
        pred_conv = mx.sym.reshape(pred_conv, shape=(0, -3, -4, num_anchors, -1)) # (n h*w a c)
        pred_conv = mx.sym.reshape(pred_conv, shape=(0, -3, -1)) # (n h*w*a c)
        pred_layers.append(pred_conv)

    anchors = mx.sym.Custom(*from_layers, op_type='multibox_prior_python', 
            sizes=sizes, ratios=ratios, clip=int(clip))
    preds = mx.sym.concat(*pred_layers, num_args=len(pred_layers), dim=1)
    return [preds, anchors]

def get_symbol_train(num_classes, **kwargs):
    '''
    '''
    n_group = 5
    patch_size = 256
    if 'patch_size' in kwargs:
        patch_size = kwargs['patch_size']

    out_layers, ctx_layer = get_pvtnet_preact(use_global_stats=False, fix_gamma=False, n_group=n_group)
    label = mx.sym.var(name='label')

    from_layers = []
    # build hyperfeatures
    hyper_names = ['hyper012', 'hyper024', 'hyper048', 'hyper096']
    scales = [16, 8, 4, 2]
    for i, s in enumerate(scales):
        hyper_layer = build_hyperfeature(out_layers[i], ctx_layer, name=hyper_names[i], 
                num_filter_proj=s*6, num_filter_hyper=128, scale=s, use_global_stats=False)
        from_layers.append(hyper_layer)

    # 192
    conv192, src_syms = bn_relu_conv(out_layers[4], prefix_name='hyper192/conv/', 
            num_filter=128, kernel=(3,3), pad=(1,1), 
            use_global_stats=False, fix_gamma=False, get_syms=True)
    from_layers.append(conv192)

    rfs = [12.0 * (2**i) for i in range(len(out_layers))]
    n_from_layers = len(from_layers)
    sizes = []
    for i in range(n_from_layers):
        s = rfs[i] / float(patch_size)
        sizes.append([s, s / np.sqrt(2.0)])
    ratios = [[1.0, 0.8, 1.25]] * len(sizes)
    clip = True

    preds, anchors = multibox_layer(from_layers, num_classes, 
            sizes=sizes, ratios=ratios, 
            use_global_stats=False, clip=clip)

    tmp = mx.symbol.Custom(*[preds, anchors, label], name='anchor_target', op_type='anchor_target')
    pred_target = tmp[0]
    target_cls = tmp[1]
    target_reg = tmp[2]
    mask_reg = tmp[3]

    pred_cls = mx.sym.slice_axis(pred_target, axis=1, begin=0, end=num_classes)
    pred_reg = mx.sym.slice_axis(pred_target, axis=1, begin=num_classes, end=None)

    cls_loss = mx.symbol.SoftmaxOutput(data=pred_cls, label=target_cls, \
        ignore_label=-1, use_ignore=True, grad_scale=3.0, 
        normalization='valid', name="cls_prob")
    loc_diff = pred_reg - target_reg
    masked_loc_diff = mx.sym.broadcast_mul(loc_diff, mask_reg)
    loc_loss_ = mx.symbol.smooth_l1(name="loc_loss_", data=masked_loc_diff, scalar=1.0)
    loc_loss = mx.symbol.MakeLoss(loc_loss_, grad_scale=1.0, \
        normalization='valid', name="loc_loss")

    label_cls = mx.sym.MakeLoss(target_cls, grad_scale=0, name='label_cls')
    label_reg = mx.sym.MakeLoss(target_reg, grad_scale=0, name='label_reg')

    # group output
    out = mx.symbol.Group([cls_loss, loc_loss, label_cls, label_reg])
    return out

if __name__ == '__main__':
    import os
    os.environ['MXNET_ENGINE_TYPE'] = 'NaiveEngine'
    net = get_symbol_train(2)

    mod = mx.mod.Module(net, data_names=['data'], label_names=['label'])
    mod.bind(data_shapes=[('data', (2, 3, 256, 256))], label_shapes=[('label', (2, 5))])
    mod.init_params()

    args, auxs = mod.get_params()
    for k, v in sorted(args.items()):
        print k + ': ' + str(v.shape)
    for k, v in sorted(auxs.items()):
        print k + ': ' + str(v.shape)