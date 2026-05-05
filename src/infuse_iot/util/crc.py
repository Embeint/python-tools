#!/usr/bin/env python3

# Source of truth: https://reveng.sourceforge.io/crc-catalogue/all.htm


def crc16_kermit(data: bytes) -> int:
    """
    CRC-16-KERMIT Algorithm
    """
    crc = 0x0000
    for b in data:
        e = (crc ^ b) & 0xFF
        f = e ^ ((e << 4) & 0xFF)
        crc = (crc >> 8) ^ (f << 8) ^ (f << 3) ^ (f >> 4)
    return crc


def crc16_ccitt(data: bytes) -> int:
    """
    CRC-16-CCITT Algorithm (Alias of KERMIT)
    """
    return crc16_kermit(data)
