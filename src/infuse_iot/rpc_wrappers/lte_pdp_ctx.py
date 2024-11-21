#!/usr/bin/env python3

import ctypes
import enum

from infuse_iot.commands import InfuseRpcCommand
import infuse_iot.generated.rpc_definitions as defs


class lte_pdp_ctx(InfuseRpcCommand, defs.kv_write):
    HELP = "Set the WiFi network SSID and PSK"
    DESCRIPTION = "Set the WiFi network SSID and PSK"

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("num", ctypes.c_uint8),
        ]
        _pack_ = 1

    class response(InfuseRpcCommand.VariableSizeResponse):
        base_fields = []
        var_name = "rc"
        var_type = ctypes.c_int16

    class PDPFamily(enum.IntEnum):
        IPv4 = 0
        IPv6 = 1
        IPv4v6 = 2
        NonIP = 3

    @staticmethod
    def kv_store_value_factory(id, value_bytes):
        class kv_store_value(ctypes.LittleEndianStructure):
            _fields_ = [
                ("id", ctypes.c_uint16),
                ("len", ctypes.c_uint16),
                ("data", ctypes.c_ubyte * len(value_bytes)),
            ]
            _pack_ = 1

        return kv_store_value(
            id, len(value_bytes), (ctypes.c_ubyte * len(value_bytes))(*value_bytes)
        )

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--apn", "-a", type=str, required=True, help="Access Point Name"
        )

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        # Hardcode IPv4 for now
        family_bytes = self.PDPFamily.IPv4.to_bytes(1, "little")
        apn_bytes = self.args.apn.encode("utf-8") + b"\x00"
        apn_bytes = len(apn_bytes).to_bytes(1, "little") + apn_bytes

        pdp_struct = self.kv_store_value_factory(45, family_bytes + apn_bytes)
        request_bytes = bytes(pdp_struct)
        return bytes(self.request(1)) + request_bytes

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid data buffer ({return_code})")
            return

        def print_status(name, rc):
            if rc < 0:
                print(f"{name} failed to write")
            elif rc == 0:
                print(f"{name} already matched")
            else:
                print(f"{name} updated")

        print_status("PDP Context", response.rc[0])
