#!/usr/bin/env python3

import ipaddress

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr import lte as z_lte
from infuse_iot.zephyr import net_if as z_nif
from infuse_iot.zephyr.errno import errno


class lte_state_v2(InfuseRpcCommand, defs.lte_state_v2):
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

        reg_class = z_lte.RegistrationState
        lte_state = reg_class(lte.registration_state)

        print("Interface State:")
        print(f"\t          State: {z_nif.OperationalState(common.state).name}")
        print(f"\t       IF Flags: {z_nif.InterfaceFlags(common.if_flags)}")
        print(f"\t       L2 Flags: {z_nif.L2Flags(common.l2_flags)}")
        print(f"\t            MTU: {common.mtu}")
        print(f"\t           IPv4: {ipv4}")
        print(f"\t           IPv6: {ipv6}")
        print("LTE State:")
        print(f"\t      Reg State: {lte_state}")

        valid = (
            lte_state == reg_class.REGISTERED_HOME
            or lte_state == reg_class.REGISTERED_ROAMING
            or lte_state == reg_class.SEARCHING
        )
        access_tech = z_lte.AccessTechnology(lte.access_technology)
        if valid:
            if lte.earfcn != 0:
                freq_dl, freq_ul = z_lte.LteBands.earfcn_to_freq(lte.earfcn)
                freq_string = f" (UL: {int(freq_ul)}MHz, DL: {int(freq_dl)}MHz)"
            else:
                freq_string = ""
            country = z_lte.MobileCountryCodes.name_from_mcc(lte.mcc)
            active_str = f"{lte.psm_active_time} s" if lte.psm_active_time != 65535 else "N/A"
            edrx_interval_str = f"{lte.edrx_interval} s" if lte.edrx_interval != -1.0 else "N/A"
            edrx_window_str = f"{lte.edrx_paging_window} s" if lte.edrx_paging_window != -1.0 else "N/A"
            as_rai = defs.rpc_enum_support_status(lte.as_rai)
            cp_rai = defs.rpc_enum_support_status(lte.cp_rai)

            print(f"\t    Access Tech: {access_tech}")
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
            print(f"\t         AS-RAI: {as_rai.name}")
            print(f"\t         CP-RAI: {cp_rai.name}")
