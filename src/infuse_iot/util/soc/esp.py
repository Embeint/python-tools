"""ESP32 factory MAC and 64-bit Infuse ID provisioning over USB."""

import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from infuse_iot.util.soc.soc import ProvisioningInterface

# Chips with the Infuse ID layout in BLOCK_USR_DATA, by esptool name
CHIPS = {"ESP32-C6": "esp32c6", "ESP32-S3": "esp32s3"}


class Interface(ProvisioningInterface):
    def __init__(self, port: str | None):
        if not port:
            raise ValueError("ESP32 provisioning requires --port")
        self._port = port
        self._chip = "auto"
        self._temp = TemporaryDirectory(prefix="infuse-esp32-")
        try:
            self._soc_name, self._hardware_id = self._read_mac()
            self._chip = CHIPS[self._soc_name]
            block, writable = self._user_block()
            device_id = int.from_bytes(block[:8], "little")
            if device_id >= 0xFFFF000000000000:
                raise ValueError("USER_DATA contains an invalid Infuse ID")
            if not device_id and (block != bytes(32) or not writable):
                raise ValueError("USER_DATA must be entirely blank and writable")
            self.provisioned_device_id = device_id or None
        except BaseException:
            self.close()
            raise

    @property
    def soc_name(self) -> str:
        return self._soc_name

    @property
    def unique_device_id_len(self) -> int:
        return 6

    def unique_device_id(self) -> int:
        return int.from_bytes(self._hardware_id, "big")

    def _esp(self, module: str, *command: str, interactive: bool = False) -> str:
        cmd = [sys.executable, "-m", module, "--chip", self._chip, "--port", self._port, *command]
        if interactive:
            subprocess.run(cmd, check=True)
            return ""
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout

    def _read_mac(self) -> tuple[str, bytes]:
        output = self._esp("esptool", "read-mac")
        chip = re.search(r"^Connected to (\S+) on ", output, re.MULTILINE)
        if chip is None:
            raise ValueError("Failed to detect the ESP32 chip type")
        if chip[1] not in CHIPS:
            raise ValueError(f"Unsupported chip '{chip[1]}', expected one of {', '.join(CHIPS)}")
        # Chips with an extended MAC (ESP32-C6) report the six byte factory MAC as BASE MAC
        mac_pattern = r"^(?:BASE )?MAC:\s+((?:[0-9a-f]{2}:){5}[0-9a-f]{2})\s*$"
        found = re.search(mac_pattern, output, re.MULTILINE | re.IGNORECASE)
        if found is None:
            raise ValueError(f"Failed to read {chip[1]} factory MAC")
        return chip[1], bytes.fromhex(found[1].replace(":", ""))

    def _user_block(self) -> tuple[bytes, bool]:
        path = Path(self._temp.name) / "efuses.json"
        self._esp("espefuse", "summary", "BLOCK_USR_DATA", "--format", "json", "--file", str(path))
        field = json.loads(path.read_text())["BLOCK_USR_DATA"]
        if not field["readable"]:
            raise ValueError("USER_DATA is unreadable")
        block = bytes.fromhex(field["value"])
        if len(block) != 32:
            raise ValueError("Incomplete USER_DATA read")
        return block, field["writeable"]

    def provisioning_data_is_blank(self, data: bytes) -> bool:
        return data == bytes(len(data))

    def read_provisioned_data(self, num: int) -> bytes:
        if num != 8:
            raise ValueError("Expected a 64-bit Infuse ID")
        return self._user_block()[0][:8]

    def write_provisioning_data(self, data: bytes):
        if len(data) != 8 or not 0 < int.from_bytes(data, "little") < 0xFFFF000000000000:
            raise ValueError("Invalid 64-bit Infuse ID")
        if self._read_mac() != (self._soc_name, self._hardware_id):
            raise ValueError("Connected ESP32 hardware changed")
        block, writable = self._user_block()
        if block[:8] == data:
            return
        if block != bytes(32) or not writable:
            raise ValueError("USER_DATA must be entirely blank and writable")
        path = Path(self._temp.name) / "infuse-id.bin"
        path.write_bytes(data + bytes(24))
        self._esp("espefuse", "burn-block-data", "BLOCK_USR_DATA", str(path), interactive=True)
        if self.read_provisioned_data(8) != data:
            raise RuntimeError("Infuse ID read-back verification failed")
        self.provisioned_device_id = int.from_bytes(data, "little")

    def close(self):
        self._temp.cleanup()
