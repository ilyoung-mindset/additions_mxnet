#!/bin/bash
if [[ "$#" -lt 1 ]]; then
  echo "Image name not given."
  exit
fi
if [[ "$#" -gt 1 ]]
then
  TH_POS=$2
else
  TH_POS=0.55
fi

python demo.py \
  --network ron_480 \
  --images $1 \
  --dir image \
  --ext .jpg \
  --prefix ./model/ron_voc_480 \
  --epoch 1000 \
  --max-data-shapes 960 960 \
  --thresh $TH_POS \
  --gpu 1
  # --cpu
