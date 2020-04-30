python gans/train_gan.py \
  --gpus 0 \
  --dataloader-num-workers 10 \
  --batch-size 32 \
  --logger wandb \
  --max-epochs 10000 \
  --dataset lsun \
  --loss-strategy ra-lsgan \
  --gradient-penalty-strategy none \
  --image-size 128 \
  --multi-scale-gradient
