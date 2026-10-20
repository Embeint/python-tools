from unittest.mock import Mock

from infuse_iot.tools.gateway import SubCommand


def make_command(log=None):
    command = object.__new__(SubCommand)
    command.port = Mock()
    command.log = log
    command.server = Mock()
    command._threads = []
    return command


def test_close_waits_for_threads_before_closing_server_and_log():
    log = Mock()
    command = make_command(log)
    thread = Mock()
    thread.is_alive.return_value = False
    command._threads = [thread]
    command.close()
    command.port.close.assert_called_once()
    thread.join.assert_called_once_with(command.THREAD_EXIT_TIMEOUT_S)
    log.close.assert_called_once()
    command.server.close.assert_called_once()


def test_close_leaves_resources_open_for_running_threads():
    log = Mock()
    command = make_command(log)
    thread = Mock()
    thread.name = "rx"
    thread.is_alive.return_value = True
    command._threads = [thread]
    command.close()
    command.port.close.assert_called_once()
    log.close.assert_not_called()
    command.server.close.assert_not_called()
