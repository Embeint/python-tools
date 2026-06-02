from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from .. import types
from ..types import File

T = TypeVar("T", bound="CreateReleaseBody")


@_attrs_define
class CreateReleaseBody:
    """
    Attributes:
        file (File):
        file_diff_len (str):
        version_major (str):
        version_minor (str):
        version_revision (str):
        version_build_num (str):
        board_id (UUID): ID of board the application release is for
        board_target (str): Revision of board the application release is for
    """

    file: File
    file_diff_len: str
    version_major: str
    version_minor: str
    version_revision: str
    version_build_num: str
    board_id: UUID
    board_target: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        file = self.file.to_tuple()

        file_diff_len = self.file_diff_len

        version_major = self.version_major

        version_minor = self.version_minor

        version_revision = self.version_revision

        version_build_num = self.version_build_num

        board_id = str(self.board_id)

        board_target = self.board_target

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "file": file,
                "fileDiffLen": file_diff_len,
                "versionMajor": version_major,
                "versionMinor": version_minor,
                "versionRevision": version_revision,
                "versionBuildNum": version_build_num,
                "boardId": board_id,
                "boardTarget": board_target,
            }
        )

        return field_dict

    def to_multipart(self) -> types.RequestFiles:
        files: types.RequestFiles = []

        files.append(("file", self.file.to_tuple()))

        files.append(("fileDiffLen", (None, str(self.file_diff_len).encode(), "text/plain")))

        files.append(("versionMajor", (None, str(self.version_major).encode(), "text/plain")))

        files.append(("versionMinor", (None, str(self.version_minor).encode(), "text/plain")))

        files.append(("versionRevision", (None, str(self.version_revision).encode(), "text/plain")))

        files.append(("versionBuildNum", (None, str(self.version_build_num).encode(), "text/plain")))

        files.append(("boardId", (None, str(self.board_id), "text/plain")))

        files.append(("boardTarget", (None, str(self.board_target).encode(), "text/plain")))

        for prop_name, prop in self.additional_properties.items():
            files.append((prop_name, (None, str(prop).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        file = File(payload=BytesIO(d.pop("file")))

        file_diff_len = d.pop("fileDiffLen")

        version_major = d.pop("versionMajor")

        version_minor = d.pop("versionMinor")

        version_revision = d.pop("versionRevision")

        version_build_num = d.pop("versionBuildNum")

        board_id = UUID(d.pop("boardId"))

        board_target = d.pop("boardTarget")

        create_release_body = cls(
            file=file,
            file_diff_len=file_diff_len,
            version_major=version_major,
            version_minor=version_minor,
            version_revision=version_revision,
            version_build_num=version_build_num,
            board_id=board_id,
            board_target=board_target,
        )

        create_release_body.additional_properties = d
        return create_release_body

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
