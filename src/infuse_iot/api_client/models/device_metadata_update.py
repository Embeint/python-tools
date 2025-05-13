from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.device_metadata_update_operation import DeviceMetadataUpdateOperation

if TYPE_CHECKING:
    from ..models.device_metadata import DeviceMetadata


T = TypeVar("T", bound="DeviceMetadataUpdate")


@_attrs_define
class DeviceMetadataUpdate:
    """Metadata update

    Attributes:
        operation (DeviceMetadataUpdateOperation): Operation to perform on metadata, patch to update/add provided
            fields, replace to replace all metadata with provided fields
        value (DeviceMetadata): Metadata fields for device Example: {'Field Name': 'Field Value'}.
    """

    operation: DeviceMetadataUpdateOperation
    value: "DeviceMetadata"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        operation = self.operation.value

        value = self.value.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "operation": operation,
                "value": value,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.device_metadata import DeviceMetadata

        d = dict(src_dict)
        operation = DeviceMetadataUpdateOperation(d.pop("operation"))

        value = DeviceMetadata.from_dict(d.pop("value"))

        device_metadata_update = cls(
            operation=operation,
            value=value,
        )

        device_metadata_update.additional_properties = d
        return device_metadata_update

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
