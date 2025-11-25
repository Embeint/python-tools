import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.device_entry_update_status import DeviceEntryUpdateStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.new_device_kv_entry_update_decoded import NewDeviceKVEntryUpdateDecoded


T = TypeVar("T", bound="DeviceKVEntryUpdate")


@_attrs_define
class DeviceKVEntryUpdate:
    """
    Attributes:
        id (UUID): ID of update
        key_id (int): Key id
        crc (int): CRC32 of entry update value
        status (DeviceEntryUpdateStatus): Status of device KV entry update
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        data (Union[Unset, str]): Raw entry data as a base64 encoded string (must provide either data or decoded)
        decoded (Union[Unset, NewDeviceKVEntryUpdateDecoded]): Decoded entry value (must provide either data or decoded)
        last_error (Union[Unset, str]): Last error message if update failed
        last_attempt_at (Union[Unset, datetime.datetime]): Time of last attempt
    """

    id: UUID
    key_id: int
    crc: int
    status: DeviceEntryUpdateStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
    data: Unset | str = UNSET
    decoded: Union[Unset, "NewDeviceKVEntryUpdateDecoded"] = UNSET
    last_error: Unset | str = UNSET
    last_attempt_at: Unset | datetime.datetime = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        key_id = self.key_id

        crc = self.crc

        status = self.status.value

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        data = self.data

        decoded: Unset | dict[str, Any] = UNSET
        if not isinstance(self.decoded, Unset):
            decoded = self.decoded.to_dict()

        last_error = self.last_error

        last_attempt_at: Unset | str = UNSET
        if not isinstance(self.last_attempt_at, Unset):
            last_attempt_at = self.last_attempt_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "keyId": key_id,
                "crc": crc,
                "status": status,
                "createdAt": created_at,
                "updatedAt": updated_at,
            }
        )
        if data is not UNSET:
            field_dict["data"] = data
        if decoded is not UNSET:
            field_dict["decoded"] = decoded
        if last_error is not UNSET:
            field_dict["lastError"] = last_error
        if last_attempt_at is not UNSET:
            field_dict["lastAttemptAt"] = last_attempt_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.new_device_kv_entry_update_decoded import NewDeviceKVEntryUpdateDecoded

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        key_id = d.pop("keyId")

        crc = d.pop("crc")

        status = DeviceEntryUpdateStatus(d.pop("status"))

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        data = d.pop("data", UNSET)

        _decoded = d.pop("decoded", UNSET)
        decoded: Unset | NewDeviceKVEntryUpdateDecoded
        if isinstance(_decoded, Unset):
            decoded = UNSET
        else:
            decoded = NewDeviceKVEntryUpdateDecoded.from_dict(_decoded)

        last_error = d.pop("lastError", UNSET)

        _last_attempt_at = d.pop("lastAttemptAt", UNSET)
        last_attempt_at: Unset | datetime.datetime
        if isinstance(_last_attempt_at, Unset):
            last_attempt_at = UNSET
        else:
            last_attempt_at = isoparse(_last_attempt_at)

        device_kv_entry_update = cls(
            id=id,
            key_id=key_id,
            crc=crc,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            data=data,
            decoded=decoded,
            last_error=last_error,
            last_attempt_at=last_attempt_at,
        )

        device_kv_entry_update.additional_properties = d
        return device_kv_entry_update

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
