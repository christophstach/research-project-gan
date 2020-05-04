python gans/train_gan.py \
  --gpus 1 \
  --dataloader-num-workers 10 \
  --batch-size 128 \
  --logger wandb \
  --max-epochs 10000 \
  --dataset lsun \
  --loss-strategy ra-lsgan \
  --image-size 256 \
  --multi-scale-gradient
