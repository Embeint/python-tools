#!/usr/bin/env python3

import ctypes
import ipaddress

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr import net_if as z_nif
from infuse_iot.zephyr import wifi as z_wifi
from infuse_iot.zephyr.errno import errno


class interface_state(ctypes.LittleEndianStructure):
    _fields_ = [
        ("_state", ctypes.c_uint8),
        ("_if_flags", ctypes.c_uint32),
        ("_l2_flags", ctypes.c_uint16),
        ("mtu", ctypes.c_uint16),
        ("ipv4", 4 * ctypes.c_uint8),
        ("ipv6", 16 * ctypes.c_uint8),
    ]
    _pack_ = 1

    @property
    def state(self):
        return z_nif.OperationalState(self._state)

    @property
    def if_flags(self):
        return z_nif.InterfaceFlags(self._if_flags)

    @property
    def l2_flags(self):
        return z_nif.L2Flags(self._l2_flags)


class wifi_state_struct(ctypes.LittleEndianStructure):
    _fields_ = [
        ("_state", ctypes.c_uint8),
        ("ssid", 32 * ctypes.c_char),
        ("bssid", 6 * ctypes.c_char),
        ("_band", ctypes.c_uint8),
        ("channel", ctypes.c_uint8),
        ("_iface_mode", ctypes.c_uint8),
        ("_link_mode", ctypes.c_uint8),
        ("_security", ctypes.c_uint8),
        ("rssi", ctypes.c_int8),
        ("beacon_interval", ctypes.c_uint16),
        ("twt_capable", ctypes.c_uint8),
    ]
    _pack_ = 1

    @property
    def state(self):
        return z_wifi.WiFiState(self._state)

    @property
    def band(self):
        return z_wifi.FrequencyBand(self._band)

    @property
    def interface_mode(self):
        return z_wifi.InterfaceMode(self._iface_mode)

    @property
    def link_mode(self):
        return z_wifi.LinkMode(self._link_mode)

    @property
    def security_type(self):
        return z_wifi.SecurityType(self._security)


class wifi_state(InfuseRpcCommand, defs.wifi_state):
    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("common", interface_state),
            ("wifi", wifi_state_struct),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        return

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        return self.request()

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({errno.strerror(-return_code)})")
            return

        common = response.common
        wifi = response.wifi

        # Address formatting
        ipv4 = ipaddress.IPv4Address(bytes(common.ipv4))
        ipv6 = ipaddress.IPv6Address(bytes(common.ipv6))
        bssid = ":".join([f"{b:02x}" for b in wifi.bssid])

        print("Interface State:")
        print(f"\t          State: {common.state.name}")
        print(f"\t       IF Flags: {common.if_flags}")
        print(f"\t       L2 Flags: {common.l2_flags}")
        print(f"\t            MTU: {common.mtu}")
        print(f"\t           IPv4: {ipv4}")
        print(f"\t           IPv6: {ipv6}")
        print("WiFi State:")
        print(f"\t          State: {wifi.state.name}")
        if wifi.state >= z_wifi.WiFiState.AUTHENTICATING:
            try:
                print(f"\t           SSID: {wifi.ssid.decode('utf-8')}")
            except UnicodeDecodeError:
                print(f"\t           SSID: Decode Error (Hex: {wifi.ssid.hex()})")
            print(f"\t          BSSID: {bssid}")
            print(f"\t Frequency Band: {wifi.band}")
            print(f"\t        Channel: {wifi.channel}")
            print(f"\t        IF Mode: {wifi.interface_mode.name}")
            print(f"\t      Link Mode: {wifi.link_mode}")
            print(f"\t       Security: {wifi.security_type}")
            print(f"\t           RSSI: {wifi.rssi} dBm")
            print(f"\tBeacon Interval: {wifi.beacon_interval} ms")
            print(f"\t    TWT Capable: {'Yes' if wifi.twt_capable else 'No'}")
