#!/usr/bin/env python3

import enum


class IPProtocol(enum.IntEnum):
    IPPROTO_IP = 0
    IPPROTO_ICMP = 1
    IPPROTO_IGMP = 2
    IPPROTO_ETH_P_ALL = 3
    IPPROTO_IPIP = 4
    IPPROTO_TCP = 6
    IPPROTO_UDP = 17
    IPPROTO_IPV6 = 41
    IPPROTO_ICMPV6 = 58
    IPPROTO_RAW = 255


class ProtocolFamily(enum.IntEnum):
    PF_UNSPEC = 0
    PF_INET = 1
    PF_INET6 = 2
    PF_PACKET = 3
    PF_CAN = 4
    PF_NET_MGMT = 5
    PF_LOCAL = 6
    PF_UNIX = PF_LOCAL


class AddressFamily(enum.IntEnum):
    AF_UNSPEC = ProtocolFamily.PF_UNSPEC
    AF_INET = ProtocolFamily.PF_INET
    AF_INET6 = ProtocolFamily.PF_INET6
    AF_PACKET = ProtocolFamily.PF_PACKET
    AF_CAN = ProtocolFamily.PF_CAN
    AF_NET_MGMT = ProtocolFamily.PF_NET_MGMT
    AF_LOCAL = ProtocolFamily.PF_LOCAL
    AF_UNIX = ProtocolFamily.PF_UNIX


class SockType(enum.IntEnum):
    SOCK_STREAM = 1
    SOCK_DGRAM = 2
    SOCK_RAW = 3
