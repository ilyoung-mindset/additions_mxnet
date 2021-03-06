#!/usr/bin/env bash

# run this experiment with
# nohup bash script/resnet_voc07.sh 0,1 &> resnet_voc07.log &
# to use gpu 0,1 to train, gpu 0 to test and write logs to resnet_voc07.log
# gpu=${1:0:1}
gpu=${1:0:1}

export MXNET_CUDNN_AUTOTUNE_DEFAULT=0
export PYTHONUNBUFFERED=1

python train_end2end.py \
  --network pvanet_twn \
  --gpu 1 \
  --prefix model/pvanet_voc0712 \
  --dataset coco \
  --resume \
  --begin_epoch 0 \
  --end_epoch 150 \
  --lr_step 30,60,100
  # --pretrained model/pvanet_voc07 \
  # --pretrained_epoch 10 \
# python test.py --network resnet --gpu 1

