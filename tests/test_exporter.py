from pathlib import Path

from infuse_iot.exporter import Exporter


def test_exporters_own_their_handles(tmp_path):
    first = Exporter(tmp_path)
    second = Exporter(tmp_path)
    filename = Path("readings.csv")
    first.write_lines(filename, ["first"], header=lambda: "header")
    second.write_lines(filename, ["second"], header=lambda: "header")
    first.write_lines(filename, ["first again"])
    first_file = first._files[tmp_path / filename]
    second_file = second._files[tmp_path / filename]
    first.close()
    assert first_file.closed
    assert not second_file.closed
    second.write_lines(filename, ["third"])
    second.close()
    assert second_file.closed
    assert (tmp_path / filename).read_text(encoding="utf-8").splitlines() == [
        "header",
        "first",
        "second",
        "first again",
        "third",
    ]
