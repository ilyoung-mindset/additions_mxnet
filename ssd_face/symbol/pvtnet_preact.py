import mxnet as mx
from net_block_clone import *

def inception_group(data, prefix_group_name, n_curr_ch,
        num_filter_3x3, num_filter_1x1, 
        use_global_stats=False, fix_gamma=True, get_syms=False):
    """ 
    inception unit, only full padding is supported
    """
    syms = {}
    prefix_name = prefix_group_name + '/'

    incep_layers = []
    conv_ = data
    for ii in range(2):
        postfix_name = '3x3/' + str(ii+1)
        conv_, s = bn_relu_conv(conv_, prefix_name, postfix_name, 
                num_filter=num_filter_3x3, kernel=(3,3), pad=(1,1), 
                use_global_stats=use_global_stats, fix_gamma=fix_gamma, get_syms=True)
        syms['unit{}'.format(ii)] = s
        incep_layers.append(conv_)
    # poolup2 layer
    postfix_name = '3x3/3'
    conv_, s = bn_relu_conv_poolup2(conv_, prefix_name, postfix_name, 
            num_filter=num_filter_3x3, kernel=(3,3), pad=(1,1), 
            use_global_stats=use_global_stats, fix_gamma=fix_gamma, get_syms=True)
    syms['unit3'] = s
    incep_layers.append(conv_)

    res_ = mx.sym.concat(*incep_layers)

    if get_syms:
        return res_, num_filter_1x1, syms
    else:
        return res_, num_filter_1x1

def clone_inception_group(data, prefix_group_name, src_syms): 
    """ 
    inception unit, only full padding is supported
    """
    prefix_name = prefix_group_name + '/'

    incep_layers = []
    conv_ = data
    for ii in range(n_unit):
        postfix_name = '3x3/' + str(ii+1)
        conv_ = clone_bn_relu_conv(conv_, prefix_name, postfix_name, src_syms=src_syms['unit{}'.format(ii)])
        incep_layers.append(conv_)

    res_ = mx.sym.concat(*incep_layers)
    # concat_ = mx.sym.concat(*incep_layers)
    # res_ = clone_bn_relu_conv(concat_, prefix_name, '1x1', src_syms=src_syms['proj'])
    return res_

def get_pvtnet_preact(use_global_stats, fix_gamma=False):
    """ main shared conv layers """
    data = mx.sym.Variable(name='data')
    data_ = data / 128.0 # mx.sym.BatchNorm(data / 255.0, name='bn_data', fix_gamma=True, use_global_stats=use_global_stats)

    conv1_1 = mx.sym.Convolution(data_, name='conv1/1', num_filter=16, kernel=(3,3), pad=(1,1), no_bias=True) 
    conv1_2 = bn_crelu_conv(conv1_1, postfix_name='1/2', 
            num_filter=32, kernel=(3,3), pad=(1,1), 
            use_global_stats=use_global_stats, fix_gamma=fix_gamma) 
    conv1_3 = bn_crelu_conv(conv1_2, postfix_name='1/3', 
            num_filter=64, kernel=(3,3), pad=(1,1), 
            use_global_stats=use_global_stats, fix_gamma=fix_gamma) 
    concat1 = mx.sym.concat(conv1_2, conv1_3)
    #
    # conv2_1 = bn_crelu_conv(pool1, postfix_name='2/1', 
    #         num_filter=32, kernel=(3,3), pad=(1,1), 
    #         use_global_stats=use_global_stats, fix_gamma=fix_gamma) 
    # conv2_2 = bn_crelu_conv(conv2_1, postfix_name='2/2', 
    #         num_filter=64, kernel=(3,3), pad=(1,1), 
    #         use_global_stats=use_global_stats, fix_gamma=fix_gamma)  
    # concat2 = mx.sym.concat(conv2_1, conv2_2)

    nf_3x3 = [24, 32, 48, 64, 48] # 24 48 96 192
    nf_1x1 = [24*3, 32*3, 48*3, 64*3, 48*3]
    n_incep = [1, 1, 1, 1, 1]

    group_i = concat1
    groups = []
    n_curr_ch = 96
    for i in range(5):
        group_i = pool(group_i) 
        for j in range(n_incep[i]):
            # syms will be overwritten but it's ok we'll use the last one anyway
            group_i, n_curr_ch, syms = inception_group(group_i, 'g{}/u{}'.format(i+1, j+1), n_curr_ch, 
                    num_filter_3x3=nf_3x3[i], num_filter_1x1=nf_1x1[i], 
                    use_global_stats=use_global_stats, fix_gamma=fix_gamma, get_syms=True) 
        groups.append(group_i)

    # for context feature
    n_curr_ch = nf_1x1[-2]
    nf_3x3_ctx = 32
    nf_1x1_ctx = 32*3
    group_c = pool(groups[-2])
    for i in range(1):
        group_c, n_curr_ch = inception_group(group_c, 'g_ctx/u{}'.format(i+1), n_curr_ch, 
                num_filter_3x3=nf_3x3_ctx, num_filter_1x1=nf_1x1_ctx,
                use_global_stats=use_global_stats, fix_gamma=fix_gamma)

    # upsample feature for small face (12px)
    # conv0 = bn_relu_conv(groups[0], prefix_name='g0/', 
    #         num_filter=32, kernel=(1,1), 
    #         use_global_stats=use_global_stats, fix_gamma=False)
    # bn0 = bn_relu(conv0, name='g0/bnu', use_global_stats=use_global_stats, fix_gamma=True)
    # convu = mx.sym.Convolution(bn0, name='g0/convu', num_filter=128, kernel=(3,3), pad=(1,1), no_bias=True)
    # convu = subpixel_upsample(convu, 32, 2, 2)
    # groups = [convu] + groups
    return groups, group_c
