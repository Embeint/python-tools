import subprocess
from pathlib import Path
from typing import TypedDict
from unittest.mock import Mock

import pytest

from infuse_iot.util.soc import rpi

DEVICE_ID = 0xAB00112233445566
ID_BYTES = DEVICE_ID.to_bytes(8, "little")
GOLDEN = bytes.fromhex("494650490100000066554433221100ab99aabbccddeeff54")


class TransportState(TypedDict):
    info: str
    sector: bytes
    commands: list[list[str]]
    corrupt_write: bool


def test_record_wire_format():
    assert rpi.encode_record(ID_BYTES) == GOLDEN
    assert rpi.decode_record(GOLDEN.ljust(rpi.SECTOR_SIZE, b"\xff")) == ID_BYTES
    assert rpi.decode_record(b"\xff" * rpi.SECTOR_SIZE) == b"\xff" * 8


@pytest.mark.parametrize("device_id", [0, 0xFFFF000000000001, rpi.UINT64_MAX])
def test_invalid_ids(device_id):
    with pytest.raises(ValueError):
        rpi.encode_record(device_id.to_bytes(8, "little"))


def test_corrupt_and_torn_records():
    good = GOLDEN.ljust(rpi.SECTOR_SIZE, b"\xff")
    for offset in range(len(GOLDEN)):
        corrupt = bytearray(good)
        corrupt[offset] ^= 1
        with pytest.raises(ValueError):
            rpi.decode_record(bytes(corrupt))
    for length in range(1, len(GOLDEN)):
        with pytest.raises(ValueError):
            rpi.decode_record(GOLDEN[:length].ljust(rpi.SECTOR_SIZE, b"\xff"))
    with pytest.raises(ValueError):
        rpi.decode_record(good[:-1] + b"\x00")
    with pytest.raises(ValueError):
        rpi.decode_record(good[:-1])


@pytest.fixture
def transport(monkeypatch):
    state: TransportState = {
        "info": "Device Information\n type: RP2040\n flash size: 2048K\n flash id: 0xE66430A64B581E32\n",
        "sector": b"\xff" * rpi.SECTOR_SIZE,
        "commands": [],
        "corrupt_write": False,
    }

    def run(command, **kwargs):
        state["commands"].append(command)
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 30
        operation = command[1]
        if operation == "save":
            Path(command[5]).write_bytes(state["sector"])
        if operation == "load":
            data = Path(command[3]).read_bytes()
            state["sector"] = data[:-1] + b"\x00" if state["corrupt_write"] else data
        return subprocess.CompletedProcess(command, 0, stdout=state["info"] if operation == "info" else "")

    monkeypatch.setattr(rpi.shutil, "which", lambda _: "/tools/picotool")
    monkeypatch.setattr(rpi.subprocess, "run", run)
    return state


@pytest.mark.parametrize(
    "chip,size,address,hardware_id",
    [
        ("RP2040", 2048, 0x101F7000, "E66430A64B581E32"),
        ("RP2350", 4096, 0x103F7000, "0123456789ABCDEF"),
    ],
)
def test_transport_layout_and_readback(transport, chip, size, address, hardware_id):
    field = "flash id" if chip == "RP2040" else "chipid"
    transport["info"] = f"Device Information\n type: {chip}\n flash size: {size}K\n {field}: 0x{hardware_id}\n"
    interface = rpi.Interface()
    assert interface.soc_name == chip.lower()
    assert interface.unique_device_id_len == 8
    assert interface.unique_device_id() == int(hardware_id, 16)
    assert interface.read_provisioned_data(8) == b"\xff" * 8
    interface.write_provisioning_data(ID_BYTES)
    assert transport["sector"] == GOLDEN.ljust(rpi.SECTOR_SIZE, b"\xff")
    interface.write_provisioning_data(ID_BYTES)  # Idempotent, no second write.
    assert sum(c[1] == "load" for c in transport["commands"]) == 1
    with pytest.raises(ValueError, match="different"):
        interface.write_provisioning_data((DEVICE_ID + 1).to_bytes(8, "little"))
    for command in transport["commands"][1:]:
        assert command[-2:] == ["--ser", hardware_id]
        if command[1] == "save":
            assert command[3:5] == [hex(address), hex(address + rpi.SECTOR_SIZE)]
        if command[1] == "load":
            assert command[2] == "-v"
            assert command[6:8] == ["-o", hex(address)]
    interface.close(reset=False)
    assert all(c[1] != "reboot" for c in transport["commands"])
    interface.close()
    assert transport["commands"][-1][1] == "reboot"


def test_failed_readback_stays_in_bootsel(transport):
    interface = rpi.Interface()
    transport["corrupt_write"] = True
    with pytest.raises(RuntimeError, match="readback"):
        interface.write_provisioning_data(ID_BYTES)
    interface.close()
    assert all(c[1] != "reboot" for c in transport["commands"])


def test_occupied_sector_never_written(transport):
    transport["sector"] = b"\x00" * rpi.SECTOR_SIZE
    interface = rpi.Interface()
    with pytest.raises(ValueError, match="occupied"):
        interface.write_provisioning_data(ID_BYTES)
    assert all(c[1] != "load" for c in transport["commands"])


def test_multiple_devices_rejected(transport):
    transport["info"] *= 2
    with pytest.raises(RuntimeError, match="exactly one"):
        rpi.Interface()


def test_unidentified_flash_requires_firmware_first(transport):
    transport["info"] = "Device Information\n type: RP2040\n"
    with pytest.raises(RuntimeError, match="Flash Infuse firmware"):
        rpi.Interface()
    assert all(c[1] != "load" for c in transport["commands"])


def test_unsupported_flash_size_rejected(transport):
    transport["info"] = transport["info"].replace("2048K", "8192K")
    with pytest.raises(RuntimeError, match="layouts"):
        rpi.Interface()


def test_missing_picotool(monkeypatch):
    monkeypatch.setattr(rpi.shutil, "which", Mock(return_value=None))
    with pytest.raises(RuntimeError, match="Install"):
        rpi.Interface()
