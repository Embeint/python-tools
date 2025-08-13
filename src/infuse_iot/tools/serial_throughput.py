#!/usr/bin/env python3

"""Test serial throughput to local gateway"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import random
import time

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.epacket.packet import Auth, PacketOutput
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    GatewayRequestEpacketSend,
    LocalClient,
    default_multicast_address,
)


class SubCommand(InfuseCommand):
    NAME = "serial_throughput"
    HELP = "Test serial throughput to local gateway"
    DESCRIPTION = "Test serial throughput to local gateway"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--iterations",
            type=int,
            default=20,
            help="Number of times to send each sized packet",
        )

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._iterations = args.iterations

    def run_send_test(self, num, size, queue_size):
        assert size >= 4
        self._client.set_rx_timeout(0.2)
        sent = 0
        pending = 0
        responses = 0

        start = time.time()
        while (sent != num) or (pending > 0):
            # Queue packets up to the maximum queue size
            while (sent != num) and (pending < queue_size):
                payload = sent.to_bytes(4, "little") + random.randbytes(size - 4)
                pkt = PacketOutput(
                    InfuseID.GATEWAY,
                    Auth.DEVICE,
                    InfuseType.ECHO_REQ,
                    payload,
                )
                req = GatewayRequestEpacketSend(pkt)
                self._client.send(req)
                sent += 1
                pending += 1
            # Wait for responses
            if rsp := self._client.receive():
                if not isinstance(rsp, ClientNotificationEpacketReceived):
                    continue
                if rsp.epacket.ptype != InfuseType.ECHO_RSP:
                    continue
                responses += 1
                pending -= 1
            else:
                # Timeout, no more data coming
                break
        end = time.time()
        duration = end - start
        total = num * size
        throughput = total / duration
        if responses != num:
            print(f"\tOnly received {responses}/{num} responses")
        msg = f"\t{num} packets with {size:3d} bytes payload complete in {duration:.2f} seconds"
        msg += f" ({int(8 * throughput):6d} bps)"
        print(msg)

    def run(self):
        # No queuing
        print(f"Averaged across {self._iterations} packets with no queuing:")
        self.run_send_test(self._iterations, 4, 1)
        self.run_send_test(self._iterations, 32, 1)
        self.run_send_test(self._iterations, 128, 1)
        self.run_send_test(self._iterations, 512, 1)
        # Small queue
        print(f"Averaged across {self._iterations} packets with 3 packet queue:")
        self.run_send_test(self._iterations, 4, 3)
        self.run_send_test(self._iterations, 32, 3)
        self.run_send_test(self._iterations, 128, 3)
        self.run_send_test(self._iterations, 512, 3)
        # Larger queue
        print(f"Averaged across {self._iterations} packets with 5 packet queue:")
        self.run_send_test(self._iterations, 4, 5)
        self.run_send_test(self._iterations, 32, 5)
        self.run_send_test(self._iterations, 128, 5)
        self.run_send_test(self._iterations, 512, 5)
