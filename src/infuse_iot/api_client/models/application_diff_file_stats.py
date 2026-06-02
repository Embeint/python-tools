from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ApplicationDiffFileStats")


@_attrs_define
class ApplicationDiffFileStats:
    """
    Attributes:
        coap_path (str): CoAP path of file Example: /release/12345.
        len_ (int): Length of file in bytes
        crc (int): CRC32 of file
    """

    coap_path: str
    len_: int
    crc: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        coap_path = self.coap_path

        len_ = self.len_

        crc = self.crc

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "coapPath": coap_path,
                "len": len_,
                "crc": crc,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        coap_path = d.pop("coapPath")

        len_ = d.pop("len")

        crc = d.pop("crc")

        application_diff_file_stats = cls(
            coap_path=coap_path,
            len_=len_,
            crc=crc,
        )

        application_diff_file_stats.additional_properties = d
        return application_diff_file_stats

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
