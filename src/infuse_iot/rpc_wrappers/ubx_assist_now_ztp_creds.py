#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class ubx_assist_now_ztp_creds(InfuseRpcCommand, defs.ubx_assist_now_ztp_creds):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--offset", "-o", type=int, default=0, help="Offset for UBX-MON-VER frame")

    def __init__(self, args):
        self._offset = args.offset

    def request_struct(self):
        return self.request(self._offset)

    def request_json(self):
        return {"mon_ver_offset": str(self._offset)}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query ZTP credentials ({errno.strerror(-return_code)})")
            return

        print(f"UBX-SEC-UNIQID: {bytes(response.ubx_sec_uniqid).hex()}")
        print(f"   UBX-MON-VER: {bytes(response.ubx_mon_ver).hex()}")
