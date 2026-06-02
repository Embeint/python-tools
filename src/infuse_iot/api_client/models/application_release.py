from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

if TYPE_CHECKING:
    from ..models.application_release_file_stats import ApplicationReleaseFileStats
    from ..models.application_release_version import ApplicationReleaseVersion


T = TypeVar("T", bound="ApplicationRelease")


@_attrs_define
class ApplicationRelease:
    """
    Attributes:
        id (str): Global unique ID of application release (generated on creation)
        application_id (int): ID of application the release belongs to
        organisation_id (UUID): ID of organisation the application release belongs to
        file (ApplicationReleaseFileStats):
        version (ApplicationReleaseVersion):
        board_id (UUID): ID of board the application release is for
        board_target (str): Board target for application release
        board_target_crc (int): CRC16 of board target string
        created_at (datetime.datetime):
        updated_at (datetime.datetime):
    """

    id: str
    application_id: int
    organisation_id: UUID
    file: ApplicationReleaseFileStats
    version: ApplicationReleaseVersion
    board_id: UUID
    board_target: str
    board_target_crc: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        application_id = self.application_id

        organisation_id = str(self.organisation_id)

        file = self.file.to_dict()

        version = self.version.to_dict()

        board_id = str(self.board_id)

        board_target = self.board_target

        board_target_crc = self.board_target_crc

        created_at = self.created_at.isoformat()

        updated_at = self.updated_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "applicationId": application_id,
                "organisationId": organisation_id,
                "file": file,
                "version": version,
                "boardId": board_id,
                "boardTarget": board_target,
                "boardTargetCRC": board_target_crc,
                "createdAt": created_at,
                "updatedAt": updated_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.application_release_file_stats import ApplicationReleaseFileStats
        from ..models.application_release_version import ApplicationReleaseVersion

        d = dict(src_dict)
        id = d.pop("id")

        application_id = d.pop("applicationId")

        organisation_id = UUID(d.pop("organisationId"))

        file = ApplicationReleaseFileStats.from_dict(d.pop("file"))

        version = ApplicationReleaseVersion.from_dict(d.pop("version"))

        board_id = UUID(d.pop("boardId"))

        board_target = d.pop("boardTarget")

        board_target_crc = d.pop("boardTargetCRC")

        created_at = isoparse(d.pop("createdAt"))

        updated_at = isoparse(d.pop("updatedAt"))

        application_release = cls(
            id=id,
            application_id=application_id,
            organisation_id=organisation_id,
            file=file,
            version=version,
            board_id=board_id,
            board_target=board_target,
            board_target_crc=board_target_crc,
            created_at=created_at,
            updated_at=updated_at,
        )

        application_release.additional_properties = d
        return application_release

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
