from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.definitions_tdf_definitions import DefinitionsTDFDefinitions
    from ..models.definitions_tdf_structs import DefinitionsTDFStructs


T = TypeVar("T", bound="DefinitionsTDF")


@_attrs_define
class DefinitionsTDF:
    """
    Attributes:
        structs (DefinitionsTDFStructs):
        definitions (DefinitionsTDFDefinitions):
    """

    structs: "DefinitionsTDFStructs"
    definitions: "DefinitionsTDFDefinitions"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        structs = self.structs.to_dict()

        definitions = self.definitions.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "structs": structs,
                "definitions": definitions,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_tdf_definitions import DefinitionsTDFDefinitions
        from ..models.definitions_tdf_structs import DefinitionsTDFStructs

        d = dict(src_dict)
        structs = DefinitionsTDFStructs.from_dict(d.pop("structs"))

        definitions = DefinitionsTDFDefinitions.from_dict(d.pop("definitions"))

        definitions_tdf = cls(
            structs=structs,
            definitions=definitions,
        )

        definitions_tdf.additional_properties = d
        return definitions_tdf

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
