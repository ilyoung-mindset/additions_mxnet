#!/bin/bash
# from scratch
# python train.py \
#     --dataset wider_patch \
#     --image-set trainval \
#     --val-image-set '' \
#     --devkit-path /home/hyunjoon/dataset/wider \
#     --network spotnet_lighter_patch \
#     --batch-size 16 \
#     --from-scratch 1 \
#     --gpu 1 \
#     --prefix model/spotnet_lighter_patch_trainval \
#     --data-shape 256 \
#     --end-epoch 1 \
#     --frequent 50 \
#     --monitor 1000 \
#     --lr 0.001 \
#     --wd 0.0001

# full training
python train.py \
    --dataset wider \
    --image-set trainval \
    --val-image-set '' \
    --devkit-path /home/hyunjoon/dataset/wider \
    --network spotnet_lighter_bnfixed \
    --batch-size 2 \
    --gpu 1 \
    --prefix model/spotnet_lighter_trainval_bnfixed \
    --data-shape 768 \
    --frequent 800 \
    --lr 1e-03 \
    --lr-factor 0.316228 \
    --lr-steps 2,2,3,3,3,3 \
    --wd 1e-05 \
    --pretrained model/spotnet_lighter_trainval_bnfixed_768 \
    --epoch 1
    # --resume 23
    # --lr-steps 10,15,18,21 \
    # --monitor 2000 \
