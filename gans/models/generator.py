import math

import torch
import torch.nn as nn

import gans.building_blocks as bb
from gans.archictures.PROGAN import FirstProGANBlock, UpsampleProGANBlock
from gans.archictures.HDCGAN import FirstHDCGANBlock, UpsampleHDCGANBlock
from gans.init import snn_weight_init, he_weight_init


class Generator(nn.Module):
    def __init__(self, hparams):
        super().__init__()

        self.hparams = hparams
        self.bias = True

        self.blocks = nn.ModuleList()
        self.to_rgb_converts = nn.ModuleList()

        if self.hparams.exponential_filter_multipliers:
            self.filter_multipliers = [
                2 ** (x + 1)
                for x in reversed(range(1, int(math.log2(self.hparams.image_size))))
            ]
        else:
            self.filter_multipliers = [
                2
                for x in range(1, int(math.log2(self.hparams.image_size)))
            ]

            self.filter_multipliers[-1] = 1


        if self.hparams.architecture == "progan":
            self.blocks.append(
                FirstProGANBlock(
                    noise_size=self.hparams.noise_size,
                    filters=self.filter_multipliers[0] * self.hparams.generator_filters,
                    bias=self.bias,
                    eq_lr=self.hparams.equalized_learning_rate,
                    spectral_normalization=self.hparams.spectral_normalization
                )
            )
        elif self.hparams.architecture == "hdcgan":
            self.blocks.append(
                FirstHDCGANBlock(
                    noise_size=self.hparams.noise_size,
                    filters=self.filter_multipliers[0] * self.hparams.generator_filters,
                    bias=self.bias,
                    eq_lr=self.hparams.equalized_learning_rate,
                    spectral_normalization=self.hparams.spectral_normalization
                )
            )

        self.to_rgb_converts.append(
            self.to_rgb_fn(
                self.filter_multipliers[0] * self.hparams.generator_filters,
                self.bias
            )
        )

        for pos, i in enumerate(self.filter_multipliers[1:]):
            self.blocks.append(
                self.block_fn(
                    self.filter_multipliers[pos - 1] * self.hparams.generator_filters,
                    i * self.hparams.generator_filters,
                    self.bias,
                    self.hparams.equalized_learning_rate,
                    self.hparams.spectral_normalization,
                    position=pos
                )
            )

            self.to_rgb_converts.append(
                self.to_rgb_fn(
                    i * self.hparams.generator_filters,
                    self.bias
                )
            )

        if self.hparams.weight_init == "he":
            self.apply(he_weight_init)
        elif self.hparams.weight_init == "snn":
            self.apply(snn_weight_init)

    def block_fn(self, in_channels, out_channels, bias=False, eq_lr=False, spectral_normalization=False, position=None):
        if self.hparams.architecture == "progan":
            return UpsampleProGANBlock(in_channels, out_channels, bias=bias, eq_lr=eq_lr, spectral_normalization=spectral_normalization, position=position)
        elif self.hparams.architecture == "hdcgan":
            return UpsampleHDCGANBlock(in_channels, out_channels, bias=bias, eq_lr=eq_lr, spectral_normalization=spectral_normalization, position=position)

    def to_rgb_fn(self, in_channels, bias=False):
        return nn.Sequential(
            bb.Conv2d(
                in_channels=in_channels,
                out_channels=self.hparams.image_channels,
                kernel_size=1,
                stride=1,
                padding=0,
                bias=bias,
                eq_lr=False,
                spectral_normalization=False
            )
        )

    def forward(self, x, y):
        outputs = []
        x = x.view(x.size(0), -1, 1, 1)

        for block, to_rgb in zip(self.blocks, self.to_rgb_converts):
            x = block(x)
            output = torch.tanh(to_rgb(x))
            outputs.append(output)

        return outputs
