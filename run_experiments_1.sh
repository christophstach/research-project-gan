git pull
clear

python gans/wgan_gp/train_wgan_gp.py --gpus 0 --dataloader-num-workers 10 --batch-size 64 --logger wandb --max-epochs 2000 --dataset cifar10 --strategy wgan-gp-0
python gans/wgan_gp/train_wgan_gp.py --gpus 0 --dataloader-num-workers 10 --batch-size 64 --logger wandb --max-epochs 2000 --dataset cifar10 --strategy wgan-gp-1