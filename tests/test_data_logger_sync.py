import binascii
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from rich.console import Console

from infuse_iot.definitions.rpc import data_logger_read, rpc_enum_data_logger
from infuse_iot.rpc import ResponseHeader
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


@pytest.mark.parametrize("result", ["valid", "timeout", "header_only", "bad_length", "bad_crc", "disconnect"])
def test_sync_preserves_resume_file_on_failed_download(tmp_path, monkeypatch, result):
    client = MagicMock()
    client.connection.return_value.__enter__.return_value = 128
    monkeypatch.setattr("infuse_iot.tools.data_logger_sync.LocalClient", lambda *_args: client)
    rpc_client = Mock()
    monkeypatch.setattr("infuse_iot.tools.data_logger_sync.RpcClient", lambda *_args: rpc_client)
    command = SubCommand(
        SimpleNamespace(
            server_sock=None, rssi=None, app=None, out=tmp_path, blocks=500, logger=rpc_enum_data_logger.FLASH_ONBOARD
        )
    )
    path = tmp_path / "resume.bin"
    original, downloaded = b"A" * 512, b"B" * 512
    path.write_bytes(original)
    state = DeviceState(path)
    state.on_device = 2

    def download(*_args):
        command.data_progress_cb(0, downloaded)
        if result == "disconnect":
            raise ConnectionAbortedError
        if result == "timeout":
            return None, None
        if result == "header_only":
            return ResponseHeader(1, data_logger_read.COMMAND_ID, -22), None
        response = data_logger_read.response(len(downloaded), binascii.crc32(downloaded))
        if result == "bad_length":
            response.sent_len += 1
        if result == "bad_crc":
            response.sent_crc ^= 1
        return ResponseHeader(1, data_logger_read.COMMAND_ID, 0), response

    rpc_client.run_data_recv_cmd.side_effect = download
    command.handle_sync(Mock(), 123, state)
    assert path.read_bytes() == original + (downloaded if result == "valid" else b"")
    assert state.on_disk == (2 if result == "valid" else 1)
    assert command.task is None
    assert command.progress.tasks == []
    client.connection.return_value.__exit__.assert_called_once()
    command.close()
    client.close.assert_called_once()
