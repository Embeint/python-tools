from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.uplink_route import UplinkRoute


T = TypeVar("T", bound="UplinkRouteAndDeviceId")


@_attrs_define
class UplinkRouteAndDeviceId:
    """Uplink route with device ID

    Attributes:
        device_id (str): 8 byte DeviceID as a hex string Example: d291d4d66bf0a955.
        last_route (UplinkRoute):
    """

    device_id: str
    last_route: "UplinkRoute"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        device_id = self.device_id

        last_route = self.last_route.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deviceId": device_id,
                "lastRoute": last_route,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.uplink_route import UplinkRoute

        d = dict(src_dict)
        device_id = d.pop("deviceId")

        last_route = UplinkRoute.from_dict(d.pop("lastRoute"))

        uplink_route_and_device_id = cls(
            device_id=device_id,
            last_route=last_route,
        )

        uplink_route_and_device_id.additional_properties = d
        return uplink_route_and_device_id

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
