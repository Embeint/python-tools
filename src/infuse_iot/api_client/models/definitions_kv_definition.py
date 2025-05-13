from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.definitions_field_definition import DefinitionsFieldDefinition


T = TypeVar("T", bound="DefinitionsKVDefinition")


@_attrs_define
class DefinitionsKVDefinition:
    """
    Attributes:
        name (str):
        description (str):
        fields (list['DefinitionsFieldDefinition']):
        reflect (Union[Unset, bool]):
        read_only (Union[Unset, bool]):
        write_only (Union[Unset, bool]):
        default (Union[Unset, str]):
        depends_on (Union[Unset, str]):
        range_ (Union[Unset, int]):
    """

    name: str
    description: str
    fields: list["DefinitionsFieldDefinition"]
    reflect: Union[Unset, bool] = UNSET
    read_only: Union[Unset, bool] = UNSET
    write_only: Union[Unset, bool] = UNSET
    default: Union[Unset, str] = UNSET
    depends_on: Union[Unset, str] = UNSET
    range_: Union[Unset, int] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        description = self.description

        fields = []
        for fields_item_data in self.fields:
            fields_item = fields_item_data.to_dict()
            fields.append(fields_item)

        reflect = self.reflect

        read_only = self.read_only

        write_only = self.write_only

        default = self.default

        depends_on = self.depends_on

        range_ = self.range_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "description": description,
                "fields": fields,
            }
        )
        if reflect is not UNSET:
            field_dict["reflect"] = reflect
        if read_only is not UNSET:
            field_dict["read_only"] = read_only
        if write_only is not UNSET:
            field_dict["write_only"] = write_only
        if default is not UNSET:
            field_dict["default"] = default
        if depends_on is not UNSET:
            field_dict["depends_on"] = depends_on
        if range_ is not UNSET:
            field_dict["range"] = range_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.definitions_field_definition import DefinitionsFieldDefinition

        d = dict(src_dict)
        name = d.pop("name")

        description = d.pop("description")

        fields = []
        _fields = d.pop("fields")
        for fields_item_data in _fields:
            fields_item = DefinitionsFieldDefinition.from_dict(fields_item_data)

            fields.append(fields_item)

        reflect = d.pop("reflect", UNSET)

        read_only = d.pop("read_only", UNSET)

        write_only = d.pop("write_only", UNSET)

        default = d.pop("default", UNSET)

        depends_on = d.pop("depends_on", UNSET)

        range_ = d.pop("range", UNSET)

        definitions_kv_definition = cls(
            name=name,
            description=description,
            fields=fields,
            reflect=reflect,
            read_only=read_only,
            write_only=write_only,
            default=default,
            depends_on=depends_on,
            range_=range_,
        )

        definitions_kv_definition.additional_properties = d
        return definitions_kv_definition

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
