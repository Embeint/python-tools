#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.generated.rpc_definitions import rpc_struct_mcuboot_img_sem_ver


class application_info(InfuseRpcCommand):
    HELP = "Get the current application info"
    DESCRIPTION = "Get the current application info"
    COMMAND_ID = 9

    class request(ctypes.LittleEndianStructure):
        _fields_ = []
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("application_id", ctypes.c_uint32),
            ("version", rpc_struct_mcuboot_img_sem_ver),
            ("network_id", ctypes.c_uint32),
            ("uptime", ctypes.c_uint32),
            ("reboots", ctypes.c_uint32),
            ("kv_crc", ctypes.c_uint32),
            ("data_blocks_internal", ctypes.c_uint32),
            ("data_blocks_external", ctypes.c_uint32),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, _parser):
        pass

    def __init__(self, _args):
        pass

    def request_struct(self):
        return self.request()

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({return_code})")
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
