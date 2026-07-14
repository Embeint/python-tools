from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.logger_state_for_devices_by_index_update_response_data import (
        LoggerStateForDevicesByIndexUpdateResponseData,
    )
    from ..models.logger_state_for_devices_by_index_update_response_errors import (
        LoggerStateForDevicesByIndexUpdateResponseErrors,
    )


T = TypeVar("T", bound="LoggerStateForDevicesByIndexUpdateResponse")


@_attrs_define
class LoggerStateForDevicesByIndexUpdateResponse:
    """Result of updating logger states for devices by index

    Attributes:
        data (LoggerStateForDevicesByIndexUpdateResponseData): Updated logger states keyed by deviceId for devices that
            were successfully updated.
        errors (LoggerStateForDevicesByIndexUpdateResponseErrors): Errors keyed by deviceId for devices that could not
            be updated.
    """

    data: LoggerStateForDevicesByIndexUpdateResponseData
    errors: LoggerStateForDevicesByIndexUpdateResponseErrors
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        errors = self.errors.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
                "errors": errors,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.logger_state_for_devices_by_index_update_response_data import (
            LoggerStateForDevicesByIndexUpdateResponseData,
        )
        from ..models.logger_state_for_devices_by_index_update_response_errors import (
            LoggerStateForDevicesByIndexUpdateResponseErrors,
        )

        d = dict(src_dict)
        data = LoggerStateForDevicesByIndexUpdateResponseData.from_dict(d.pop("data"))

        errors = LoggerStateForDevicesByIndexUpdateResponseErrors.from_dict(d.pop("errors"))

        logger_state_for_devices_by_index_update_response = cls(
            data=data,
            errors=errors,
        )

        logger_state_for_devices_by_index_update_response.additional_properties = d
        return logger_state_for_devices_by_index_update_response

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
