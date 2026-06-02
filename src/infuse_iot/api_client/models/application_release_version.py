from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ApplicationReleaseVersion")


@_attrs_define
class ApplicationReleaseVersion:
    """
    Attributes:
        major (int): Major version number of application release
        minor (int): Minor version number of application release
        revision (int): Revision version number of application release
        build_num (int): Build version number of application release
    """

    major: int
    minor: int
    revision: int
    build_num: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        major = self.major

        minor = self.minor

        revision = self.revision

        build_num = self.build_num

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "major": major,
                "minor": minor,
                "revision": revision,
                "buildNum": build_num,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        major = d.pop("major")

        minor = d.pop("minor")

        revision = d.pop("revision")

        build_num = d.pop("buildNum")

        application_release_version = cls(
            major=major,
            minor=minor,
            revision=revision,
            build_num=build_num,
        )

        application_release_version.additional_properties = d
        return application_release_version

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
