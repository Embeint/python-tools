import os

from infuse_iot.util.time import humanised_seconds

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_humanised_seconds():
    for units in range(1, 6):
        # Test 0 case
        assert humanised_seconds(0, units) == "0 seconds"
        # Test a range of magnitudes
        seconds = 1
        for _time_step in range(10):
            result = humanised_seconds(seconds, units)
            assert isinstance(result, str)
            print(f"{seconds:10}: {result}")
            seconds *= 10
