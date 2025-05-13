from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.definitions_field_conversion_int import DefinitionsFieldConversionInt
from ..types import UNSET, Unset

T = TypeVar("T", bound="DefinitionsFieldConversion")


@_attrs_define
class DefinitionsFieldConversion:
    """Conversion formula for a field (m * <value> + c)

    Attributes:
        m (Union[Unset, float]):
        c (Union[Unset, float]):
        int_ (Union[Unset, DefinitionsFieldConversionInt]): Byte array value should be treated  as an integer
    """

    m: Union[Unset, float] = UNSET
    c: Union[Unset, float] = UNSET
    int_: Union[Unset, DefinitionsFieldConversionInt] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        m = self.m

        c = self.c

        int_: Union[Unset, str] = UNSET
        if not isinstance(self.int_, Unset):
            int_ = self.int_.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if m is not UNSET:
            field_dict["m"] = m
        if c is not UNSET:
            field_dict["c"] = c
        if int_ is not UNSET:
            field_dict["int"] = int_

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        m = d.pop("m", UNSET)

        c = d.pop("c", UNSET)

        _int_ = d.pop("int", UNSET)
        int_: Union[Unset, DefinitionsFieldConversionInt]
        if isinstance(_int_, Unset):
            int_ = UNSET
        else:
            int_ = DefinitionsFieldConversionInt(_int_)

        definitions_field_conversion = cls(
            m=m,
            c=c,
            int_=int_,
        )

        definitions_field_conversion.additional_properties = d
        return definitions_field_conversion

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
