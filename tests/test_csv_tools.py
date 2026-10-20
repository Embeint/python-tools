from types import SimpleNamespace

import pytest

from infuse_iot.tools.csv_annotate import SubCommand as Annotate


def test_annotate_rejects_empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("time,value\n", encoding="utf-8")
    command = Annotate(SimpleNamespace(file=path, default="N/A"))
    with pytest.raises(ValueError, match="no readings"):
        command.run()
