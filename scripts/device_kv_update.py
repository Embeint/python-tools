#!/usr/bin/env python3
"""Schedule cloud-side key-value updates for selected Infuse-IoT devices.

Edit the ``config`` block in this file with target device IDs, the KV key ID,
and the desired base64-encoded value. The script checks the current cloud KV
entry for each device and schedules an update only when the stored value does
not already match.
"""

import base64

from infuse_iot.api_client import Client, models
from infuse_iot.api_client.api.device import (
    create_device_kv_entry_update_by_device_id_and_key_id,
    get_device_kv_entry_by_device_id_and_key_id,
)
from infuse_iot.credentials import get_api_auth_header
from infuse_iot.util.api import format_api_error


class ScriptConfig:
    def __init__(self, devices: list[int], kv_key: int, kv_value: str):
        self.devices = devices
        self.kv_key = kv_key
        self.kv_value = kv_value


# Example sets APPLICATION_ACTIVE to 0x00 for all listed devices
config = ScriptConfig(
    [
        0x12345678ABCDEF01,
    ],
    # APPLICATION_ACTIVE == 6
    6,
    # Base64 string of desired value (0x00)
    base64.b64encode(b"\x00").decode("utf-8"),
)

if __name__ == "__main__":
    api_client = Client(base_url="https://api.infuse-iot.com").with_headers(get_api_auth_header())

    with api_client as client:
        # Value doesn't change per device
        params = models.NewDeviceKVEntryUpdate(data=config.kv_value)

        # Get device state
        for device in config.devices:
            id_str = f"{device:016x}"

            # Failures are specific to this device, report and continue with the remaining devices.
            # Key may not have been set on the device yet (404), so only skip on a matching value.
            entry = get_device_kv_entry_by_device_id_and_key_id.sync_detailed(
                client=client, device_id=id_str, key_id=config.kv_key
            ).parsed

            if isinstance(entry, models.DeviceKVEntry) and entry.data == config.kv_value:
                print(f"{id_str}: Already has desired value")
                continue

            rsp = create_device_kv_entry_update_by_device_id_and_key_id.sync_detailed(
                client=client,
                device_id=id_str,
                key_id=config.kv_key,
                body=params,
            )
            if isinstance(rsp.parsed, models.DeviceKVEntry):
                print(f"{id_str}: Already has desired value (not caught above?)")
            elif isinstance(rsp.parsed, models.DeviceKVEntryUpdate):
                print(f"{id_str}: Update scheduled ({rsp.parsed.id})")
            else:
                print(f"{id_str}: KV update: {format_api_error(rsp)}")
