import math

import torch
import torch.nn as nn
import torch.nn.functional as F

import gans.building_blocks as bb


class SimpleCombiner(nn.Module):
    def __init__(self, hparams, in_channels):
        super().__init__()

        self.hparams = hparams
        self.in_channels = in_channels

    def forward(self, x1, x2):
        return torch.cat([x1, x2], dim=1)


class LinCatCombiner(nn.Module):
    def __init__(self, hparams, in_channels, bias=False, eq_lr=False, spectral_normalization=False):
        super().__init__()

        self.hparams = hparams
        self.in_channels = in_channels

        self.conv = bb.Conv2d(
            in_channels=self.hparams.image_channels,
            out_channels=self.hparams.image_channels,
            kernel_size=1,
            stride=1,
            padding=0,
            bias=bias,
            eq_lr=eq_lr,
            spectral_normalization=spectral_normalization
        )

    def forward(self, x1, x2):
        x1 = F.leaky_relu(self.conv(x1), 0.2)

        return torch.cat([x1, x2], dim=1)


class CatLinCombiner(nn.Module):
    def __init__(self, hparams, in_channels, bias=False, eq_lr=False, spectral_normalization=False):
        super().__init__()

        self.hparams = hparams
        self.in_channels = in_channels

        self.conv = bb.Conv2d(
            in_channels=in_channels + self.hparams.image_channels,
            out_channels=in_channels,
            kernel_size=1,
            stride=1,
            padding=0,
            bias=bias,
            eq_lr=eq_lr,
            spectral_normalization=spectral_normalization
        )

    def forward(self, x1, x2):
        x = torch.cat([x1, x2], dim=1)
        x = self.conv(x)
        x = F.leaky_relu(x, 0.2)

        return x


class DownsampleResidualBlock(nn.Module):
    def __init__(self, in_channels, out_channels, bias=False, eq_lr=False, spectral_normalization=False):
        super().__init__()

        self.conv1 = bb.Conv2d(in_channels, in_channels, kernel_size=3, stride=1, padding=1, bias=bias)
        self.conv2 = bb.Conv2d(in_channels, in_channels, kernel_size=3, stride=1, padding=1, bias=bias)

        self.downsample = bb.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=4,
            stride=2,
            padding=1,
            bias=bias,
            eq_lr=eq_lr,
            spectral_normalization=spectral_normalization
        )

    def forward(self, x):
        identity = x
        x = F.leaky_relu(self.conv1(x), 0.2)
        x = F.leaky_relu(self.conv2(x), 0.2)
        x = self.downsample(x + identity)

        return x


class DownsampleSimpleBlock(nn.Module):
    def __init__(self, in_channels, out_channels, bias=False, eq_lr=False, spectral_normalization=False):
        super().__init__()

        self.downsample = bb.Conv2d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=4,
            stride=2,
            padding=1,
            bias=bias,
            eq_lr=eq_lr,
            spectral_normalization=spectral_normalization
        )

    def forward(self, x):
        x = F.leaky_relu(self.downsample(x))

        return x


