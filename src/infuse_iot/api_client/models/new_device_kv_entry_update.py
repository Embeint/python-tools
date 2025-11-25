from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.new_device_kv_entry_update_decoded import NewDeviceKVEntryUpdateDecoded


T = TypeVar("T", bound="NewDeviceKVEntryUpdate")


@_attrs_define
class NewDeviceKVEntryUpdate:
    """
    Attributes:
        data (Union[Unset, str]): Raw entry data as a base64 encoded string (must provide either data or decoded)
        decoded (Union[Unset, NewDeviceKVEntryUpdateDecoded]): Decoded entry value (must provide either data or decoded)
    """

    data: Unset | str = UNSET
    decoded: Union[Unset, "NewDeviceKVEntryUpdateDecoded"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.data

        decoded: Unset | dict[str, Any] = UNSET
        if not isinstance(self.decoded, Unset):
            decoded = self.decoded.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if data is not UNSET:
            field_dict["data"] = data
        if decoded is not UNSET:
            field_dict["decoded"] = decoded

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.new_device_kv_entry_update_decoded import NewDeviceKVEntryUpdateDecoded

        d = dict(src_dict)
        data = d.pop("data", UNSET)

        _decoded = d.pop("decoded", UNSET)
        decoded: Unset | NewDeviceKVEntryUpdateDecoded
        if isinstance(_decoded, Unset):
            decoded = UNSET
        else:
            decoded = NewDeviceKVEntryUpdateDecoded.from_dict(_decoded)

        new_device_kv_entry_update = cls(
            data=data,
            decoded=decoded,
        )

        new_device_kv_entry_update.additional_properties = d
        return new_device_kv_entry_update

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
