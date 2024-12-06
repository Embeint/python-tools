import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.route_type import RouteType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.application_version import ApplicationVersion


T = TypeVar("T", bound="DeviceState")


@_attrs_define
class DeviceState:
    """
    Attributes:
        created_at (Union[Unset, datetime.datetime]):
        updated_at (Union[Unset, datetime.datetime]):
        last_route_interface (Union[Unset, RouteType]): Interface of route
        last_route_udp_address (Union[Unset, str]): UDP address of last packet sent by device
        application_id (Union[Unset, int]): Last announced application ID
        application_version (Union[Unset, ApplicationVersion]): Application version
    """

    created_at: Union[Unset, datetime.datetime] = UNSET
    updated_at: Union[Unset, datetime.datetime] = UNSET
    last_route_interface: Union[Unset, RouteType] = UNSET
    last_route_udp_address: Union[Unset, str] = UNSET
    application_id: Union[Unset, int] = UNSET
    application_version: Union[Unset, "ApplicationVersion"] = UNSET
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        created_at: Union[Unset, str] = UNSET
        if not isinstance(self.created_at, Unset):
            created_at = self.created_at.isoformat()

        updated_at: Union[Unset, str] = UNSET
        if not isinstance(self.updated_at, Unset):
            updated_at = self.updated_at.isoformat()

        last_route_interface: Union[Unset, str] = UNSET
        if not isinstance(self.last_route_interface, Unset):
            last_route_interface = self.last_route_interface.value

        last_route_udp_address = self.last_route_udp_address

        application_id = self.application_id

        application_version: Union[Unset, Dict[str, Any]] = UNSET
        if not isinstance(self.application_version, Unset):
            application_version = self.application_version.to_dict()

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if created_at is not UNSET:
            field_dict["createdAt"] = created_at
        if updated_at is not UNSET:
            field_dict["updatedAt"] = updated_at
        if last_route_interface is not UNSET:
            field_dict["lastRouteInterface"] = last_route_interface
        if last_route_udp_address is not UNSET:
            field_dict["lastRouteUdpAddress"] = last_route_udp_address
        if application_id is not UNSET:
            field_dict["applicationId"] = application_id
        if application_version is not UNSET:
            field_dict["applicationVersion"] = application_version

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        from ..models.application_version import ApplicationVersion

        d = src_dict.copy()
        _created_at = d.pop("createdAt", UNSET)
        created_at: Union[Unset, datetime.datetime]
        if isinstance(_created_at, Unset):
            created_at = UNSET
        else:
            created_at = isoparse(_created_at)

        _updated_at = d.pop("updatedAt", UNSET)
        updated_at: Union[Unset, datetime.datetime]
        if isinstance(_updated_at, Unset):
            updated_at = UNSET
        else:
            updated_at = isoparse(_updated_at)

        _last_route_interface = d.pop("lastRouteInterface", UNSET)
        last_route_interface: Union[Unset, RouteType]
        if isinstance(_last_route_interface, Unset):
            last_route_interface = UNSET
        else:
            last_route_interface = RouteType(_last_route_interface)

        last_route_udp_address = d.pop("lastRouteUdpAddress", UNSET)

        application_id = d.pop("applicationId", UNSET)

        _application_version = d.pop("applicationVersion", UNSET)
        application_version: Union[Unset, ApplicationVersion]
        if isinstance(_application_version, Unset):
            application_version = UNSET
        else:
            application_version = ApplicationVersion.from_dict(_application_version)

        device_state = cls(
            created_at=created_at,
            updated_at=updated_at,
            last_route_interface=last_route_interface,
            last_route_udp_address=last_route_udp_address,
            application_id=application_id,
            application_version=application_version,
        )

        device_state.additional_properties = d
        return device_state

    @property
    def additional_keys(self) -> List[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
