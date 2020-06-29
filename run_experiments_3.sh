python gans/train_gan.py \
  --gpus 1 \
  --max-epochs 10000 \
  --dataset celeba_hq \
  --dataloader-num-workers 10 \
  --exponential-filter-multipliers \
  --generator-filters 4 \
  --discriminator-filters 4 \
  --batch-size 32 \
  --image-size 256 \
  --noise-size 256 \
  --logger wandb \
  --loss-strategy wgan \
  --gradient-penalty-strategy 0-gp \
  --architecture hdcgan \
  --multi-scale-gradient \
  --spectral-normalization \
  --instance-noise