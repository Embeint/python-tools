"""ESP32 factory identity, permanent ID writes, and cloud provisioning contracts."""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from infuse_iot.api_client.models import Board, Device, DeviceMetadata
from infuse_iot.tools.provision import SubCommand
from infuse_iot.util.soc import esp, soc

MAC = bytes.fromhex("7c2c677c8280")
DEVICE_ID = 0xCD3F20A4E131
DATA = DEVICE_ID.to_bytes(8, "little")


def esptool_output(soc_name, mac):
    output = f"Detecting chip type... {soc_name}\nConnected to {soc_name} on /dev/fake:\n"
    if soc_name == "ESP32-C6":
        return output + f"MAC: {mac[:3].hex(':')}:ff:fe:{mac[3:].hex(':')}\nBASE MAC: {mac.hex(':')}\n"
    return output + f"MAC: {mac.hex(':')}\n"


class FakeESP(esp.Interface):
    def __init__(self, block=bytes(32), writable=True, readable=True, soc_name="ESP32-C6"):
        self.block = block
        self.writable = writable
        self.readable = readable
        self.chip_name = soc_name
        self.mac = MAC
        self.writes = 0
        self.fail_verify = False
        self.closed = False
        self.commands = []
        super().__init__("fake")

    def _esp(self, module, *command, interactive=False):
        self.commands.append((module, command[0]))
        if module == "esptool":
            assert command == ("read-mac",)
            return esptool_output(self.chip_name, self.mac)
        assert module == "espefuse"
        if command[0] == "summary":
            field = {"value": self.block.hex(), "readable": self.readable, "writeable": self.writable}
            Path(command[-1]).write_text(json.dumps({"BLOCK_USR_DATA": field}))
        else:
            assert command[:2] == ("burn-block-data", "BLOCK_USR_DATA")
            assert interactive
            self.writes += 1
            if not self.fail_verify:
                self.block = Path(command[2]).read_bytes()
        return ""

    def close(self):
        self.closed = True
        super().close()


@pytest.mark.parametrize(("soc_name", "chip"), [("ESP32-C6", "esp32c6"), ("ESP32-S3", "esp32s3")])
def test_factory_mac_and_blank_storage(soc_name, chip):
    interface = FakeESP(soc_name=soc_name)
    try:
        assert interface.soc_name == soc_name
        assert interface._chip == chip
        assert interface.unique_device_id() == int.from_bytes(MAC, "big")
        assert interface.unique_device_id_len == 6
        assert interface.provisioned_device_id is None
        assert interface.provisioning_data_is_blank(interface.read_provisioned_data(8))
        assert not soc.ProvisioningInterface.provisioning_data_is_blank(interface, bytes(8))
    finally:
        interface.close()


def test_program_64_bit_id_once_and_verify():
    interface = FakeESP()
    try:
        interface.write_provisioning_data(DATA)
        assert interface.block == DATA + bytes(24)
        assert interface.read_provisioned_data(8) == DATA
        assert interface.provisioned_device_id == DEVICE_ID
        assert interface.unique_device_id() == int.from_bytes(MAC, "big")
        interface.write_provisioning_data(DATA)
        assert interface.writes == 1
        with pytest.raises(soc.ProvisioningError, match="blank"):
            interface.write_provisioning_data((DEVICE_ID + 1).to_bytes(8, "little"))
    finally:
        interface.close()


@pytest.mark.parametrize("device_id", [0, 0xFFFF000000000000, 0xFFFFFFFFFFFFFFFF])
def test_reserved_id_write_rejected(device_id):
    interface = FakeESP()
    try:
        with pytest.raises(soc.ProvisioningError, match="Invalid"):
            interface.write_provisioning_data(device_id.to_bytes(8, "little"))
        assert interface.writes == 0
    finally:
        interface.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"block": bytes(25) + b"\x02" + bytes(6)},
        {"block": b"\xff" * 32},
        {"block": bytes(31)},
        {"writable": False},
        {"readable": False},
    ],
)
def test_unavailable_or_occupied_efuses_rejected(kwargs):
    with pytest.raises(soc.ProvisioningError):
        FakeESP(**kwargs)


@pytest.mark.parametrize("soc_name", ["ESP32", "ESP32-C3", "ESP32-S2"])
def test_unsupported_chip_rejected(soc_name):
    with pytest.raises(soc.ProvisioningError, match="Unsupported chip"):
        FakeESP(soc_name=soc_name)


def test_hardware_swap_before_burn_rejected():
    interface = FakeESP()
    try:
        interface.mac = bytes(6)
        with pytest.raises(soc.ProvisioningError, match="hardware changed"):
            interface.write_provisioning_data(DATA)
        assert interface.writes == 0
    finally:
        interface.close()


def test_readback_failure():
    interface = FakeESP()
    try:
        interface.fail_verify = True
        with pytest.raises(soc.ProvisioningError, match="verification"):
            interface.write_provisioning_data(DATA)
    finally:
        interface.close()


class VirtualESP(esp.Interface):
    def __init__(self, tmp_path, soc_name):
        self.state = tmp_path / "virtual-efuses.bin"
        self.chip_name = soc_name
        super().__init__("virtual")

    def _esp(self, module, *command, interactive=False):
        if module == "esptool":
            return esptool_output(self.chip_name, MAC)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "espefuse",
                "--chip",
                self._chip,
                "--virt",
                "--path-efuse-file",
                str(self.state),
                "--do-not-confirm",
                *command,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout


