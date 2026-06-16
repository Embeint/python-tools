from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.application_release_version import ApplicationReleaseVersion


T = TypeVar("T", bound="DeviceApplicationState")


@_attrs_define
class DeviceApplicationState:
    """
    Attributes:
        application_id (int): ID of application
        version (ApplicationReleaseVersion):
        last_reported_time (datetime.datetime): Time of report from device with this application state (if reported by
            device)
        board_target_crc (int | Unset): CRC16 of board target string for application release
        release_id (str | Unset): ID of associated release for the application state (if known)
    """

    application_id: int
    version: ApplicationReleaseVersion
    last_reported_time: datetime.datetime
    board_target_crc: int | Unset = UNSET
    release_id: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        application_id = self.application_id

        version = self.version.to_dict()

        last_reported_time = self.last_reported_time.isoformat()

        board_target_crc = self.board_target_crc

        release_id = self.release_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "applicationId": application_id,
                "version": version,
                "lastReportedTime": last_reported_time,
            }
        )
        if board_target_crc is not UNSET:
            field_dict["boardTargetCrc"] = board_target_crc
        if release_id is not UNSET:
            field_dict["releaseId"] = release_id

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.application_release_version import ApplicationReleaseVersion

        d = dict(src_dict)
        application_id = d.pop("applicationId")

        version = ApplicationReleaseVersion.from_dict(d.pop("version"))

        last_reported_time = isoparse(d.pop("lastReportedTime"))

        board_target_crc = d.pop("boardTargetCrc", UNSET)

        release_id = d.pop("releaseId", UNSET)

        device_application_state = cls(
            application_id=application_id,
            version=version,
            last_reported_time=last_reported_time,
            board_target_crc=board_target_crc,
            release_id=release_id,
        )

        device_application_state.additional_properties = d
        return device_application_state

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
