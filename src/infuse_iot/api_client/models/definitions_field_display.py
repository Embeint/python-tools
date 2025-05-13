from collections.abc import Mapping
from typing import Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.definitions_field_display_fmt import DefinitionsFieldDisplayFmt
from ..types import UNSET, Unset

T = TypeVar("T", bound="DefinitionsFieldDisplay")


@_attrs_define
class DefinitionsFieldDisplay:
    """Display settings for a field

    Attributes:
        fmt (Union[Unset, DefinitionsFieldDisplayFmt]): Format string for field
        digits (Union[Unset, int]):
        postfix (Union[Unset, str]):
    """

    fmt: Union[Unset, DefinitionsFieldDisplayFmt] = UNSET
    digits: Union[Unset, int] = UNSET
    postfix: Union[Unset, str] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        fmt: Union[Unset, str] = UNSET
        if not isinstance(self.fmt, Unset):
            fmt = self.fmt.value

        digits = self.digits

        postfix = self.postfix

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if fmt is not UNSET:
            field_dict["fmt"] = fmt
        if digits is not UNSET:
            field_dict["digits"] = digits
        if postfix is not UNSET:
            field_dict["postfix"] = postfix

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        _fmt = d.pop("fmt", UNSET)
        fmt: Union[Unset, DefinitionsFieldDisplayFmt]
        if isinstance(_fmt, Unset):
            fmt = UNSET
        else:
            fmt = DefinitionsFieldDisplayFmt(_fmt)

        digits = d.pop("digits", UNSET)

        postfix = d.pop("postfix", UNSET)

        definitions_field_display = cls(
            fmt=fmt,
            digits=digits,
            postfix=postfix,
        )

        definitions_field_display.additional_properties = d
        return definitions_field_display

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
