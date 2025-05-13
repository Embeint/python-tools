from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.algorithm import Algorithm
    from ..models.application_version import ApplicationVersion


T = TypeVar("T", bound="NewDeviceState")


@_attrs_define
class NewDeviceState:
    """
    Attributes:
        application_id (Union[Unset, int]): Last announced application ID
        application_version (Union[Unset, ApplicationVersion]): Application version
        algorithms (Union[Unset, list['Algorithm']]): Last announced algorithms
    """

    application_id: Union[Unset, int] = UNSET
    application_version: Union[Unset, "ApplicationVersion"] = UNSET
    algorithms: Union[Unset, list["Algorithm"]] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        application_id = self.application_id

        application_version: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.application_version, Unset):
            application_version = self.application_version.to_dict()

        algorithms: Union[Unset, list[dict[str, Any]]] = UNSET
        if not isinstance(self.algorithms, Unset):
            algorithms = []
            for algorithms_item_data in self.algorithms:
                algorithms_item = algorithms_item_data.to_dict()
                algorithms.append(algorithms_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if application_id is not UNSET:
            field_dict["applicationId"] = application_id
        if application_version is not UNSET:
            field_dict["applicationVersion"] = application_version
        if algorithms is not UNSET:
            field_dict["algorithms"] = algorithms

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.algorithm import Algorithm
        from ..models.application_version import ApplicationVersion

        d = dict(src_dict)
        application_id = d.pop("applicationId", UNSET)

        _application_version = d.pop("applicationVersion", UNSET)
        application_version: Union[Unset, ApplicationVersion]
        if isinstance(_application_version, Unset):
            application_version = UNSET
        else:
            application_version = ApplicationVersion.from_dict(_application_version)

        algorithms = []
        _algorithms = d.pop("algorithms", UNSET)
        for algorithms_item_data in _algorithms or []:
            algorithms_item = Algorithm.from_dict(algorithms_item_data)

            algorithms.append(algorithms_item)

        new_device_state = cls(
            application_id=application_id,
            application_version=application_version,
            algorithms=algorithms,
        )

        new_device_state.additional_properties = d
        return new_device_state

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
