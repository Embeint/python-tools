from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.definitions_field_conversion import DefinitionsFieldConversion
    from ..models.definitions_field_display import DefinitionsFieldDisplay


T = TypeVar("T", bound="DefinitionsFieldDefinition")


@_attrs_define
class DefinitionsFieldDefinition:
    """
    Attributes:
        name (str): Field name
        type_ (str): Field type
        description (Union[Unset, str]): Field description
        num (Union[Unset, int]): If field is array, the number of elements (0 for variable length)
        display (Union[Unset, DefinitionsFieldDisplay]): Display settings for a field
        conversion (Union[Unset, DefinitionsFieldConversion]): Conversion formula for a field (m * <value> + c)
    """

    name: str
    type_: str
    description: Union[Unset, str] = UNSET
    num: Union[Unset, int] = UNSET
    display: Union[Unset, "DefinitionsFieldDisplay"] = UNSET
    conversion: Union[Unset, "DefinitionsFieldConversion"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        type_ = self.type_

        description = self.description

        num = self.num

        display: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.display, Unset):
            display = self.display.to_dict()

        conversion: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.conversion, Unset):
            conversion = self.conversion.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "type": type_,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if num is not UNSET:
            field_dict["num"] = num
        if display is not UNSET:
            field_dict["display"] = display
        if conversion is not UNSET:
            field_dict["conversion"] = conversion

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_field_conversion import DefinitionsFieldConversion
        from ..models.definitions_field_display import DefinitionsFieldDisplay

        d = dict(src_dict)
        name = d.pop("name")

        type_ = d.pop("type")

        description = d.pop("description", UNSET)

        num = d.pop("num", UNSET)

        _display = d.pop("display", UNSET)
        display: Union[Unset, DefinitionsFieldDisplay]
        if isinstance(_display, Unset):
            display = UNSET
        else:
            display = DefinitionsFieldDisplay.from_dict(_display)

        _conversion = d.pop("conversion", UNSET)
        conversion: Union[Unset, DefinitionsFieldConversion]
        if isinstance(_conversion, Unset):
            conversion = UNSET
        else:
            conversion = DefinitionsFieldConversion.from_dict(_conversion)

        definitions_field_definition = cls(
            name=name,
            type_=type_,
            description=description,
            num=num,
            display=display,
            conversion=conversion,
        )

        definitions_field_definition.additional_properties = d
        return definitions_field_definition

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
