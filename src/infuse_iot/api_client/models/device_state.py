from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.route_type import RouteType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.algorithm import Algorithm
    from ..models.application_version import ApplicationVersion
    from ..models.uplink_route import UplinkRoute


T = TypeVar("T", bound="DeviceState")


@_attrs_define
class DeviceState:
    """
    Attributes:
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
        application_id (int | Unset): Last announced application ID
        application_version (ApplicationVersion | Unset): Application version
        algorithms (list[Algorithm] | Unset): Last announced algorithms
        last_route_interface (RouteType | Unset): Interface of route
        last_route_udp_address (str | Unset): Address of last packet sent directly via UDP
        last_route_udp_time (datetime.datetime | Unset): Time of last packet sent directly via UDP
        last_route (UplinkRoute | Unset):
        last_route_time (datetime.datetime | Unset): Time of last packet sent by device (via any route)
    """

    created_at: datetime.datetime
    updated_at: datetime.datetime
    application_id: int | Unset = UNSET
    application_version: ApplicationVersion | Unset = UNSET
    algorithms: list[Algorithm] | Unset = UNSET
    last_route_interface: RouteType | Unset = UNSET
    last_route_udp_address: str | Unset = UNSET
    last_route_udp_time: datetime.datetime | Unset = UNSET
    last_route: UplinkRoute | Unset = UNSET
    last_route_time: datetime.datetime | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        application_id = self.application_id

        application_version: dict[str, Any] | Unset = UNSET
        if not isinstance(self.application_version, Unset):
            application_version = self.application_version.to_dict()

        algorithms: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.algorithms, Unset):
            algorithms = []
            for algorithms_item_data in self.algorithms:
                algorithms_item = algorithms_item_data.to_dict()
                algorithms.append(algorithms_item)

        last_route_interface: str | Unset = UNSET
        if not isinstance(self.last_route_interface, Unset):
            last_route_interface = self.last_route_interface.value

        last_route_udp_address = self.last_route_udp_address

        last_route_udp_time: str | Unset = UNSET
        if not isinstance(self.last_route_udp_time, Unset):
            last_route_udp_time = self.last_route_udp_time.isoformat()

        last_route: dict[str, Any] | Unset = UNSET
        if not isinstance(self.last_route, Unset):
            last_route = self.last_route.to_dict()

        last_route_time: str | Unset = UNSET
        if not isinstance(self.last_route_time, Unset):
            last_route_time = self.last_route_time.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "createdAt": created_at,
                "updatedAt": updated_at,
            }
        )
        if application_id is not UNSET:
            field_dict["applicationId"] = application_id
        if application_version is not UNSET:
            field_dict["applicationVersion"] = application_version
        if algorithms is not UNSET:
            field_dict["algorithms"] = algorithms
        if last_route_interface is not UNSET:
            field_dict["lastRouteInterface"] = last_route_interface
        if last_route_udp_address is not UNSET:
            field_dict["lastRouteUdpAddress"] = last_route_udp_address
        if last_route_udp_time is not UNSET:
            field_dict["lastRouteUdpTime"] = last_route_udp_time
        if last_route is not UNSET:
            field_dict["lastRoute"] = last_route
        if last_route_time is not UNSET:
            field_dict["lastRouteTime"] = last_route_time

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.algorithm import Algorithm
        from ..models.application_version import ApplicationVersion
        from ..models.uplink_route import UplinkRoute

        d = dict(src_dict)
        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        application_id = d.pop("applicationId", UNSET)

        _application_version = d.pop("applicationVersion", UNSET)
        application_version: ApplicationVersion | Unset
        if isinstance(_application_version, Unset):
            application_version = UNSET
        else:
            application_version = ApplicationVersion.from_dict(_application_version)

        _algorithms = d.pop("algorithms", UNSET)
        algorithms: list[Algorithm] | Unset = UNSET
        if _algorithms is not UNSET:
            algorithms = []
            for algorithms_item_data in _algorithms:
                algorithms_item = Algorithm.from_dict(algorithms_item_data)

                algorithms.append(algorithms_item)

        _last_route_interface = d.pop("lastRouteInterface", UNSET)
        last_route_interface: RouteType | Unset
        if isinstance(_last_route_interface, Unset):
            last_route_interface = UNSET
        else:
            last_route_interface = RouteType(_last_route_interface)

        last_route_udp_address = d.pop("lastRouteUdpAddress", UNSET)

        _last_route_udp_time = d.pop("lastRouteUdpTime", UNSET)
        last_route_udp_time: datetime.datetime | Unset
        if isinstance(_last_route_udp_time, Unset):
            last_route_udp_time = UNSET
        else:
            last_route_udp_time = isoparse(_last_route_udp_time)

        _last_route = d.pop("lastRoute", UNSET)
        last_route: UplinkRoute | Unset
        if isinstance(_last_route, Unset):
            last_route = UNSET
        else:
            last_route = UplinkRoute.from_dict(_last_route)

        _last_route_time = d.pop("lastRouteTime", UNSET)
        last_route_time: datetime.datetime | Unset
        if isinstance(_last_route_time, Unset):
            last_route_time = UNSET
        else:
            last_route_time = isoparse(_last_route_time)

        device_state = cls(
            created_at=created_at,
            updated_at=updated_at,
            application_id=application_id,
            application_version=application_version,
            algorithms=algorithms,
            last_route_interface=last_route_interface,
            last_route_udp_address=last_route_udp_address,
            last_route_udp_time=last_route_udp_time,
            last_route=last_route,
            last_route_time=last_route_time,
        )

        device_state.additional_properties = d
        return device_state

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
