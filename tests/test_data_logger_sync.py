import pytest

from infuse_iot.tools.data_logger_sync import DeviceState


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
