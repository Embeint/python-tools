#!/usr/bin/env python3

import binascii
import time

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.ctypes import UINT32_MAX
from infuse_iot.zephyr.errno import errno


class data_logger_read(InfuseRpcCommand, defs.data_logger_read):
    RPC_DATA_RECEIVE = True

    @classmethod
    def add_parser(cls, parser):
        logger = parser.add_mutually_exclusive_group(required=True)
        logger.add_argument("--onboard", action="store_true", help="Onboard flash logger")
        logger.add_argument("--removable", action="store_true", help="Removable flash logger (SD)")
        parser.add_argument("--start", type=int, default=0, help="First logger block to read (default 0)")
        parser.add_argument("--last", type=int, default=UINT32_MAX, help="Last logger block to read (default all)")

    def __init__(self, args):
        self.infuse_id = args.id
        self.start = args.start
        self.last = args.last
        if args.onboard:
            self.logger = defs.rpc_enum_data_logger.FLASH_ONBOARD
        elif args.removable:
            self.logger = defs.rpc_enum_data_logger.FLASH_REMOVABLE
        else:
            raise NotImplementedError
        self.expected_offset = 0
        self.output = b""
        self.start_time = time.time()

    def request_struct(self):
        return self.request(self.logger, self.start, self.last)

    def request_json(self):
        return {"logger": self.logger.name, "start_block": self.start, "last_block": self.last}

    def data_recv_cb(self, offset: int, data: bytes) -> None:
        if self.expected_offset == 0:
            self.start_time = time.time()
        if offset != self.expected_offset:
            missing = offset - self.expected_offset
            print(f"Missed {missing:d} bytes from offset 0x{self.expected_offset:08x}")
            self.output += b"\x00" * missing

        self.output += data
        # Next expected offset
        self.expected_offset = offset + len(data)

    def handle_response(self, return_code, response):
        end_time = time.time()
        if return_code != 0:
            print(f"Failed to read data logger ({errno.strerror(-return_code)})")
            return

        if response.sent_len != len(self.output):
            print(f"Unexpected received length ({response.sent_len} != {len(self.output)})")

        if response.sent_crc != binascii.crc32(self.output):
            print(f"Unexpected received CRC ({response.sent_crc:08x} != {binascii.crc32(self.output):08x})")

        duration = end_time - self.start_time
        bitrate = (len(self.output) * 8) / duration / 1024

        file_prefix = f"{self.infuse_id:016x}" if self.infuse_id else "gateway"
        output_file = f"{file_prefix}_{self.logger.name}.bin"
        with open(output_file, "wb") as f:
            f.write(self.output)
        print(f"Wrote {response.sent_len:d} bytes to {output_file} in {duration:.2f} sec ({bitrate:.3f} kbps)")
