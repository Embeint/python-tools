#!/usr/bin/env python3

import ctypes
import ipaddress

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr import lte as z_lte
from infuse_iot.zephyr import net_if as z_nif
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


class lte_state_struct(ctypes.LittleEndianStructure):
    _fields_ = [
        ("_state", ctypes.c_uint8),
        ("_act", ctypes.c_uint8),
        ("mcc", ctypes.c_uint16),
        ("mnc", ctypes.c_uint16),
        ("cell_id", ctypes.c_uint32),
        ("tac", ctypes.c_uint32),
        ("tau", ctypes.c_int32),
        ("earfcn", ctypes.c_uint16),
        ("band", ctypes.c_uint8),
        ("psm_active_time", ctypes.c_int16),
        ("edrx_interval", ctypes.c_float),
        ("edrx_window", ctypes.c_float),
        ("rsrp", ctypes.c_int16),
        ("rsrq", ctypes.c_int8),
    ]
    _pack_ = 1

    @property
    def state(self):
        return z_lte.RegistrationState(self._state)

    @property
    def access_technology(self):
        return z_lte.AccessTechnology(self._act)


class lte_state(InfuseRpcCommand, defs.lte_state):
    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("common", interface_state),
            ("lte", lte_state_struct),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        return

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        return self.request()

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({errno.strerror(-return_code)})")
            return

        common = response.common
        lte = response.lte

        # Address formatting
        ipv4 = ipaddress.IPv4Address(bytes(common.ipv4))
        ipv6 = ipaddress.IPv6Address(bytes(common.ipv6))

        print("Interface State:")
        print(f"\t          State: {common.state.name}")
        print(f"\t       IF Flags: {common.if_flags}")
        print(f"\t       L2 Flags: {common.l2_flags}")
        print(f"\t            MTU: {common.mtu}")
        print(f"\t           IPv4: {ipv4}")
        print(f"\t           IPv6: {ipv6}")
        print("LTE State:")
        print(f"\t      Reg State: {lte.state}")

        reg_class = z_lte.RegistrationState
        valid = (
            lte.state == reg_class.REGISTERED_HOME
            or lte.state == reg_class.REGISTERED_ROAMING
            or lte.state == reg_class.SEARCHING
        )
        if valid:
            if lte.earfcn != 0:
                freq_dl, freq_ul = z_lte.LteBands.earfcn_to_freq(lte.earfcn)
                freq_string = f" (UL: {int(freq_ul)}MHz, DL: {int(freq_dl)}MHz)"
            else:
                freq_string = ""
            country = z_lte.MobileCountryCodes.name_from_mcc(lte.mcc)
            active_str = f"{lte.psm_active_time} s" if lte.psm_active_time != 65535 else "N/A"
            edrx_interval_str = f"{lte.edrx_interval} s" if lte.edrx_interval != -1.0 else "N/A"
            edrx_window_str = f"{lte.edrx_window} s" if lte.edrx_window != -1.0 else "N/A"
            print(f"\t    Access Tech: {lte.access_technology}")
            print(f"\t   Country Code: {lte.mcc} ({country})")
            print(f"\t   Network Code: {lte.mnc}")
            print(f"\t        Cell ID: {lte.cell_id}")
            print(f"\t  Tracking Area: {lte.tac}")
            print(f"\t            TAU: {lte.tau} s")
            print(f"\t         EARFCN: {lte.earfcn}{freq_string}")
            print(f"\t           Band: {lte.band}")
            print(f"\tPSM Active Time: {active_str}")
            print(f"\t  eDRX Interval: {edrx_interval_str}")
            print(f"\t    eDRX Window: {edrx_window_str}")
            print(f"\t           RSRP: {lte.rsrp} dBm")
            print(f"\t           RSRQ: {lte.rsrq} dB")
