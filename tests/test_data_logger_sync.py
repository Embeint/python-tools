from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.console import Console

from infuse_iot.definitions.rpc import rpc_enum_data_logger
from infuse_iot.tools.data_logger_sync import DeviceState, SubCommand


def test_resume_rejects_partial_block_without_changing_file(tmp_path):
    path = tmp_path / "partial.bin"
    original = b"A" * 513
    path.write_bytes(original)
    with pytest.raises(ValueError, match="Cannot resume"):
        DeviceState(path)
    assert path.read_bytes() == original


def test_resume_appends_complete_blocks(tmp_path):
    path = tmp_path / "complete.bin"
    path.write_bytes(b"A" * 512)
    state = DeviceState(path)
    assert state.on_disk == 1
    state.append_data(b"B" * 1024)
    assert state.on_disk == 3
    assert state.downloaded == 2
    assert path.read_bytes() == b"A" * 512 + b"B" * 1024
    with pytest.raises(ValueError, match="complete blocks"):
        state.append_data(b"partial")
    assert path.stat().st_size == 1536


def test_progress_with_empty_logger(tmp_path, monkeypatch):
    monkeypatch.setattr("infuse_iot.tools.data_logger_sync.LocalClient", Mock())
    args = SimpleNamespace(
        server_sock=None, rssi=None, app=None, out=tmp_path, blocks=500, logger=rpc_enum_data_logger.FLASH_ONBOARD
    )
    command = SubCommand(args)
    state = DeviceState(tmp_path / "empty.bin")
    state.on_device = 0
    command._device_state[123] = state
    output = StringIO()
    Console(file=output, width=120).print(command.progress_table())
    assert "100%" in output.getvalue()
