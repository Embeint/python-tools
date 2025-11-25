import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.device_kv_entry_decoded import DeviceKVEntryDecoded


T = TypeVar("T", bound="DeviceKVEntry")


@_attrs_define
class DeviceKVEntry:
    """
    Attributes:
        key_id (int): Key id
        crc (int): CRC32 of entry value
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        key_name (Union[Unset, str]): Key name - if definition known
        data (Union[Unset, str]): Raw entry data as a base64 encoded string - if not write_only
        decoded (Union[Unset, DeviceKVEntryDecoded]): Decoded entry value - if not write_only and definition known
    """

    key_id: int
    crc: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    key_name: Unset | str = UNSET
    data: Unset | str = UNSET
    decoded: Union[Unset, "DeviceKVEntryDecoded"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        key_id = self.key_id

        crc = self.crc

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        key_name = self.key_name

        data = self.data

        decoded: Unset | dict[str, Any] = UNSET
        if not isinstance(self.decoded, Unset):
            decoded = self.decoded.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "keyId": key_id,
                "crc": crc,
                "createdAt": created_at,
                "updatedAt": updated_at,
            }
        )
        if key_name is not UNSET:
            field_dict["keyName"] = key_name
        if data is not UNSET:
            field_dict["data"] = data
        if decoded is not UNSET:
            field_dict["decoded"] = decoded

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.device_kv_entry_decoded import DeviceKVEntryDecoded

        d = dict(src_dict)
        key_id = d.pop("keyId")

        crc = d.pop("crc")

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        key_name = d.pop("keyName", UNSET)

        data = d.pop("data", UNSET)

        _decoded = d.pop("decoded", UNSET)
        decoded: Unset | DeviceKVEntryDecoded
        if isinstance(_decoded, Unset):
            decoded = UNSET
        else:
            decoded = DeviceKVEntryDecoded.from_dict(_decoded)

        device_kv_entry = cls(
            key_id=key_id,
            crc=crc,
            created_at=created_at,
            updated_at=updated_at,
            key_name=key_name,
            data=data,
            decoded=decoded,
        )

        device_kv_entry.additional_properties = d
        return device_kv_entry

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
