import mxnet as mx

'''
Basic blocks
'''
def data_norm(data, name, nch, bias=None, eps=1e-03, get_syms=False):
    bias_name = name + '_beta'
    if bias:
        bias_ = bias
    else:
        bias_ = mx.sym.var(name=bias_name, shape=(1, nch, 1, 1), lr_mult=1, wd_mult=1)

    kernel = (3, 3)
    pad = (1, 1)
    ones_ = mx.sym.ones(shape=(1,1,kernel[0],kernel[1])) / 9.0

    mean_ = mx.sym.mean(data, axis=1, keepdims=True)
    mean_ = mx.sym.Convolution(data=mean_, num_filter=1, weight=ones_, 
            kernel=kernel, pad=pad, no_bias=True)
    var_ = mx.sym.mean(mx.sym.square(data), axis=1, keepdims=True)
    var_ = mx.sym.Convolution(data=var_, num_filter=1, weight=ones_, 
            kernel=kernel, pad=pad, no_bias=True)
    var_ = mx.sym.maximum(var_ - mx.sym.square(mean_), 0.0)
    # var_ = mx.sym.broadcast_maximum(var_ - mx.sym.square(mean_), mx.sym.zeros(shape=(1,)))
    norm_ = mx.sym.sqrt(var_ + eps)
    data_ = mx.sym.broadcast_sub(data, mean_)
    data_ = mx.sym.broadcast_div(data_, norm_)
    data_ = mx.sym.broadcast_add(data_, bias_)

    if get_syms:
        syms = {'bias': bias_ }
        return data_, syms
    else:
        return data_

def bn_relu(data, name, use_global_stats=False, fix_gamma=False):
    #
    bn_ = mx.sym.BatchNorm(data, use_global_stats=use_global_stats, fix_gamma=fix_gamma, name=name)
    relu_ = mx.sym.Activation(bn_, act_type='relu')
    return relu_

def conv_poolup2(data, name, num_filter, kernel=(3,3), pad=(0,0), no_bias=True, get_syms=False):
    #
    pool_ = pool(data, kernel=(2,2), stride=(2,2))
    n_filter_pooled = num_filter * 4
    wd_mult = 0.25
    conv_ = mx.sym.Convolution(pool_, name=name, num_filter=n_filter_pooled, 
            attr={'__wd_mult__': str(wd_mult)}, 
            kernel=kernel, pad=pad, no_bias=no_bias)
    up_ = subpixel_upsample(conv_, num_filter, 2, 2)
    if get_syms:
        syms = {'conv': conv_}
        return up_, syms
    else:
        return up_

def bn_relu_conv(data, prefix_name='', postfix_name='', 
        num_filter=0, kernel=(3,3), pad=(0,0), stride=(1,1), num_group=1, use_crelu=False, 
        use_dn=False, nch=0, 
        use_global_stats=False, fix_gamma=False, no_bias=True, get_syms=False):
    #
    assert prefix_name != '' or postfix_name != ''
    conv_name = prefix_name + 'conv' + postfix_name
    bn_name = prefix_name + 'bn' + postfix_name
    syms = {}
    if use_dn:
        bn_, s = data_norm(data, bn_name, nch, get_syms=True)
        syms.update(s)
    else:
        bn_ = mx.sym.BatchNorm(data, use_global_stats=use_global_stats, fix_gamma=fix_gamma, name=bn_name)
        syms['bn'] = bn_
    relu_ = mx.sym.Activation(bn_, act_type='relu')
    conv_ = mx.sym.Convolution(relu_, name=conv_name, num_filter=num_filter, 
            num_group=num_group, kernel=kernel, pad=pad, stride=stride, no_bias=no_bias)
    syms['conv'] = conv_
    if use_crelu:
        concat_name = prefix_name + 'concat' + postfix_name
        conv_ = mx.sym.concat(conv_, -conv_, name=concat_name)
        syms['concat'] = conv_
    if get_syms:
        return conv_, syms
    else:
        return conv_

def bn_relu_conv_poolup2(data, prefix_name='', postfix_name='', 
        num_filter=0, kernel=(3,3), pad=(0,0), use_crelu=False, 
        use_dn=False, nch=0, 
        use_global_stats=False, fix_gamma=False, no_bias=True, get_syms=False):
    #
    assert prefix_name != '' or postfix_name != ''
    conv_name = prefix_name + 'conv' + postfix_name
    bn_name = prefix_name + 'bn' + postfix_name
    syms = {}
    if use_dn:
        bn_, s = data_norm(data, bn_name, nch, get_syms=True)
        syms.update(s)
    else:
        bn_ = mx.sym.BatchNorm(data, use_global_stats=use_global_stats, fix_gamma=fix_gamma, name=bn_name)
        syms['bn'] = bn_
    relu_ = mx.sym.Activation(bn_, act_type='relu')
    conv_, syms_conv = conv_poolup2(relu_, name=conv_name, num_filter=num_filter, 
            kernel=kernel, pad=pad, no_bias=no_bias, get_syms=True)
    syms.update(syms_conv)
    if use_crelu:
        concat_name = prefix_name + 'concat' + postfix_name
        conv_ = mx.sym.concat(conv_, -conv_, name=concat_name)
        syms['concat'] = conv_
    if get_syms:
        return conv_, syms
    else:
        return conv_

