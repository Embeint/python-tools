#!/usr/bin/env python3

# import ctypes
import argparse

from infuse_iot.definitions.kv import slots as kv_slots
from infuse_iot.definitions.kv import structs as kv_structs
from infuse_iot.zephyr import lte as z_lte
from infuse_iot.zephyr.errno import errno

from . import kv_read, lte_pdp_ctx


class lte_modem_info(kv_read.kv_read):
    HELP = "Get LTE modem information"
    DESCRIPTION = "Get LTE modem information"

    class request(kv_read.kv_read.request):
        pass

    class response(kv_read.kv_read.response):
        pass

    @classmethod
    def add_parser(cls, parser):
        return

    def __init__(self, _args):
        super().__init__(argparse.Namespace(keys=[40, 41, 42, 43, 44, 45, 46]))

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query modem info ({errno.strerror(-return_code)})")
            return

        def struct_decode(t, r):
            if r.len <= 0:
                return None
            return t.vla_from_buffer_copy(bytes(r.data))

        def str_decode(r):
            if r.len <= 0:
                return "Unknown"
            return str(kv_structs.kv_string.vla_from_buffer_copy(bytes(r.data)))

        modem_imei = struct_decode(kv_slots.lte_modem_imei, response[3])
        pdp_ctx = struct_decode(kv_slots.lte_pdp_config, response[5])
        system_modes = struct_decode(kv_slots.lte_networking_modes, response[6])

        if pdp_ctx:
            pdp_str = f'"{str(pdp_ctx.apn)}" ({lte_pdp_ctx.lte_pdp_ctx.PDPFamily(pdp_ctx.family).name})'
        else:
            pdp_str = "unknown"
        if system_modes:
            system_mode = z_lte.LteSystemMode(system_modes.modes)
            system_pref = z_lte.LteSystemPreference(system_modes.prefer)
            modes_str = f"{system_mode} (Prefer: {system_pref})"
        else:
            modes_str = "default"

        print(f"\t   Model: {str_decode(response[0])}")
        print(f"\tFirmware: {str_decode(response[1])}")
        print(f"\t     ESN: {str_decode(response[2])}")
        print(f"\t    IMEI: {modem_imei.imei}")
        print(f"\t     SIM: {str_decode(response[4])}")
        print(f"\t     APN: {pdp_str}")
        print(f"\t    Mode: {modes_str}")
