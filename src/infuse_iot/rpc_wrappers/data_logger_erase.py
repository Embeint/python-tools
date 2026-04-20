#!/usr/bin/env python3

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class data_logger_erase(InfuseRpcCommand, defs.data_logger_erase):
    @classmethod
    def add_parser(cls, parser):
        logger = parser.add_mutually_exclusive_group(required=True)
        logger.add_argument("--onboard", action="store_true", help="Onboard flash logger")
        logger.add_argument("--removable", action="store_true", help="Removable flash logger (SD)")
        erase_mode = parser.add_mutually_exclusive_group()
        erase_mode.add_argument(
            "--erase-all",
            action="store_true",
            help="Erase entire address space, not just written blocks",
        )
        erase_mode.add_argument(
            "--erase-force",
            action="store_true",
            help="Erase entire address space, even if logger init failed",
        )
        # Erasing a complete flash chip can take a long time
        parser.add_argument("--timeout", type=int, default=60000, help="Duration to wait for erase to complete")

    def __init__(self, args):
        self.infuse_id = args.id
        self.timeout = args.timeout
        if args.onboard:
            self.logger = defs.rpc_enum_data_logger.FLASH_ONBOARD
        elif args.removable:
            self.logger = defs.rpc_enum_data_logger.FLASH_REMOVABLE
        else:
            raise NotImplementedError
        self.erase_all = 1 if args.erase_all else (0xAA if args.erase_force else 0)

    def command_timeout_ms(self) -> int:
        return self.timeout

    def request_struct(self):
        return self.request(self.logger, self.erase_all)

    def request_json(self):
        return {"logger": self.logger.name, "erase_empty": self.erase_all}

    def handle_response(self, return_code, _response):
        if return_code != 0:
            print(f"Failed to erase data logger ({errno.strerror(-return_code)})")
            return

        print("Data logger erased")
