from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.definitions_field_definition import DefinitionsFieldDefinition


T = TypeVar("T", bound="DefinitionsStructDefinition")


@_attrs_define
class DefinitionsStructDefinition:
    """
    Attributes:
        description (str):
        fields (list['DefinitionsFieldDefinition']):
    """

    description: str
    fields: list["DefinitionsFieldDefinition"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        description = self.description

        fields = []
        for fields_item_data in self.fields:
            fields_item = fields_item_data.to_dict()
            fields.append(fields_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "description": description,
                "fields": fields,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_field_definition import DefinitionsFieldDefinition

        d = dict(src_dict)
        description = d.pop("description")

        fields = []
        _fields = d.pop("fields")
        for fields_item_data in _fields:
            fields_item = DefinitionsFieldDefinition.from_dict(fields_item_data)

            fields.append(fields_item)

        definitions_struct_definition = cls(
            description=description,
            fields=fields,
        )

        definitions_struct_definition.additional_properties = d
        return definitions_struct_definition

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
