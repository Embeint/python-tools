#!/usr/bin/env python3

import ctypes
import enum

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.rpc_wrappers.kv_write import kv_write
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct
from infuse_iot.zephyr.errno import errno


class lte_pdp_ctx(InfuseRpcCommand, defs.kv_write):
    HELP = "Set the LTE PDP context (IP family & APN)"
    DESCRIPTION = "Set the LTE PDP context (IP family & APN)"

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("num", ctypes.c_uint8),
        ]
        _pack_ = 1

    class response(VLACompatLittleEndianStruct):
        vla_field = ("rc", 0 * ctypes.c_int16)

    class PDPFamily(enum.IntEnum):
        IPv4 = 0
        IPv6 = 1
        IPv4v6 = 2
        NonIP = 3

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--apn", "-a", type=str, required=True, help="Access Point Name")
        family_group = parser.add_mutually_exclusive_group()
        family_group.add_argument("--ipv4", dest="family", action="store_const", const=cls.PDPFamily.IPv4, help="IPv4")
        family_group.add_argument("--ipv6", dest="family", action="store_const", const=cls.PDPFamily.IPv6, help="IPv6")
        family_group.add_argument(
            "--ipv4v6",
            dest="family",
            action="store_const",
            default=cls.PDPFamily.IPv4v6,
            const=cls.PDPFamily.IPv4v6,
            help="IPv4v6",
        )
        family_group.add_argument(
            "--nonip", dest="family", action="store_const", const=cls.PDPFamily.NonIP, help="NonIP"
        )

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        family_bytes = self.args.family.to_bytes(1, "little")
        apn_bytes = self.args.apn.encode("utf-8") + b"\x00"
        apn_bytes = len(apn_bytes).to_bytes(1, "little") + apn_bytes

        pdp_struct = kv_write.kv_store_value_factory(45, family_bytes + apn_bytes)
        request_bytes = bytes(pdp_struct)
        return bytes(self.request(1)) + request_bytes

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid data buffer ({errno.strerror(-return_code)})")
            return

        def print_status(name, rc):
            if rc < 0:
                print(f"{name} failed to write")
            elif rc == 0:
                print(f"{name} already matched")
            else:
                print(f"{name} updated")

        print_status("PDP Context", response.rc[0])
