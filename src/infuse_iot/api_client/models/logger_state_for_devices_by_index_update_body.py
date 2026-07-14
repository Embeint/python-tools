from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.device_logger_state_update import DeviceLoggerStateUpdate


T = TypeVar("T", bound="LoggerStateForDevicesByIndexUpdateBody")


@_attrs_define
class LoggerStateForDevicesByIndexUpdateBody:
    """Body for updating logger states for devices by index

    Attributes:
        update (DeviceLoggerStateUpdate):
        device_ids (list[str]):
    """

    update: DeviceLoggerStateUpdate
    device_ids: list[str]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        update = self.update.to_dict()

        device_ids = self.device_ids

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "update": update,
                "deviceIds": device_ids,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.device_logger_state_update import DeviceLoggerStateUpdate

        d = dict(src_dict)
        update = DeviceLoggerStateUpdate.from_dict(d.pop("update"))

        device_ids = cast(list[str], d.pop("deviceIds"))

        logger_state_for_devices_by_index_update_body = cls(
            update=update,
            device_ids=device_ids,
        )

        logger_state_for_devices_by_index_update_body.additional_properties = d
        return logger_state_for_devices_by_index_update_body

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
