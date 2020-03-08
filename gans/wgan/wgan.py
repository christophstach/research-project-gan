import os
from argparse import ArgumentParser
from collections import OrderedDict

import pytorch_lightning as pl
import torch
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import DataLoader
from torchvision.datasets import MNIST

from gans.wgan.models import Generator, Critic


class WGAN(pl.LightningModule):
    def __init__(self, hparams):
        super().__init__()

        self.hparams = hparams
        self.image_channels = self.hparams.image_channels
        self.image_width = self.hparams.image_width
        self.image_height = self.hparams.image_height
        self.alternation_interval = self.hparams.alternation_interval
        self.batch_size = self.hparams.batch_size
        self.noise_size = self.hparams.noise_size
        self.y_size = self.hparams.y_size
        self.learning_rate = self.hparams.learning_rate
        self.weight_clipping = self.hparams.weight_clipping
        self.sampling_interval = self.hparams.sampling_interval
        self.dataloader_num_workers = self.hparams.dataloader_num_workers

        self.generator = Generator(self.hparams)
        self.critic = Critic(self.hparams)

        self.real_images = None
        self.fake_images = None
        self.y = None

    def forward(self, x, y):
        return self.generator.forward(x, y)

    def generator_loss(self, fake_images, y):
        return -torch.mean(self.critic(fake_images, y))

    def critic_loss(self, real_images, fake_images, y):
        return -(torch.mean(self.critic(real_images, y)) - torch.mean(self.critic(fake_images, y)))

    def training_step(self, batch, batch_idx, optimizer_idx):
        self.real_images, self.y = batch

        if optimizer_idx == 0:  # Train generator
            noise = torch.randn(self.real_images.shape[0], self.noise_size, 1, 1)
            if self.on_gpu:
                noise = noise.cuda(self.real_images.device.index)

            self.fake_images = self.generator(noise, self.y)

            loss = self.generator_loss(self.fake_images, self.y)
            logs = {"generator_loss": loss}
            return OrderedDict({"loss": loss, "log": logs, "progress_bar": logs})

        if optimizer_idx == 1:  # Train critic
            noise = torch.randn(self.real_images.shape[0], self.noise_size, 1, 1)
            if self.on_gpu:
                noise = noise.cuda(self.real_images.device.index)

            self.fake_images = self.generator(noise, self.y)

            loss = self.critic_loss(self.real_images, self.fake_images.detach(), self.y)
            logs = {"critic_loss": loss}
            return OrderedDict({"loss": loss, "log": logs, "progress_bar": logs})

    # Logs an image for each class defined as noise size
    def on_epoch_end(self):
        if self.logger:
            num_images = self.y_size if self.y_size > 0 else 6
            noise = torch.randn(num_images, self.noise_size, 1, 1)
            y = torch.tensor(range(num_images))

            if self.on_gpu:
                noise = noise.cuda(self.real_images.device.index)
                y = y.cuda(self.real_images.device.index)

            fake_images = self.generator.forward(noise, y)
            grid = torchvision.utils.make_grid(fake_images, nrow=int(num_images / 2))

            # for tensorboard
            # self.logger.experiment.add_image("example_images", grid, 0)

            # for comet.ml
            self.logger.experiment.log_image(
                grid.detach().cpu().numpy(),
                name="generated images",
                image_channels="first"
            )

    def optimizer_step(self, current_epoch, batch_idx, optimizer, optimizer_idx, second_order_closure=None):
        optimizer.step()
        optimizer.zero_grad()

        # update generator opt every {self.alternation_interval} steps
        if optimizer_idx == 0 and batch_idx % self.alternation_interval == 0:
            optimizer.step()
            optimizer.zero_grad()

        # update critic opt every step
        if optimizer_idx == 1:
            optimizer.step()

            for weight in self.critic.parameters():
                weight.data.clamp_(-self.weight_clipping, self.weight_clipping)

            optimizer.zero_grad()

    def configure_optimizers(self):
        return [
            optim.RMSprop(self.generator.parameters(), lr=self.learning_rate),
            optim.RMSprop(self.critic.parameters(), lr=self.learning_rate)
        ]

    def prepare_data(self):
        # download only
        MNIST(os.getcwd(), train=True, download=True)

    def train_dataloader(self):
        # no download, just transform
        transform = transforms.Compose([
            transforms.Resize((self.image_width, self.image_height)),
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5])
        ])

        return DataLoader(
            MNIST(os.getcwd() + "/.datasets", train=True, download=False, transform=transform),
            num_workers=self.dataloader_num_workers,
            batch_size=self.batch_size
        )

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = ArgumentParser(parents=[parent_parser])
        train_group = parser.add_argument_group("Training")
        train_group.add_argument("-mine", "--min-epochs", type=int, default=1, help="Minimum number of epochs to train")
        train_group.add_argument("-maxe", "--max-epochs", type=int, default=50, help="Maximum number of epochs to train")
        train_group.add_argument("-acb", "--accumulate_grad_batches", type=int, default=1, help="Accumulate gradient batches")
        train_group.add_argument("-si", "--sampling-interval", type=int, default=1000, help="Log a generated sample sample very $n batches")
        train_group.add_argument("-dnw", "--dataloader-num-workers", type=int, default=8, help="Number of workers the dataloader uses")

        system_group = parser.add_argument_group("System")
        system_group.add_argument("-ic", "--image-channels", type=int, default=1, help="Generated image shape channels")
        system_group.add_argument("-iw", "--image-width", type=int, default=32, help="Generated image shape width")
        system_group.add_argument("-ih", "--image-height", type=int, default=32, help="Generated image shape height")
        system_group.add_argument("-bs", "--batch-size", type=int, default=32, help="Batch size")
        system_group.add_argument("-lr", "--learning-rate", type=float, default=0.00005, help="Learning rate of both optimizers")
        system_group.add_argument("-z", "--noise-size", type=int, default=100, help="Length of the noise vector")
        system_group.add_argument("-y", "--y-size", type=int, default=0, help="Length of the y/label vector")
        system_group.add_argument("-yes", "--y-embedding-size", type=int, default=10, help="Length of the y/label embedding vector")
        system_group.add_argument("-k", "--alternation-interval", type=int, default=5, help="Amount of steps the critic is trained for each training step of the generator")

        critic_group = parser.add_argument_group("Critic")
        critic_group.add_argument("-clrs", "--critic-leaky-relu-slope", type=float, default=0.2, help="Slope of the leakyReLU activation function in the critic")
        critic_group.add_argument("-cf", "--critic-filters", type=int, default=64, help="Filters in the critic (are multiplied with different powers of 2)")
        critic_group.add_argument("-cl", "--critic-length", type=int, default=2, help="Length of the critic or number of down sampling blocks")
        critic_group.add_argument("-wc", "--weight-clipping", type=float, default=0.01, help="Weights of the critic gets clipped at this point")

        generator_group = parser.add_argument_group("Generator")
        generator_group.add_argument("-gf", "--generator-filters", type=int, default=32, help="Filters in the generator (are multiplied with different powers of 2)")
        generator_group.add_argument("-gl", "--generator-length", type=int, default=3, help="Length of the generator or number of up sampling blocks (also determines the size of the output image)")

        return parser
