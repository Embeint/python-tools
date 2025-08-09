#!/usr/bin/env python3

import ctypes
import ipaddress
import socket

import tabulate

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno
from infuse_iot.zephyr.net import AddressFamily, SockType


class zperf_upload(InfuseRpcCommand, defs.zperf_upload):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--address", "-a", type=str, required=True, help="Peer IP address")
        parser.add_argument("--port", "-p", type=int, default=5001, help="Peer port")
        socket_group = parser.add_mutually_exclusive_group(required=True)
        socket_group.add_argument(
            "--tcp",
            dest="sock_type",
            action="store_const",
            const=SockType.SOCK_STREAM,
            help="TCP protocol",
        )
        socket_group.add_argument(
            "--udp",
            dest="sock_type",
            action="store_const",
            const=SockType.SOCK_DGRAM,
            help="UDP protocol",
        )
        source_group = parser.add_mutually_exclusive_group()
        source_group.add_argument(
            "--constant",
            dest="data_source",
            action="store_const",
            const=defs.rpc_enum_zperf_data_source.CONSTANT,
            default=defs.rpc_enum_zperf_data_source.CONSTANT,
            help="Constant data payload ('z')",
        )
        source_group.add_argument(
            "--random",
            dest="data_source",
            action="store_const",
            const=defs.rpc_enum_zperf_data_source.RANDOM,
            help="Random data payload",
        )
        source_group.add_argument(
            "--onboard",
            dest="data_source",
            action="store_const",
            const=defs.rpc_enum_zperf_data_source.FLASH_ONBOARD,
            help="Read from onboard flash logger",
        )
        source_group.add_argument(
            "--removable",
            dest="data_source",
            action="store_const",
            const=defs.rpc_enum_zperf_data_source.FLASH_REMOVABLE,
            help="Read from removable flash logger",
        )
        parser.add_argument("--encrypt", action="store_true", help="Encrypt payloads before transmission")
        parser.add_argument("--duration", type=int, default=5000, help="Duration to run test over in milliseconds")
        parser.add_argument("--rate-kbps", type=int, default=0, help="Desired upload rate in kbps")
        parser.add_argument("--payload-size", type=int, default=512, help="Payload size")

    def __init__(self, args):
        self.peer_addr = ipaddress.ip_address(args.address)
        self.peer_port = args.port
        self.sock_type = args.sock_type
        self.data_source = args.data_source
        if args.encrypt:
            self.data_source |= defs.rpc_enum_zperf_data_source.ENCRYPT
        self.duration = args.duration
        self.rate = args.rate_kbps
        self.packet_size = args.payload_size
        if self.sock_type == SockType.SOCK_DGRAM:
            # Add the UDP client header size to the requested payload size
            self.packet_size += 40

    def request_struct(self):
        peer_family = (
            AddressFamily.AF_INET if isinstance(self.peer_addr, ipaddress.IPv4Address) else AddressFamily.AF_INET6
        )
        addr_bytes = (16 * ctypes.c_uint8)(*self.peer_addr.packed)
        peer = defs.rpc_struct_sockaddr(
            sin_family=peer_family,
            sin_port=socket.htons(self.peer_port),
            sin_addr=addr_bytes,
            scope_id=0,
        )

        return self.request(
            peer_address=peer,
            sock_type=self.sock_type,
            data_source=self.data_source,
            duration_ms=self.duration,
            rate_kbps=self.rate,
            packet_size=self.packet_size,
        )

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to run zperf ({errno.strerror(-return_code)})")
            return

        throughput_bps = 8 * response.total_len / (response.client_time_in_us / 1000)
        print(f"Average Throughput: {throughput_bps / 1000:.3f} kbps")
        if self.sock_type == SockType.SOCK_DGRAM:
            recv = 100 * response.nb_packets_rcvd / response.nb_packets_sent
            loss = 100 * response.nb_packets_lost / response.nb_packets_sent
            print(f"       Packet Recv: {recv:6.2f}%")
            print(f"       Packet Loss: {loss:6.2f}%")
        results = []
        for field_name, _ in response._fields_:
            results.append([field_name, getattr(response, field_name)])
        print(tabulate.tabulate(results))
