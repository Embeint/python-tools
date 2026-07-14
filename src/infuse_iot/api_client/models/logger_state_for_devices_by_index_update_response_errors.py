from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.batch_device_error import BatchDeviceError


T = TypeVar("T", bound="LoggerStateForDevicesByIndexUpdateResponseErrors")


@_attrs_define
class LoggerStateForDevicesByIndexUpdateResponseErrors:
    """Errors keyed by deviceId for devices that could not be updated."""

    additional_properties: dict[str, BatchDeviceError] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.batch_device_error import BatchDeviceError

        d = dict(src_dict)
        logger_state_for_devices_by_index_update_response_errors = cls()

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = BatchDeviceError.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        logger_state_for_devices_by_index_update_response_errors.additional_properties = additional_properties
        return logger_state_for_devices_by_index_update_response_errors

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> BatchDeviceError:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: BatchDeviceError) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
