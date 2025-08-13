#!/usr/bin/env python3

"""Connect to remote Bluetooth device serial logs"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"


from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.epacket import interface
from infuse_iot.socket_comms import (
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF


class SubCommand(InfuseCommand):
    NAME = "bt_log"
    HELP = "Connect to remote Bluetooth device serial logs"
    DESCRIPTION = "Connect to remote Bluetooth device serial logs"

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()
        self._id = args.id
        self._data = args.data
        self._conn_timeout = args.conn_timeout

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--id", type=lambda x: int(x, 0), help="Infuse ID to receive logs for")
        parser.add_argument("--data", action="store_true", help="Subscribe to the data characteristic as well")
        parser.add_argument(
            "--conn-timeout", type=int, default=10000, help="Timeout to wait for a connection to the device (ms)"
        )

    def run(self):
        try:
            types = GatewayRequestConnectionRequest.DataType.LOGGING
            if self._data:
                types |= GatewayRequestConnectionRequest.DataType.DATA
            with self._client.connection(self._id, types, self._conn_timeout) as _:
                while evt := self._client.receive():
                    if evt is None:
                        continue
                    if isinstance(evt, ClientNotificationConnectionDropped):
                        print(f"Connection to {self._id:016x} lost")
                        break
                    if not isinstance(evt, ClientNotificationEpacketReceived):
                        continue
                    source = evt.epacket.route[0]
                    if source.infuse_id != self._id:
                        continue
                    if source.interface != interface.ID.BT_CENTRAL:
                        continue

                    if evt.epacket.ptype == InfuseType.SERIAL_LOG:
                        print(evt.epacket.payload.decode("utf-8"), end="")
                    if evt.epacket.ptype == InfuseType.TDF:
                        for tdf in self._decoder.decode(evt.epacket.payload):
                            t = tdf.data[-1]
                            t_str = f"{tdf.time:.3f}" if tdf.time else "N/A"
                            if len(tdf.data) > 1:
                                print(f"{t_str} TDF: {t.name}[{len(tdf.data)}]")
                            else:
                                print(f"{t_str} TDF: {t.name}")

        except KeyboardInterrupt:
            print(f"Disconnecting from {self._id:016x}")
        except ConnectionRefusedError:
            print(f"Unable to connect to {self._id:016x}")
