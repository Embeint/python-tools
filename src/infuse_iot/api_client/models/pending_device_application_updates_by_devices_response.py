from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.pending_device_application_updates_by_devices_response_data import (
        PendingDeviceApplicationUpdatesByDevicesResponseData,
    )


T = TypeVar("T", bound="PendingDeviceApplicationUpdatesByDevicesResponse")


@_attrs_define
class PendingDeviceApplicationUpdatesByDevicesResponse:
    """
    Attributes:
        data (PendingDeviceApplicationUpdatesByDevicesResponseData): Pending device application updates keyed by
            deviceId. Example: {'d291d4d66bf0a955': {'id': '5f4b1b2b-3b4d-4b5e-8c6f-7d8e9f0a1b2c', 'releaseId':
            '0011223344556677', 'status': 'pending', 'attemptCount': 0, 'maxAttempts': 5, 'createdAt':
            datetime.datetime(2026, 7, 14, 0, 43, 47, 520000, tzinfo=datetime.timezone(datetime.timedelta(0), 'Z')),
            'updatedAt': datetime.datetime(2026, 7, 14, 0, 43, 47, 520000, tzinfo=datetime.timezone(datetime.timedelta(0),
            'Z'))}}.
    """

    data: PendingDeviceApplicationUpdatesByDevicesResponseData
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = self.data.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "data": data,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.pending_device_application_updates_by_devices_response_data import (
            PendingDeviceApplicationUpdatesByDevicesResponseData,
        )

        d = dict(src_dict)
        data = PendingDeviceApplicationUpdatesByDevicesResponseData.from_dict(d.pop("data"))

        pending_device_application_updates_by_devices_response = cls(
            data=data,
        )

        pending_device_application_updates_by_devices_response.additional_properties = d
        return pending_device_application_updates_by_devices_response

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
