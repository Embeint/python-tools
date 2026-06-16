from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.device_application_update_status import DeviceApplicationUpdateStatus
from ..types import UNSET, Unset

T = TypeVar("T", bound="DeviceApplicationUpdate")


@_attrs_define
class DeviceApplicationUpdate:
    """
    Attributes:
        release_id (str): ID of application release to update device to
        id (UUID): ID of update
        status (DeviceApplicationUpdateStatus): Status of device application update
        attempt_count (int): Number of attempts made to update the device
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        last_error (str | Unset): Last error message if update failed
        last_attempt_at (datetime.datetime | Unset): Time of last attempt
        downlink_message_id (UUID | Unset): ID of latest downlink message for the update (if sent)
        completed_at (datetime.datetime | Unset): Time the update was completed (if completed)
    """

    release_id: str
    id: UUID
    status: DeviceApplicationUpdateStatus
    attempt_count: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    last_error: str | Unset = UNSET
    last_attempt_at: datetime.datetime | Unset = UNSET
    downlink_message_id: UUID | Unset = UNSET
    completed_at: datetime.datetime | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        release_id = self.release_id

        id = str(self.id)

        status = self.status.value

        attempt_count = self.attempt_count

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        last_error = self.last_error

        last_attempt_at: str | Unset = UNSET
        if not isinstance(self.last_attempt_at, Unset):
            last_attempt_at = self.last_attempt_at.isoformat()

        downlink_message_id: str | Unset = UNSET
        if not isinstance(self.downlink_message_id, Unset):
            downlink_message_id = str(self.downlink_message_id)

        completed_at: str | Unset = UNSET
        if not isinstance(self.completed_at, Unset):
            completed_at = self.completed_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "releaseId": release_id,
                "id": id,
                "status": status,
                "attemptCount": attempt_count,
                "createdAt": created_at,
                "updatedAt": updated_at,
            }
        )
        if last_error is not UNSET:
            field_dict["lastError"] = last_error
        if last_attempt_at is not UNSET:
            field_dict["lastAttemptAt"] = last_attempt_at
        if downlink_message_id is not UNSET:
            field_dict["downlinkMessageId"] = downlink_message_id
        if completed_at is not UNSET:
            field_dict["completedAt"] = completed_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        release_id = d.pop("releaseId")

        id = UUID(d.pop("id"))

        status = DeviceApplicationUpdateStatus(d.pop("status"))

        attempt_count = d.pop("attemptCount")

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        last_error = d.pop("lastError", UNSET)

        _last_attempt_at = d.pop("lastAttemptAt", UNSET)
        last_attempt_at: datetime.datetime | Unset
        if isinstance(_last_attempt_at, Unset):
            last_attempt_at = UNSET
        else:
            last_attempt_at = isoparse(_last_attempt_at)

        _downlink_message_id = d.pop("downlinkMessageId", UNSET)
        downlink_message_id: UUID | Unset
        if isinstance(_downlink_message_id, Unset):
            downlink_message_id = UNSET
        else:
            downlink_message_id = UUID(_downlink_message_id)

        _completed_at = d.pop("completedAt", UNSET)
        completed_at: datetime.datetime | Unset
        if isinstance(_completed_at, Unset):
            completed_at = UNSET
        else:
            completed_at = isoparse(_completed_at)

        device_application_update = cls(
            release_id=release_id,
            id=id,
            status=status,
            attempt_count=attempt_count,
            created_at=created_at,
            updated_at=updated_at,
            last_error=last_error,
            last_attempt_at=last_attempt_at,
            downlink_message_id=downlink_message_id,
            completed_at=completed_at,
        )

        device_application_update.additional_properties = d
        return device_application_update

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
