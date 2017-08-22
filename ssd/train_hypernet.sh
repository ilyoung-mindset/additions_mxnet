python train.py \
    --network hypernet \
    --batch-size 32 \
    --data-shape 448 \
    --optimizer-name sgd \
    --freeze '' \
    --pretrained none \
    --epoch 1000 \
    --lr 1e-02 \
    --lr-factor 0.316227766 \
    --lr-steps 2,2,4,4,6,6,8,8 \
    --end-epoch 250 \
    --frequent 100 \
    --gpus 0,1
