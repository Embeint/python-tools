import argparse
import datetime
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import UUID

import pytest

from infuse_iot.api_client.models import Device, DeviceMetadata
from infuse_iot.tools import provision
from infuse_iot.util.soc import nrf, stm
from infuse_iot.util.soc.soc import ProvisioningInterface

DEVICE_ID = 0xAB00112233445566
HARDWARE_ID = 0xE66430A64B581E32
UUID_VALUE = UUID("12345678-1234-5678-1234-567812345678")


def command(*extra):
    parser = argparse.ArgumentParser()
    provision.SubCommand.add_parser(parser)
    return provision.SubCommand(parser.parse_args(["--rpi", *extra]))


@pytest.fixture
def environment(monkeypatch):
    interface = Mock(spec=ProvisioningInterface)
    interface.DefaultProvisioningStruct = ProvisioningInterface.DefaultProvisioningStruct
    interface.unique_device_id.return_value = HARDWARE_ID
    interface.unique_device_id_len = 8
    interface.soc_name = "rp2040"
    interface.read_provisioned_data.return_value = b"\xff" * 8
    factory = Mock(return_value=interface)
    monkeypatch.setattr(provision.rpi, "Interface", factory)
    client = MagicMock()
    monkeypatch.setattr(provision, "Client", Mock(return_value=client))
    monkeypatch.setattr(provision, "get_api_auth_header", lambda: {})
    now = datetime.datetime.now(datetime.timezone.utc)
    device = Device(
        UUID_VALUE, now, now, f"{HARDWARE_ID:016x}", UUID_VALUE, UUID_VALUE, f"{DEVICE_ID:016x}", DeviceMetadata()
    )
    query = Mock(return_value=SimpleNamespace(parsed=device, status_code=HTTPStatus.OK))
    monkeypatch.setattr(provision.get_device_by_soc_and_mcu_id, "sync_detailed", query)
    return SimpleNamespace(interface=interface, factory=factory, client=client, query=query)


def test_rpi_cloud_identity_written(environment):
    command("--usb-serial", "E66430A64B581E32").run()
    environment.factory.assert_called_once_with("E66430A64B581E32")
    assert environment.query.call_args.kwargs["soc"] == "rp2040"
    assert environment.query.call_args.kwargs["mcu_id"] == "e66430a64b581e32"
    environment.interface.write_provisioning_data.assert_called_once_with(DEVICE_ID.to_bytes(8, "little"))
    environment.interface.close.assert_called_once_with(reset=True)


def test_existing_cloud_dry_run_never_writes(environment):
    command("--dry-run").run()
    environment.interface.write_provisioning_data.assert_not_called()
    environment.interface.close.assert_called_once_with(reset=False)


def test_already_provisioned_is_idempotent(environment):
    environment.interface.read_provisioned_data.return_value = DEVICE_ID.to_bytes(8, "little")
    command().run()
    environment.interface.write_provisioning_data.assert_not_called()


def test_cloud_id_conflict_never_writes(environment):
    with pytest.raises(SystemExit, match="cloud"):
        command("--id", hex(DEVICE_ID + 1)).run()
    environment.interface.write_provisioning_data.assert_not_called()
    environment.interface.close.assert_called_once()


def test_bad_local_storage_stops_before_cloud(environment):
    environment.interface.read_provisioned_data.side_effect = ValueError("occupied sector")
    with pytest.raises(SystemExit, match="Provisioning failed: occupied"):
        command().run()
    environment.query.assert_not_called()
    environment.interface.write_provisioning_data.assert_not_called()
    environment.interface.close.assert_called_once()


def test_stored_id_conflict_stops_before_cloud(environment):
    environment.interface.read_provisioned_data.return_value = DEVICE_ID.to_bytes(8, "little")
    with pytest.raises(SystemExit, match="refusing"):
        command("--id", hex(DEVICE_ID + 1)).run()
    environment.query.assert_not_called()


def test_new_device_dry_run_never_writes(environment, monkeypatch):
    environment.query.return_value = SimpleNamespace(parsed=None, status_code=HTTPStatus.NOT_FOUND)
    cmd = command("--dry-run")
    create_device = Mock()
    monkeypatch.setattr(cmd, "create_device", create_device)
    cmd.run()
    create_device.assert_called_once()
    environment.interface.write_provisioning_data.assert_not_called()


def test_new_cloud_record_preserves_stored_id(environment, monkeypatch):
    environment.interface.read_provisioned_data.return_value = DEVICE_ID.to_bytes(8, "little")
    environment.query.return_value = SimpleNamespace(parsed=None, status_code=HTTPStatus.NOT_FOUND)
    cmd = command("--dry-run")
    monkeypatch.setattr(cmd, "create_device", Mock())
    cmd.run()
    assert cmd._id == DEVICE_ID


def test_usb_selection_only_for_rpi():
    parser = argparse.ArgumentParser()
    provision.SubCommand.add_parser(parser)
    with pytest.raises(SystemExit, match="only supported"):
        provision.SubCommand(parser.parse_args(["--nrf", "--usb-serial", "123"]))
    with pytest.raises(SystemExit, match="--usb-serial"):
        command("--snr", "123")


@pytest.mark.parametrize("device_id", ["0", "ffff112233445566", "-1", "10000000000000000"])
def test_invalid_rpi_id_stops_before_hardware(environment, device_id):
    with pytest.raises(SystemExit, match="Infuse ID must"):
        command(f"--id={device_id}").run()
    environment.factory.assert_not_called()
    environment.query.assert_not_called()


@pytest.mark.parametrize("vendor", ["nrf", "stm", "rpi"])
@pytest.mark.parametrize("cloud_exists", [False, True])
def test_dry_run_closes_without_reset(environment, monkeypatch, vendor, cloud_exists):
    monkeypatch.setattr(getattr(provision, vendor), "Interface", environment.factory)
    if not cloud_exists:
        environment.query.return_value = SimpleNamespace(parsed=None, status_code=HTTPStatus.NOT_FOUND)
    parser = argparse.ArgumentParser()
    provision.SubCommand.add_parser(parser)
    cmd = provision.SubCommand(parser.parse_args([f"--{vendor}", "--dry-run"]))
    monkeypatch.setattr(cmd, "create_device", Mock())
    cmd.run()
    environment.interface.write_provisioning_data.assert_not_called()
    environment.interface.close.assert_called_once_with(reset=False)


def test_nrf_close_without_reset(monkeypatch):
    interface = nrf.Interface.__new__(nrf.Interface)
    execute = Mock()
    monkeypatch.setattr(interface, "_exec", execute)
    interface.close(reset=False)
    execute.assert_not_called()
    interface.close()
    execute.assert_called_once_with(["reset"])


def test_stm_close_without_reset(monkeypatch):
    interface = stm.Interface.__new__(stm.Interface)
    interface._cli = Path("STM32_Programmer_CLI")
    run = Mock()
    monkeypatch.setattr(stm.subprocess, "run", run)
    interface.close(reset=False)
    run.assert_not_called()
    interface.close()
    run.assert_called_once_with(
        ["STM32_Programmer_CLI", "--connect", "port=SWD", "-rst"], capture_output=True, check=True
    )
