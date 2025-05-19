#!/usr/bin/env python3

import ctypes
import random
from collections.abc import Callable

from infuse_iot import rpc
from infuse_iot.common import InfuseType
from infuse_iot.epacket.packet import Auth, PacketOutput, PacketReceived
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequestEpacketSend,
    LocalClient,
)


class RpcClient:
    def __init__(
        self,
        client: LocalClient,
        max_payload: int,
        infuse_id: int,
        rx_cb: Callable[[ClientNotification], None] | None = None,
    ):
        self._request_id = random.randint(0, 2**31 - 1)
        self._client = client
        self._id = infuse_id
        self._max_payload = max_payload
        self._rx_cb = rx_cb

    def _finalise_command(
        self, rpc_rsp: PacketReceived, rsp_decoder: Callable[[bytes], ctypes.LittleEndianStructure]
    ) -> tuple[rpc.ResponseHeader, ctypes.LittleEndianStructure | None]:
        # Convert response bytes back to struct form
        rsp_header = rpc.ResponseHeader.from_buffer_copy(rpc_rsp.payload)
        rsp_payload = rpc_rsp.payload[ctypes.sizeof(rpc.ResponseHeader) :]
        try:
            rsp_data = rsp_decoder(rsp_payload)
        except ValueError:
            rsp_data = None
        return (rsp_header, rsp_data)

    def _client_recv(self) -> ClientNotification | None:
        rsp = self._client.receive()
        if rsp is not None and self._rx_cb is not None:
            self._rx_cb(rsp)
        return rsp

    def _wait_data_ack(self) -> PacketReceived:
        while True:
            rsp = self._client_recv()
            if rsp is None:
                continue
            if not isinstance(rsp, ClientNotificationEpacketReceived):
                continue
            if rsp.epacket.ptype == InfuseType.RPC_RSP:
                rsp_header = rpc.ResponseHeader.from_buffer_copy(rsp.epacket.payload)
                if rsp_header.request_id == self._request_id:
                    return rsp.epacket
            elif rsp.epacket.ptype != InfuseType.RPC_DATA_ACK:
                continue
            data_ack = rpc.DataAck.from_buffer_copy(rsp.epacket.payload)
            # Response to the request we sent
            if data_ack.request_id != self._request_id:
                continue
            return rsp.epacket

    def _wait_rpc_rsp(self) -> PacketReceived:
        # Wait for responses
        while True:
            rsp = self._client_recv()
            if rsp is None:
                continue
            if not isinstance(rsp, ClientNotificationEpacketReceived):
                continue
            # RPC response packet
            if rsp.epacket.ptype != InfuseType.RPC_RSP:
                continue
            rsp_header = rpc.ResponseHeader.from_buffer_copy(rsp.epacket.payload)
            # Response to the request we sent
            if rsp_header.request_id != self._request_id:
                continue
            return rsp.epacket

    def run_data_send_cmd(
        self,
        cmd_id: int,
        auth: Auth,
        params: bytes,
        data: bytes,
        progress_cb: Callable[[int], None] | None,
        rsp_decoder: Callable[[bytes], ctypes.LittleEndianStructure],
    ) -> tuple[rpc.ResponseHeader, ctypes.LittleEndianStructure | None]:
        self._request_id += 1
        ack_period = 1
        header = rpc.RequestHeader(self._request_id, cmd_id)  # type: ignore
        data_hdr = rpc.RequestDataHeader(len(data), ack_period)

        request_packet = bytes(header) + bytes(data_hdr) + params
        pkt = PacketOutput(
            self._id,
            auth,
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequestEpacketSend(pkt)
        self._client.send(req)

        # Wait for initial ACK
        recv = self._wait_data_ack()
        if recv.ptype == InfuseType.RPC_RSP:
            return self._finalise_command(recv, rsp_decoder)

        # Send data payloads with maximum interface size
        ack_cnt = -ack_period
        offset = 0
        size = self._max_payload - ctypes.sizeof(rpc.DataHeader)
        # Round payload down to multiple of 4 bytes
        size -= size % 4
        while len(data) > 0:
            size = min(size, len(data))
            payload = data[:size]

            hdr = rpc.DataHeader(self._request_id, offset)
            pkt_bytes = bytes(hdr) + payload
            pkt = PacketOutput(
                self._id,
                auth,
                InfuseType.RPC_DATA,
                pkt_bytes,
            )
            self._client.send(GatewayRequestEpacketSend(pkt))
            ack_cnt += 1

            # Wait for ACKs at the period
            if ack_cnt == ack_period:
                recv = self._wait_data_ack()
                if recv.ptype == InfuseType.RPC_RSP:
                    return self._finalise_command(recv, rsp_decoder)
                ack_cnt = 0

            offset += size
            data = data[size:]
            if progress_cb:
                progress_cb(offset)

        recv = self._wait_rpc_rsp()
        return self._finalise_command(recv, rsp_decoder)

    def run_data_recv_cmd(
        self,
        cmd_id: int,
        auth: Auth,
        params: bytes,
        size: int,
        recv_cb: Callable[[int, bytes], None],
        rsp_decoder: Callable[[bytes], ctypes.LittleEndianStructure],
    ) -> tuple[rpc.ResponseHeader, ctypes.LittleEndianStructure | None]:
        self._request_id += 1
        header = rpc.RequestHeader(self._request_id, cmd_id)
        data_hdr = rpc.RequestDataHeader(size, 0)

        request_packet = bytes(header) + bytes(data_hdr) + params
        pkt = PacketOutput(
            self._id,
            auth,
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequestEpacketSend(pkt)
        self._client.send(req)

        while True:
            rsp = self._client_recv()
            if rsp is None:
                continue
            if isinstance(rsp, ClientNotificationConnectionDropped):
                raise ConnectionAbortedError
            if not isinstance(rsp, ClientNotificationEpacketReceived):
                continue
            if rsp.epacket.ptype == InfuseType.RPC_RSP:
                rsp_header = rpc.ResponseHeader.from_buffer_copy(rsp.epacket.payload)
                # Response to the request we sent
                if rsp_header.request_id != self._request_id:
                    continue
                # Convert response bytes back to struct form
                rsp_payload = rsp.epacket.payload[ctypes.sizeof(rpc.ResponseHeader) :]
                rsp_data = rsp_decoder(rsp_payload)
                return (rsp_header, rsp_data)

            if rsp.epacket.ptype != InfuseType.RPC_DATA:
                continue
            data = rpc.DataHeader.from_buffer_copy(rsp.epacket.payload)
            # Response to the request we sent
            if data.request_id != self._request_id:
                continue

            recv_cb(data.offset, rsp.epacket.payload[ctypes.sizeof(rpc.DataHeader) :])

    def run_standard_cmd(
        self, cmd_id: int, auth: Auth, params: bytes, rsp_decoder: Callable[[bytes], ctypes.LittleEndianStructure]
    ) -> tuple[rpc.ResponseHeader, ctypes.LittleEndianStructure | None]:
        self._request_id += 1
        header = rpc.RequestHeader(self._request_id, cmd_id)  # type: ignore

        request_packet = bytes(header) + params
        pkt = PacketOutput(
            self._id,
            auth,
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequestEpacketSend(pkt)
        self._client.send(req)
        recv = self._wait_rpc_rsp()
        return self._finalise_command(recv, rsp_decoder)
