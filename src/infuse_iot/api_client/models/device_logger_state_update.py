from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define

T = TypeVar("T", bound="DeviceLoggerStateUpdate")


@_attrs_define
class DeviceLoggerStateUpdate:
    """
    Attributes:
        download_enabled (bool): Whether logger download is enabled
    """

    download_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        download_enabled = self.download_enabled

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "downloadEnabled": download_enabled,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        download_enabled = d.pop("downloadEnabled")

        device_logger_state_update = cls(
            download_enabled=download_enabled,
        )

        return device_logger_state_update
