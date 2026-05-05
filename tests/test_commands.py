#!/usr/bin/env python3

import os

from infuse_iot.commands import wrapper_from_command_id
from infuse_iot.rpc_wrappers import application_info, security_public_keys, wifi_scan

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_wrapper_from_command_id():
    def class_test(wrapper_class):
        assert wrapper_class == wrapper_from_command_id(wrapper_class.COMMAND_ID)

    class_test(application_info.application_info)
    class_test(wifi_scan.wifi_scan)
    class_test(security_public_keys.security_public_keys)

    assert wrapper_from_command_id(123456789) is None
