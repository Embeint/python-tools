from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.application_diff_file_stats import ApplicationDiffFileStats


T = TypeVar("T", bound="ApplicationReleaseDiff")


@_attrs_define
class ApplicationReleaseDiff:
    """
    Attributes:
        id (str): Global unique ID of application release diff (generated on creation)
        from_release_id (str): ID of application release the diff is from
        to_release_id (str): ID of application release the diff is to
        file (ApplicationDiffFileStats):
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
    """

    id: str
    from_release_id: str
    to_release_id: str
    file: ApplicationDiffFileStats
    created_at: datetime.datetime
    updated_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        from_release_id = self.from_release_id

        to_release_id = self.to_release_id

        file = self.file.to_dict()

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "fromReleaseId": from_release_id,
                "toReleaseId": to_release_id,
                "file": file,
                "createdAt": created_at,
                "updatedAt": updated_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.application_diff_file_stats import ApplicationDiffFileStats

        d = dict(src_dict)
        id = d.pop("id")

        from_release_id = d.pop("fromReleaseId")

        to_release_id = d.pop("toReleaseId")

        file = ApplicationDiffFileStats.from_dict(d.pop("file"))

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        application_release_diff = cls(
            id=id,
            from_release_id=from_release_id,
            to_release_id=to_release_id,
            file=file,
            created_at=created_at,
            updated_at=updated_at,
        )

        application_release_diff.additional_properties = d
        return application_release_diff

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
