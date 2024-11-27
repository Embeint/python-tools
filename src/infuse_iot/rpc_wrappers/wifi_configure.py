#!/usr/bin/env python3

import ctypes

import infuse_iot.generated.rpc_definitions as defs
from infuse_iot.commands import InfuseRpcCommand


class wifi_configure(InfuseRpcCommand, defs.kv_write):
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

    @staticmethod
    def kv_store_value_factory(id, value_bytes):
        class kv_store_value(ctypes.LittleEndianStructure):
            _fields_ = [
                ("id", ctypes.c_uint16),
                ("len", ctypes.c_uint16),
                ("data", ctypes.c_char * len(value_bytes)),
            ]
            _pack_ = 1

        return kv_store_value(id, len(value_bytes), value_bytes)

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--ssid", "-s", type=str, help="Network name")
        parser.add_argument("--psk", "-p", type=str, help="Network password")

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        ssid_bytes = self.args.ssid.encode("utf-8") + b"\x00"
        psk_bytes = self.args.psk.encode("utf-8") + b"\x00"

        ssid_struct = self.kv_store_value_factory(20, (len(ssid_bytes) + 1).to_bytes(1, "little") + ssid_bytes)
        psk_struct = self.kv_store_value_factory(21, (len(psk_bytes) + 1).to_bytes(1, "little") + psk_bytes)

        request_bytes = bytes(ssid_struct) + bytes(psk_struct)
        return bytes(self.request(2)) + request_bytes

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

        print_status("SSID", response.rc[0])
        print_status("PSK", response.rc[1])
