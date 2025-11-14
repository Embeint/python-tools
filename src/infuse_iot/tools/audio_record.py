#!/usr/bin/env python3

"""Connect to remote Bluetooth device serial logs"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import time
import wave
from contextlib import ExitStack

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.definitions import tdf as tdf_defs
from infuse_iot.epacket import interface
from infuse_iot.socket_comms import (
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF
from infuse_iot.util.console import Console


class SubCommand(InfuseCommand):
    NAME = "audio_record"
    HELP = "Record audio data to a file from TDF"
    DESCRIPTION = "Record audio data to a file from TDF"

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()
        if args.gateway:
            self._id = InfuseID.GATEWAY
        else:
            self._id = args.id
        self._file_prefix = f"{args.name}_" if args.name else ""
        self._conn_timeout = args.conn_timeout
        self._freq: int | None = None
        self._left: wave.Wave_write | None = None
        self._right: wave.Wave_write | None = None

    @classmethod
    def add_parser(cls, parser):
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--gateway", action="store_true", help="Run command on local gateway")
        addr_group.add_argument("--id", type=lambda x: int(x, 0), help="Infuse ID to run command on")
        parser.add_argument(
            "--conn-timeout", type=int, default=10000, help="Timeout to wait for a connection to the device (ms)"
        )
        parser.add_argument("--name", type=str, help="Filename prefix")

    def handle_channel(self, channel: str, stack: ExitStack, tdf: TDF.Reading):
        if channel == "left":
            chan = self._left
        else:
            chan = self._right

        if chan is None:
            filename = f"{self._file_prefix}{int(time.time())}_{channel}.wav"
            Console.log_info(f"Opening '{filename}'")
            chan = stack.enter_context(wave.open(filename, "wb"))  # noqa: SIM115
            chan.setnchannels(1)
            chan.setsampwidth(2)
            assert self._freq
            chan.setframerate(float(self._freq))

            if channel == "left":
                self._left = chan
            else:
                self._right = chan

        samples = b"".join([x.val.to_bytes(2, "little", signed=True) for x in tdf.data])
        chan.writeframes(samples)

    def handle_connection(self):
        with ExitStack() as stack:
            Console.log_info("Waiting for frequency information...")
            while evt := self._client.receive():
                if evt is None:
                    continue
                if isinstance(evt, ClientNotificationConnectionDropped):
                    Console.log_error(f"Connection to {self._id:016x} lost")
                    break
                if not isinstance(evt, ClientNotificationEpacketReceived):
                    continue
                source = evt.epacket.route[0]
                if source.infuse_id != self._id:
                    continue
                if source.interface != interface.ID.BT_CENTRAL:
                    continue
                if evt.epacket.ptype != InfuseType.TDF:
                    continue
                for tdf in self._decoder.decode(evt.epacket.payload):
                    if self._freq is None:
                        if tdf.id == tdf_defs.readings.idx_array_freq.ID:
                            self._freq = tdf.data[0].frequency
                            Console.log_info(f"Audio frequency is {self._freq} Hz")
                        else:
                            # Don't write until metadata is known
                            continue
                    if tdf.id == tdf_defs.readings.pcm_16bit_chan_left.ID:
                        self.handle_channel("left", stack, tdf)
                    elif tdf.id == tdf_defs.readings.pcm_16bit_chan_right.ID:
                        self.handle_channel("right", stack, tdf)

    def run(self):
        try:
            types = GatewayRequestConnectionRequest.DataType.DATA
            Console.log_info(f"Connecting to 0x{self._id:016x}")
            with self._client.connection(self._id, types, self._conn_timeout) as _:
                self.handle_connection()

        except KeyboardInterrupt:
            Console.log_error(f"Disconnecting from {self._id:016x}")
        except ConnectionRefusedError:
            Console.log_error(f"Unable to connect to {self._id:016x}")

        if self._left:
            assert self._freq
            Console.log_text(f"Left Channel Recorded: {self._left.getnframes() / self._freq} Seconds")
        if self._right:
            assert self._freq
            Console.log_text(f"Right Channel Recorded: {self._right.getnframes() / self._freq} Seconds")
