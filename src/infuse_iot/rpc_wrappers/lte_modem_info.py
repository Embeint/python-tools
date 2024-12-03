#!/usr/bin/env python3

import ctypes
import os

import infuse_iot.generated.rpc_definitions as defs
from infuse_iot.commands import InfuseRpcCommand

from . import kv_read, lte_pdp_ctx


class lte_modem_info(InfuseRpcCommand, defs.kv_read):
    HELP = "Get LTE modem information"
    DESCRIPTION = "Get LTE modem information"

    class request(kv_read.kv_read.request):
        pass

    class response(kv_read.kv_read.response):
        pass

    @classmethod
    def add_parser(cls, parser):
        return

    def __init__(self, args):
        self.keys = [40, 41, 42, 43, 44, 45]

    def request_struct(self):
        keys = (ctypes.c_uint16 * len(self.keys))(*self.keys)
        return bytes(self.request(len(self.keys))) + bytes(keys)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query modem info ({os.strerror(-return_code)})")
            return

        unknown = b"_unknown"
        modem_model = bytes(response[0].data) if response[0].len > 0 else unknown
        modem_firmware = bytes(response[1].data) if response[1].len > 0 else unknown
        modem_esn = bytes(response[2].data) if response[2].len > 0 else unknown
        modem_imei = bytes(response[3].data) if response[3].len > 0 else unknown
        sim_uicc = bytes(response[4].data) if response[4].len > 0 else unknown
        if response[5].len > 0:
            family = lte_pdp_ctx.lte_pdp_ctx.PDPFamily(response[5].data[0])
            apn = bytes(response[5].data[2:]).decode("utf-8")
            pdp_cfg = f'"{apn}" ({family.name})'
        else:
            pdp_cfg = "default"

        print(f"\t   Model: {modem_model[1:].decode('utf-8')}")
        print(f"\tFirmware: {modem_firmware[1:].decode('utf-8')}")
        print(f"\t     ESN: {modem_esn[1:].decode('utf-8')}")
        print(f"\t    IMEI: {int.from_bytes(modem_imei, 'little')}")
        print(f"\t     SIM: {sim_uicc[1:].decode('utf-8')}")
        print(f"\t     APN: {pdp_cfg}")
