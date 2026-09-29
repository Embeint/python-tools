from pathlib import Path
from unittest.mock import Mock

from infuse_iot.util.soc import nrf, stm


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
