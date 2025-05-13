from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.definitions_enum_value import DefinitionsEnumValue


T = TypeVar("T", bound="DefinitionsEnumDefinition")


@_attrs_define
class DefinitionsEnumDefinition:
    """
    Attributes:
        description (str):
        type_ (str):
        values (list['DefinitionsEnumValue']):
    """

    description: str
    type_: str
    values: list["DefinitionsEnumValue"]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        description = self.description

        type_ = self.type_

        values = []
        for values_item_data in self.values:
            values_item = values_item_data.to_dict()
            values.append(values_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "description": description,
                "type": type_,
                "values": values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_enum_value import DefinitionsEnumValue

        d = dict(src_dict)
        description = d.pop("description")

        type_ = d.pop("type")

        values = []
        _values = d.pop("values")
        for values_item_data in _values:
            values_item = DefinitionsEnumValue.from_dict(values_item_data)

            values.append(values_item)

        definitions_enum_definition = cls(
            description=description,
            type_=type_,
            values=values,
        )

        definitions_enum_definition.additional_properties = d
        return definitions_enum_definition

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