class Discriminator(nn.Module):
    def __init__(self, hparams):
        super().__init__()

        self.hparams = hparams
        self.bias = True
        self.hparams.spectral_normalization = True

        if self.hparams.multi_scale_gradient:
            if self.hparams.multi_scale_gradient_combiner == "simple":
                additional_channels = self.hparams.image_channels
            elif self.hparams.multi_scale_gradient_combiner == "cat_lin":
                additional_channels = 0
            elif self.hparams.multi_scale_gradient_combiner == "lin_cat":
                additional_channels = self.hparams.image_channels
            else:
                raise ValueError()
        else:
            additional_channels = 0

        self.blocks = nn.ModuleList()
        self.from_rgb_combiners = nn.ModuleList()

        self.blocks.append(
            self.block_fn(
                self.hparams.image_channels,
                self.hparams.discriminator_filters // 2 ** (int(math.log2(self.hparams.image_size)) - 3),
                self.bias,
                self.hparams.equalized_learning_rate,
                self.hparams.spectral_normalization
            )
        )

        # print(self.hparams.discriminator_filters // 2 ** (int(math.log2(self.hparams.image_size)) - 3))

        for i in range(2, int(math.log2(self.hparams.image_size)) - 1):
            o = int(math.log2(self.hparams.image_size)) - i

            self.blocks.append(
                self.block_fn(
                    self.hparams.discriminator_filters // 2 ** (o - 1) + additional_channels,
                    self.hparams.discriminator_filters // 2 ** (o - 2),
                    self.bias,
                    self.hparams.equalized_learning_rate,
                    self.hparams.spectral_normalization
                )
            )

            # print(
            #    self.hparams.discriminator_filters // 2 ** (o - 1),
            #    self.hparams.discriminator_filters // 2 ** (o - 2)
            # )

        for i in range(1, int(math.log2(self.hparams.image_size)) - 1):
            o = int(math.log2(self.hparams.image_size)) - i

            self.from_rgb_combiners.append(
                self.from_rgb_fn(
                    self.hparams.discriminator_filters // 2 ** (o - 2),
                    self.bias,
                    self.hparams.equalized_learning_rate,
                    self.hparams.spectral_normalization
                )
            )

        self.validator = nn.Sequential(
            bb.MinibatchStdDev(),
            bb.Conv2d(
                self.hparams.discriminator_filters + additional_channels + 1,
                self.hparams.discriminator_filters + additional_channels,
                kernel_size=3,
                stride=1,
                padding=1,
                bias=self.bias,
                eq_lr=self.hparams.equalized_learning_rate,
                spectral_normalization=self.hparams.spectral_normalization
            ),
            nn.LeakyReLU(0.2, inplace=True),
            bb.Conv2d(
                self.hparams.discriminator_filters + additional_channels,
                self.hparams.discriminator_filters + additional_channels,
                kernel_size=4,
                stride=1,
                padding=0,
                bias=self.bias,
                eq_lr=self.hparams.equalized_learning_rate,
                spectral_normalization=self.hparams.spectral_normalization
            ),
            nn.LeakyReLU(0.2, inplace=True),
            bb.Conv2d(
                self.hparams.discriminator_filters + additional_channels,
                1,
                kernel_size=1,
                stride=1,
                padding=0,
                bias=self.bias,
                eq_lr=self.hparams.equalized_learning_rate,
                spectral_normalization=self.hparams.spectral_normalization
            )
        )

    def block_fn(self, in_channels, out_channels, bias=False, eq_lr=False, spectral_normalization=False):
        # return DownsampleResidualBlock(in_channels, out_channels, bias=bias, eq_lr=eq_lr, spectral_normalization=spectral_normalization)
        return DownsampleSimpleBlock(in_channels, out_channels, bias=bias, eq_lr=eq_lr, spectral_normalization=spectral_normalization)

    def from_rgb_fn(self, in_channels, bias=False, eq_lr=False, spectral_normalization=False):
        if self.hparams.multi_scale_gradient_combiner == "simple":
            return SimpleCombiner(self.hparams, in_channels)
        elif self.hparams.multi_scale_gradient_combiner == "lin_cat":
            return LinCatCombiner(self.hparams, in_channels, bias=bias, eq_lr=False, spectral_normalization=False)
        elif self.hparams.multi_scale_gradient_combiner == "cat_lin":
            return CatLinCombiner(self.hparams, in_channels, bias=bias, eq_lr=False, spectral_normalization=False)
        else:
            raise ValueError()

    # Dropout is just used for WGAN-CT
    def forward(self, x, y, dropout=0.0, intermediate_output=False):
        x_hats = None

        for i in range(1, int(math.log2(self.hparams.image_size)) - 1):
            if x_hats is None:
                if isinstance(x, list):
                    x_hats = [self.blocks[i - 1](x[-1])]
                else:
                    x_hats = [self.blocks[i - 1](x)]
            else:
                x_hats.append(self.blocks[i - 1](x_hats[-1]))

            if isinstance(x, list): x_hats[i - 1] = self.from_rgb_combiners[i - 1](x[len(x) - i - 1], x_hats[i - 1])
            x_hats[i - 1] = torch.dropout(x_hats[i - 1], p=dropout, train=True)

        validity = self.validator(x_hats[-1])

        if intermediate_output:
            return validity, x.mean()
        else:
            return validity
