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
  --network spotnet_lighter \
  --images $1 \
  --dir image \
  --ext .jpg \
  --prefix model/best/spotnet_lighter_bnfixed_768 \
  --epoch 22 \
  --max-data-shapes 2560 2560 \
  --thresh $TH_POS \
  --gpu 0
  # --cpu 
