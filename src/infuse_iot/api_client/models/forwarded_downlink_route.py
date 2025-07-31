from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.downlink_route import DownlinkRoute


T = TypeVar("T", bound="ForwardedDownlinkRoute")


@_attrs_define
class ForwardedDownlinkRoute:
    """
    Attributes:
        device_id (str): The ID of the forwarding device as a hex string Example: d291d4d66bf0a955.
        route (DownlinkRoute):
        auth (int): Auth level for the forwarding device packet
    """

    device_id: str
    route: "DownlinkRoute"
    auth: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        device_id = self.device_id

        route = self.route.to_dict()

        auth = self.auth

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deviceId": device_id,
                "route": route,
                "auth": auth,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.downlink_route import DownlinkRoute

        d = dict(src_dict)
        device_id = d.pop("deviceId")

        route = DownlinkRoute.from_dict(d.pop("route"))

        auth = d.pop("auth")

        forwarded_downlink_route = cls(
            device_id=device_id,
            route=route,
            auth=auth,
        )

        forwarded_downlink_route.additional_properties = d
        return forwarded_downlink_route

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
