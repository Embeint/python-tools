#!/usr/bin/env python3

import enum


class OperationalState(enum.IntEnum):
    UNKNOWN = 0
    NOTPRESENT = 1
    DOWN = 2
    LOWERLAYERDOWN = 3
    TESTING = 4
    DORMANT = 5
    UP = 6


class InterfaceFlags(enum.Flag):
    UP = 0x0001
    POINTOPOINT = 0x0002
    PROMISC = 0x0004
    NO_AUTO_START = 0x0008
    SUSPENDED = 0x0010
    FORWARD_MULTICASTS = 0x0020
    IPV4 = 0x0040
    IPV6 = 0x0080
    RUNNING = 0x0100
    LOWER_UP = 0x0200
    DORMANT = 0x0400
    IPV6_NO_ND = 0x0800
    IPV6_NO_MLD = 0x1000
    NO_TX_LOCK = 0x2000


class L2Flags(enum.Flag):
    MULTICAST = 0x0001
    MULTICAST_SKIP_SOLICIT = 0x0002
    PROMISC_MODE = 0x0004
    POINT_TO_POINT = 0x0008
