#!/usr/bin/env python3

import enum


class Bandwidth(enum.IntEnum):
    """
    LoRa Bandwidth
    Higher bandwidths result in faster datarates but lower range
    """

    BW_125_KHZ = 0
    BW_250_KHZ = 1
    BW_500_KHZ = 2


class SpreadingFactor(enum.IntEnum):
    """
    LoRa Spreading Factor
    Higher spreading factors result in lower datarates but higher range
    """

    SF6 = 6
    SF7 = 7
    SF8 = 8
    SF9 = 9
    SF10 = 10
    SF11 = 11
    SF12 = 12


class CodingRate(enum.IntEnum):
    """
    LoRa Coding Rate
    Higher coding rates improve error recovery but increase packet overhead
    """

    CR_4_5 = 1
    CR_4_6 = 2
    CR_4_7 = 3
    CR_4_8 = 4
