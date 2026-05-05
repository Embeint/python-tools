#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class application_info(InfuseRpcCommand, defs.application_info):
    @classmethod
    def add_parser(cls, _parser):
        pass

    def __init__(self, _args):
        pass

    def request_struct(self):
        return self.request()

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query application info ({errno.strerror(-return_code)})")
            return

        r = response
        v = r.version
        print(f"\tApplication: 0x{r.application_id:08x}")
        print(f"\t    Version: {v.major}.{v.minor}.{v.revision}+{v.build_num:08x}")
        print(f"\t    Network: 0x{r.network_id:08x}")
        print(f"\t     Uptime: {r.uptime}")
        print(f"\t    Reboots: {r.reboots}")
        print(f"\t     KV CRC: 0x{r.kv_crc:08x}")
        print(f"\t   O Blocks: {r.data_blocks_internal}")
        print(f"\t   E Blocks: {r.data_blocks_external}")

    @classmethod
    def handle_json_response(cls, response: dict) -> None:
        rsp = defs.application_info.response(
            int(response["application_id"]),
            defs.rpc_struct_mcuboot_img_sem_ver(
                int(response["version"]["major"]),
                int(response["version"]["minor"]),
                int(response["version"]["revision"]),
                int(response["version"]["build_num"]),
            ),
            int(response["network_id"]),
            int(response["uptime"]),
            int(response["reboots"]),
            int(response["kv_crc"]),
            int(response["data_blocks_internal"]),
            int(response["data_blocks_external"]),
        )
        x = cls({})
        x.handle_response(0, rsp)
