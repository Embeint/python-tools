#!/usr/bin/env python3

import ctypes

import pytest

from infuse_iot.common import InfuseType
from infuse_iot.database import DeviceDatabase
from infuse_iot.epacket.interface import ID as Interface
from infuse_iot.epacket.interface import Address
from infuse_iot.epacket.packet import (
    Auth,
    CtypeBtGattFrame,
    CtypePacketReceived,
    HopOutput,
    PacketOutputRouted,
    PacketReceived,
)

GATEWAY = 0x1000
RELAY = 0x2000
DEVICE = 0x3000
RELAY_ADDR = Address.BluetoothLeAddr(1, 0x0000AABBCCDDEE01)
DEVICE_ADDR = Address.BluetoothLeAddr(1, 0x0000AABBCCDDEE02)


@pytest.fixture
def ddb():
    # Devices on the default network, which has a known key
    database = DeviceDatabase(None)
    database.observe_device(GATEWAY, network_id=0)
    database.observe_device(RELAY, network_id=0, bt_addr=RELAY_ADDR)
    database.observe_device(DEVICE, network_id=0, bt_addr=DEVICE_ADDR)
    return database


def received_entry(interface: Interface, addr: Address.BluetoothLeAddr, body: bytes, encrypted: bool) -> bytes:
    """Entry of a `RECEIVED_EPACKET` payload"""
    header = CtypePacketReceived.CommonHeader()
    address = bytes(addr.to_ctype())
    header._len_encr = (ctypes.sizeof(header) + len(address) + len(body)) | (0x8000 if encrypted else 0)
    header._rssi = 60
    header._if = interface.value
    return bytes(header) + address + body


def test_packets_forwarded_by_relay_are_decoded(ddb):
    # Packet from the device that the relay could not decrypt
    device_frame = CtypeBtGattFrame.encrypt(ddb, DEVICE, InfuseType.RPC_RSP, Auth.NETWORK, b"response")
    relay_payload = received_entry(Interface.BT_CENTRAL, DEVICE_ADDR, device_frame, True)
    # Forwarded to the gateway by the relay, which the gateway decrypted
    relay_header = CtypePacketReceived.DecryptedHeader(device_id=RELAY, _type=InfuseType.RECEIVED_EPACKET)
    gateway_payload = received_entry(Interface.BT_CENTRAL, RELAY_ADDR, bytes(relay_header) + relay_payload, False)
    frame = PacketOutputRouted(
        [HopOutput(GATEWAY, Interface.SERIAL, Auth.NETWORK)], InfuseType.RECEIVED_EPACKET, gateway_payload
    ).to_serial(ddb)

    (packet,) = PacketReceived.from_serial(ddb, frame)
    assert [hop.infuse_id for hop in packet.route] == [DEVICE, RELAY, GATEWAY]
    assert packet.route[0].interface_address.val == DEVICE_ADDR
    assert packet.ptype == InfuseType.RPC_RSP
    assert packet.payload == b"response"
