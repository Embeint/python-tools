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
        parser.add_argument(
            "--erase-all",
            action="store_true",
            help="Erase entire address space, not just written blocks",
        )

    def __init__(self, args):
        self.infuse_id = args.id
        if args.onboard:
            self.logger = defs.rpc_enum_data_logger.FLASH_ONBOARD
        elif args.removable:
            self.logger = defs.rpc_enum_data_logger.FLASH_REMOVABLE
        else:
            raise NotImplementedError
        self.erase_all = 1 if args.erase_all else 0

    def request_struct(self):
        return self.request(self.logger, self.erase_all)

    def request_json(self):
        return {"logger": self.logger.name, "erase_empty": self.erase_all}

    def handle_response(self, return_code, _response):
        if return_code != 0:
            print(f"Failed to erase data logger ({errno.strerror(-return_code)})")
            return

        print("Data logger erased")
