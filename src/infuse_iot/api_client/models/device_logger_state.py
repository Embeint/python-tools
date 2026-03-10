from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="DeviceLoggerState")


@_attrs_define
class DeviceLoggerState:
    """
    Attributes:
        download_enabled (bool): Whether logger download is enabled
        last_reported_block (int | Unset): Last reported block number
        last_reported_time (datetime.datetime | Unset): Last time logger state was reported
        last_downloaded_block (int | Unset): Last downloaded block number
        last_downloaded_wrap_count (int | Unset): Last downloaded block wrap count
        last_downloaded_time (datetime.datetime | Unset): Last time logger state was downloaded
    """

    download_enabled: bool
    last_reported_block: int | Unset = UNSET
    last_reported_time: datetime.datetime | Unset = UNSET
    last_downloaded_block: int | Unset = UNSET
    last_downloaded_wrap_count: int | Unset = UNSET
    last_downloaded_time: datetime.datetime | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        download_enabled = self.download_enabled

        last_reported_block = self.last_reported_block

        last_reported_time: str | Unset = UNSET
        if not isinstance(self.last_reported_time, Unset):
            last_reported_time = self.last_reported_time.isoformat()

        last_downloaded_block = self.last_downloaded_block

        last_downloaded_wrap_count = self.last_downloaded_wrap_count

        last_downloaded_time: str | Unset = UNSET
        if not isinstance(self.last_downloaded_time, Unset):
            last_downloaded_time = self.last_downloaded_time.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "downloadEnabled": download_enabled,
            }
        )
        if last_reported_block is not UNSET:
            field_dict["lastReportedBlock"] = last_reported_block
        if last_reported_time is not UNSET:
            field_dict["lastReportedTime"] = last_reported_time
        if last_downloaded_block is not UNSET:
            field_dict["lastDownloadedBlock"] = last_downloaded_block
        if last_downloaded_wrap_count is not UNSET:
            field_dict["lastDownloadedWrapCount"] = last_downloaded_wrap_count
        if last_downloaded_time is not UNSET:
            field_dict["lastDownloadedTime"] = last_downloaded_time

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        download_enabled = d.pop("downloadEnabled")

        last_reported_block = d.pop("lastReportedBlock", UNSET)

        _last_reported_time = d.pop("lastReportedTime", UNSET)
        last_reported_time: datetime.datetime | Unset
        if isinstance(_last_reported_time, Unset):
            last_reported_time = UNSET
        else:
            last_reported_time = isoparse(_last_reported_time)

        last_downloaded_block = d.pop("lastDownloadedBlock", UNSET)

        last_downloaded_wrap_count = d.pop("lastDownloadedWrapCount", UNSET)

        _last_downloaded_time = d.pop("lastDownloadedTime", UNSET)
        last_downloaded_time: datetime.datetime | Unset
        if isinstance(_last_downloaded_time, Unset):
            last_downloaded_time = UNSET
        else:
            last_downloaded_time = isoparse(_last_downloaded_time)

        device_logger_state = cls(
            download_enabled=download_enabled,
            last_reported_block=last_reported_block,
            last_reported_time=last_reported_time,
            last_downloaded_block=last_downloaded_block,
            last_downloaded_wrap_count=last_downloaded_wrap_count,
            last_downloaded_time=last_downloaded_time,
        )

        device_logger_state.additional_properties = d
        return device_logger_state

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