@pytest.mark.parametrize("soc_name", ["ESP32-C6", "ESP32-S3"])
def test_real_virtual_efuse_programming(tmp_path, soc_name):
    interface = VirtualESP(tmp_path, soc_name)
    try:
        interface.write_provisioning_data(DATA)
        assert interface._user_block()[0] == DATA + bytes(24)
        interface.write_provisioning_data(DATA)
        with pytest.raises(soc.ProvisioningError, match="blank"):
            interface.write_provisioning_data((DEVICE_ID + 1).to_bytes(8, "little"))
    finally:
        interface.close()


def test_missing_esptool_reported(monkeypatch):
    monkeypatch.setattr(esp, "find_spec", lambda name: None)
    with pytest.raises(soc.ProvisioningError, match=r"install infuse_iot\[provisioning\]"):
        esp.Interface("fake")


def test_tool_errors_reported(monkeypatch):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2, "esptool v5\n", "A fatal error occurred: Could not open fake\n")

    monkeypatch.setattr(esp.subprocess, "run", run)
    with pytest.raises(soc.ProvisioningError, match="esptool read-mac failed:\nA fatal error occurred: Could not open"):
        esp.Interface("fake")


def mock_cloud(monkeypatch, missing=False):
    now = datetime.datetime.now(datetime.UTC)
    device = Device(uuid4(), now, now, MAC.hex(), uuid4(), uuid4(), f"{DEVICE_ID:016x}", DeviceMetadata.from_dict({}))
    response = SimpleNamespace(parsed=None if missing else device, status_code=404 if missing else 200)
    client = MagicMock()
    client.with_headers.return_value = client
    client.__enter__.return_value = client
    monkeypatch.setattr("infuse_iot.tools.provision.Client", lambda **kwargs: client)
    monkeypatch.setattr("infuse_iot.tools.provision.get_api_auth_header", lambda: {})
    monkeypatch.setattr(
        "infuse_iot.tools.provision.get_device_by_soc_and_mcu_id.sync_detailed", lambda **kwargs: response
    )
    return device


def command_for(interface, monkeypatch, *args):
    parser = argparse.ArgumentParser()
    SubCommand.add_parser(parser)
    command = SubCommand(parser.parse_args(["--esp32", "--port", "fake", *args]))
    monkeypatch.setattr(esp, "Interface", lambda port: interface)
    return command


def test_existing_cloud_dry_run_never_writes(monkeypatch, capsys):
    interface = FakeESP()
    mock_cloud(monkeypatch)
    command_for(interface, monkeypatch, "--dry-run").run()
    assert interface.writes == 0
    assert interface.closed
    assert "Would provision" in capsys.readouterr().out


def test_new_cloud_dry_run_never_creates_or_writes(monkeypatch):
    interface = FakeESP()
    device = mock_cloud(monkeypatch, missing=True)
    board = MagicMock(spec=Board, soc="ESP32-C6", name="test")
    monkeypatch.setattr("infuse_iot.tools.provision.get_board_by_id.sync", lambda **kwargs: board)
    create = MagicMock(side_effect=AssertionError("dry run created cloud device"))
    monkeypatch.setattr("infuse_iot.tools.provision.create_device.sync_detailed", create)
    command_for(
        interface,
        monkeypatch,
        "--dry-run",
        "--organisation",
        str(device.organisation_id),
        "--board",
        str(device.board_id),
    ).run()
    create.assert_not_called()
    assert interface.writes == 0
    assert interface.closed


def test_provisioned_missing_cloud_record_not_recreated(monkeypatch):
    interface = FakeESP(block=DATA + bytes(24))
    mock_cloud(monkeypatch, missing=True)
    command = command_for(interface, monkeypatch)
    command.create_device = MagicMock()
    with pytest.raises(SystemExit, match="matching cloud"):
        command.run()
    command.create_device.assert_not_called()
    assert interface.closed


def test_conflicting_cloud_id_rejected(monkeypatch):
    interface = FakeESP(block=(DEVICE_ID + 1).to_bytes(8, "little") + bytes(24))
    mock_cloud(monkeypatch)
    with pytest.raises(SystemExit, match="differs"):
        command_for(interface, monkeypatch).run()
    assert interface.writes == 0
    assert interface.closed


def test_cloud_id_written_and_matching_id_not_rewritten(monkeypatch):
    interface = FakeESP()
    mock_cloud(monkeypatch)
    command_for(interface, monkeypatch).run()
    assert interface.block == DATA + bytes(24)
    # Connect, then check the hardware and block again right before the burn and verify it
    assert interface.commands == [
        ("esptool", "read-mac"),
        ("espefuse", "summary"),
        ("esptool", "read-mac"),
        ("espefuse", "summary"),
        ("espefuse", "burn-block-data"),
        ("espefuse", "summary"),
    ]
    interface = FakeESP(block=DATA + bytes(24))
    command_for(interface, monkeypatch).run()
    assert interface.writes == 0


def test_provisioning_errors_exit_without_traceback(monkeypatch):
    parser = argparse.ArgumentParser()
    SubCommand.add_parser(parser)
    with pytest.raises(SystemExit, match="requires --port"):
        SubCommand(parser.parse_args(["--esp32"])).run()
