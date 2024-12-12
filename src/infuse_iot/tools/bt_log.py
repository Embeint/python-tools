#!/usr/bin/env python3

"""Connect to remote Bluetooth device serial logs"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"


from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.socket_comms import (
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)


class SubCommand(InfuseCommand):
    NAME = "bt_log"
    HELP = "Connect to remote Bluetooth device serial logs"
    DESCRIPTION = "Connect to remote Bluetooth device serial logs"

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 60.0)
        self._id = args.id

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--id", type=lambda x: int(x, 0), help="Infuse ID to receive logs for")

    def run(self):
        try:
            with self._client.connection(self._id, GatewayRequestConnectionRequest.DataType.LOGGING) as _:
                while rsp := self._client.receive():
                    if isinstance(rsp, ClientNotificationConnectionDropped):
                        print(f"Connection to {self._id:016x} lost")
                        break
                    if (
                        isinstance(rsp, ClientNotificationEpacketReceived)
                        and rsp.epacket.ptype == InfuseType.SERIAL_LOG
                    ):
                        print(rsp.epacket.payload.decode("utf-8"), end="")

        except KeyboardInterrupt:
            print(f"Disconnecting from {self._id:016x}")
        except ConnectionRefusedError:
            print(f"Unable to connect to {self._id:016x}")
