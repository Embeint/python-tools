from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="NewDeviceApplicationUpdate")


@_attrs_define
class NewDeviceApplicationUpdate:
    """
    Attributes:
        release_id (str): ID of application release to update device to
        max_attempts (int | Unset): Maximum number of attempts to update the device - set to 0 for unlimited attempts
            Default: 5.
    """

    release_id: str
    max_attempts: int | Unset = 5
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        release_id = self.release_id

        max_attempts = self.max_attempts

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "releaseId": release_id,
            }
        )
        if max_attempts is not UNSET:
            field_dict["maxAttempts"] = max_attempts

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        release_id = d.pop("releaseId")

        max_attempts = d.pop("maxAttempts", UNSET)

        new_device_application_update = cls(
            release_id=release_id,
            max_attempts=max_attempts,
        )

        new_device_application_update.additional_properties = d
        return new_device_application_update

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
