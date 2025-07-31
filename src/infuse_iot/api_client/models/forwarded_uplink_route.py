from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.uplink_route import UplinkRoute


T = TypeVar("T", bound="ForwardedUplinkRoute")


@_attrs_define
class ForwardedUplinkRoute:
    """
    Attributes:
        device_id (str): The ID of the forwarding device as a hex string Example: d291d4d66bf0a955.
        route (UplinkRoute):
        auth (int): Auth level for the forwarding device packet
        rssi (int): RSSI of the packet
    """

    device_id: str
    route: "UplinkRoute"
    auth: int
    rssi: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        device_id = self.device_id

        route = self.route.to_dict()

        auth = self.auth

        rssi = self.rssi

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deviceId": device_id,
                "route": route,
                "auth": auth,
                "rssi": rssi,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.uplink_route import UplinkRoute

        d = dict(src_dict)
        device_id = d.pop("deviceId")

        route = UplinkRoute.from_dict(d.pop("route"))

        auth = d.pop("auth")

        rssi = d.pop("rssi")

        forwarded_uplink_route = cls(
            device_id=device_id,
            route=route,
            auth=auth,
            rssi=rssi,
        )

        forwarded_uplink_route.additional_properties = d
        return forwarded_uplink_route

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