def pool(data, name=None, kernel=(2,2), stride=(2,2), pool_type='max'):
    pool_ = mx.sym.Pooling(data=data, name=name, kernel=kernel, stride=stride, pool_type=pool_type)
    return pool_

def convaspool(data, num_filter, name='', use_global_stats=False, fix_gamma=False):
    #
    proj_ = bn_relu_conv(data, prefix_name=name+'/pproj/', 
            num_filter=num_filter/4, kernel=(1,1), use_global_stats=use_global_stats, fix_gamma=fix_gamma)
    conv_ = bn_relu_conv(proj_, prefix_name=name+'/pconv/', 
            num_filter=num_filter, kernel=(2,2), stride=(2,2), 
            use_global_stats=use_global_stats, fix_gamma=fix_gamma)
    return conv_

'''
Cloning blocks
'''
def clone_conv(data, name, src_layer):
    attrs = src_layer.list_attr()
    no_bias = False
    if 'no_bias' in attrs:
        no_bias = attrs['no_bias'] == 'True'
    inputs = src_layer.get_children()

    if no_bias == False:
        conv = mx.symbol.Convolution(name=name, data=data,
                weight=inputs[1], 
                bias=inputs[2],
                **attrs)
    else:
        conv = mx.symbol.Convolution(name=name, data=data,
                weight=inputs[1], 
                **attrs)
    return conv

def clone_bn(data, name, src_layer):
    attrs = src_layer.list_attr()
    inputs = src_layer.get_children()

    bn = mx.symbol.BatchNorm(name=name, data=data, 
            beta=inputs[2], 
            gamma=inputs[1], 
            **attrs)
    return bn

def clone_conv_poolup2(data, name, src_layer):
    pool_ = pool(data, kernel=(2,2), stride=(2,2))
    conv_ = clone_conv(pool_, name=name, src_layer=src_layer)
    attr = src_layer.list_attr()
    num_filter = int(attr['num_filter']) / 4
    up_ = subpixel_upsample(conv_, num_filter, 2, 2)
    return up_

def clone_bn_relu_conv(data, prefix_name='', postfix_name='', src_syms=None):
    assert prefix_name != '' or postfix_name != ''
    conv_name = prefix_name + 'conv' + postfix_name
    bn_name = prefix_name + 'bn' + postfix_name
    if 'bias' in src_syms:
        bn = data_norm(data, name=bn_name, nch=0, bias=src_syms['bias'])
    else:
        bn = clone_bn(data, name=bn_name, src_layer=src_syms['bn'])
    relu_ = mx.sym.Activation(bn, act_type='relu')
    conv_ = clone_conv(relu_, name=conv_name, src_layer=src_syms['conv'])
    if 'concat' in src_syms:
        concat_name = prefix_name + 'concat' + postfix_name
        conv_ = mx.sym.concat(conv_, -conv_, name=concat_name)
    return conv_

def clone_bn_relu_conv_poolup2(data, prefix_name='', postfix_name='', src_syms=None):
    #
    assert prefix_name != '' or postfix_name != ''
    conv_name = prefix_name + 'conv' + postfix_name
    bn_name = prefix_name + 'bn' + postfix_name
    if 'bias' in src_syms:
        bn = data_norm(data, name=bn_name, nch=0, bias=src_syms['bias'])
    else:
        bn = clone_bn(data, name=bn_name, src_layer=src_syms['bn'])
    relu_ = mx.sym.Activation(bn, act_type='relu')
    conv_ = clone_conv_poolup2(relu_, name=conv_name, src_layer=src_syms['conv'])
    if 'concat' in src_syms:
        concat_name = prefix_name + 'concat' + postfix_name
        conv_ = mx.sym.concat(conv_, -conv_, name=concat_name)
    return conv_

'''
Misc
'''
def subpixel_upsample(data, ch, c, r):
    if r == 1 and c == 1:
        return data
    X = mx.sym.reshape(data=data, shape=(-3, 0, 0)) # (bsize*ch*r*c, a, b)
    X = mx.sym.reshape(data=X, shape=(-4, -1, r*c, 0, 0)) # (bsize*ch, r*c, a, b)
    X = mx.sym.transpose(data=X, axes=(0, 3, 2, 1)) # (bsize*ch, b, a, r*c)
    X = mx.sym.reshape(data=X, shape=(0, 0, -1, c)) # (bsize*ch, b, a*r, c)
    X = mx.sym.transpose(data=X, axes=(0, 2, 1, 3)) # (bsize*ch, a*r, b, c)
    X = mx.sym.reshape(data=X, shape=(-4, -1, ch, 0, -3)) # (bsize, ch, a*r, b*c)
    return X
