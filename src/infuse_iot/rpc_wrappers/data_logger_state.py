#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.time import humanised_seconds
from infuse_iot.zephyr.errno import errno


class data_logger_state(InfuseRpcCommand, defs.data_logger_state):
    @classmethod
    def add_parser(cls, parser):
        logger = parser.add_mutually_exclusive_group(required=True)
        logger.add_argument("--onboard", action="store_true", help="Onboard flash logger")
        logger.add_argument("--removable", action="store_true", help="Removable flash logger (SD)")

    def __init__(self, args):
        if args.onboard:
            self.logger = defs.rpc_enum_data_logger.FLASH_ONBOARD
        elif args.removable:
            self.logger = defs.rpc_enum_data_logger.FLASH_REMOVABLE
        else:
            raise NotImplementedError

    def request_struct(self):
        return self.request(self.logger)

    def request_json(self):
        return {"logger": self.logger.name}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query data logger state ({errno.strerror(-return_code)})")
            return

        def sizeof_fmt(num, suffix="B"):
            for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
                if abs(num) < 1024.0:
                    return f"{num:3.2f} {unit}{suffix}"
                num /= 1024.0
            return f"{num:.2f} Yi{suffix}"

        r = response
        total_logged = r.current_block * r.block_size
        percent = 100 * r.current_block / r.logical_blocks
        block_rate = (r.current_block - r.boot_block) / r.uptime
        byte_rate = r.bytes_logged / r.uptime

        print(f"{self.logger.name}")
        print(f"\t     Logged: {sizeof_fmt(total_logged)}")
        print(f"\t     Blocks: {r.current_block}/{r.logical_blocks} ({percent:.0f}%)")
        if r.earliest_block > 0:
            print(f"\t   Earliest: {r.earliest_block}")
        if byte_rate == 0.0:
            print("\t Block Rate: N/A")
            print("\t  Byte Rate: N/A")
        elif byte_rate < 0.1:
            print(f"\t Block Rate: {1 / block_rate:.2f} sec/block")
            print(f"\t  Byte Rate: {1 / byte_rate:.2f} sec/byte")
        else:
            print(f"\t Block Rate: {block_rate:.2f} blocks/sec")
            print(f"\t  Byte Rate: {sizeof_fmt(byte_rate)}/sec")
        if r.bytes_logged > 0:
            physical_wrap_time = r.physical_blocks / block_rate
            logical_fill_time = r.logical_blocks / block_rate
            print(f"\t   Phy Wrap: {humanised_seconds(int(physical_wrap_time))}")
            print(f"\t   Log Fill: {humanised_seconds(int(logical_fill_time))}")
