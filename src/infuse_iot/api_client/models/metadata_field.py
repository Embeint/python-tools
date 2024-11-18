from typing import Any, Dict, List, Type, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MetadataField")


@_attrs_define
class MetadataField:
    """
    Attributes:
        name (str): Name of metadata field Example: Field Name.
        required (bool): Whether field is required Example: True.
        unique (bool): Whether field is unique (across all devices of the same board)
    """

    name: str
    required: bool
    unique: bool
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        name = self.name

        required = self.required

        unique = self.unique

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "required": required,
                "unique": unique,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        d = src_dict.copy()
        name = d.pop("name")

        required = d.pop("required")

        unique = d.pop("unique")

        metadata_field = cls(
            name=name,
            required=required,
            unique=unique,
        )

        metadata_field.additional_properties = d
        return metadata_field

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
