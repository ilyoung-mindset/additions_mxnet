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
  --gpu 0 \
  --prefix model/pva911_twn_voc07 \
  --image_set 2007_trainval \
  --frequent 500 \
  --begin_epoch 0 \
  --end_epoch 100 \
  --lr 1e-04 \
  --lr_step 30,60,90 \
  --pretrained /home/hyunjoon/github/model_mxnet/pva911/pva911_21cls \
  --pretrained_epoch 0
  # --resume \
# python test.py --network resnet --gpu 1

