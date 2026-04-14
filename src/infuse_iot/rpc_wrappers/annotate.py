#!/usr/bin/env python3

from datetime import datetime, timedelta

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.generated.rpc_definitions import rpc_enum_data_logger
from infuse_iot.time import InfuseTime
from infuse_iot.util.ctypes import bytes_to_uint8
from infuse_iot.zephyr.errno import errno


class annotate(InfuseRpcCommand, defs.annotate):
    NAME = "annotate event"
    HELP = "Write a data annotation event to a tag"
    DESCRIPTION = "Write a labelled annotation event to a tag"

    @classmethod
    def annotate_factory(cls, logger, timestamp, label):
        label_bytes = label.encode('utf-8') + b"\x00"
        return bytes(cls.request(logger, timestamp)) + bytes_to_uint8(label_bytes)

    @staticmethod
    def parse_logger(raw: str) -> rpc_enum_data_logger:
        try:
            return rpc_enum_data_logger(int(raw))
        except ValueError:
            return rpc_enum_data_logger[raw.upper()]

    @classmethod
    def add_parser(cls, parser):
        # Logger configuration parsing
        l_parser = parser.add_mutually_exclusive_group(required=True)
        l_parser.add_argument("--onboard", dest="logger", action="store_const",
                              const=rpc_enum_data_logger.FLASH_ONBOARD)
        l_parser.add_argument("--external", dest="logger", action="store_const",
                              const=rpc_enum_data_logger.FLASH_REMOVABLE)
        l_parser.add_argument("--logger", "-l", type=cls.parse_logger,
                              help="TDF Data Logger to write the event to")

        # Timestamp parsing
        t_parser = parser.add_mutually_exclusive_group(required=True)
        t_parser.add_argument("--now", '-n', action="store_true",
                              help="Use current time as event timestamp")
        t_parser.add_argument("--timestamp", "-t", type=datetime.fromisoformat,
                              help="Event timestamp as unix epoch time")
        t_parser.add_argument("--delta", "-d", type=int,
                              help="Event timestamp as delta from current time in seconds")
        parser.add_argument("--string", "-s", type=str, help="Annotation Label", required=True)

    def __init__(self, args):
        self.label = args.string
        self.logger: rpc_enum_data_logger = args.logger
        if args.now:
            self.time = datetime.now()
        if args.timestamp is not None:
            self.time = args.timestamp
        if args.delta is not None:
            self.time = datetime.now() + timedelta(seconds=args.delta)

    def request_struct(self):
        timestamp = InfuseTime.gps_seconds_from_unix(int(self.time.timestamp()))
        return self.annotate_factory(self.logger, timestamp, self.label)

    def handle_response(self, return_code, response):
        self.handle_response_generic(return_code, self.logger, self.time, self.label)

    @staticmethod
    def handle_response_generic(return_code, logger: rpc_enum_data_logger, time: datetime, label: str):
        if return_code != 0:
            if return_code == -errno.ENODEV:
                reason = f": No such logger {logger.name}"
            elif return_code == -errno.EBADF:
                reason = f": Logger {logger.name} not ready"
            elif return_code == -errno.EINVAL:
                reason = f": Invalid event label '{label}'"
            else:
                reason = ""

            print(f"Failed to log annotation event ({errno.strerror(-return_code)}){reason}")
            return

        print(f"Wrote annotation to {logger.name} with timestamp {time.isoformat()}")
