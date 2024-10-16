#!/usr/bin/env python3

import ctypes
import ipaddress

from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr import net_if as z_nif
from infuse_iot.zephyr import lte as z_lte

from . import kv_read


class lte_modem_info(InfuseRpcCommand):
    HELP = "Get LTE modem information"
    DESCRIPTION = "Get LTE modem information"
    COMMAND_ID = 6

    class request(kv_read.kv_read.request):
        pass

    class response(kv_read.kv_read.response):
        pass

    @classmethod
    def add_parser(cls, parser):
        return

    def __init__(self, args):
        self.keys = [40, 41, 42, 43, 44]

    def request_struct(self):
        keys = (ctypes.c_uint16 * len(self.keys))(*self.keys)
        return bytes(self.request(len(self.keys))) + bytes(keys)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query modem info ({return_code})")
            return

        modem_model = bytes(response[0].data)
        modem_firmware = bytes(response[1].data)
        modem_esn = bytes(response[2].data)
        modem_imei = bytes(response[3].data)
        sim_uicc = bytes(response[4].data)

        print(f"\t   Model: {modem_model[1:].decode('utf-8')}")
        print(f"\tFirmware: {modem_firmware[1:].decode('utf-8')}")
        print(f"\t     ESN: {modem_esn[1:].decode('utf-8')}")
        print(f"\t    IMEI: {int.from_bytes(modem_imei, 'little')}")
        print(f"\t     SIM: {sim_uicc[1:].decode('utf-8')}")
