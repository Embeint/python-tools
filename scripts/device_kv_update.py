#!/usr/bin/env python3

import base64

from infuse_iot.api_client import Client, models
from infuse_iot.api_client.api.device import (
    create_device_kv_entry_update_by_device_id_and_key_id,
    get_device_kv_entry_by_device_id_and_key_id,
)
from infuse_iot.credentials import get_api_key


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
    api_client = Client(base_url="https://api.infuse-iot.com").with_headers({"x-api-key": f"Bearer {get_api_key()}"})

    with api_client as client:
        # Value doesn't change per device
        params = models.NewDeviceKVEntryUpdate(data=config.kv_value)

        # Get device state
        for device in config.devices:
            id_str = f"{device:016x}"

            entry = get_device_kv_entry_by_device_id_and_key_id.sync(
                client=client, device_id=id_str, key_id=config.kv_key
            )

            if isinstance(entry, models.DeviceKVEntry) and entry.data == config.kv_value:
                print(f"{id_str}: Already has desired value")
                continue

            update = create_device_kv_entry_update_by_device_id_and_key_id.sync(
                client=client,
                device_id=id_str,
                key_id=config.kv_key,
                body=params,
            )
            if isinstance(update, models.DeviceKVEntry):
                print(f"{id_str}: Already has desired value (not caught above?)")
            elif isinstance(update, models.DeviceKVEntryUpdate):
                print(f"{id_str}: Update scheduled ({update.id})")
            elif isinstance(update, models.Error):
                print(f"{id_str}: <{update.code}> {update.message}")
            else:
                assert update is None
                print(f"{id_str}: No response?")
