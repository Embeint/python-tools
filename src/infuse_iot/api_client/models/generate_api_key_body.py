from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.api_key_org_user_type import APIKeyOrgUserType

if TYPE_CHECKING:
    from ..models.generate_api_key_body_resource_perms import GenerateAPIKeyBodyResourcePerms


T = TypeVar("T", bound="GenerateAPIKeyBody")


@_attrs_define
class GenerateAPIKeyBody:
    """
    Attributes:
        organisation_id (UUID): ID of the organisation Example: 123e4567-e89b-12d3-a456-426614174000.
        user_type (APIKeyOrgUserType): The type of user in the organization.
        resource_perms (GenerateAPIKeyBodyResourcePerms):
    """

    organisation_id: UUID
    user_type: APIKeyOrgUserType
    resource_perms: "GenerateAPIKeyBodyResourcePerms"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        organisation_id = str(self.organisation_id)

        user_type = self.user_type.value

        resource_perms = self.resource_perms.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "organisationId": organisation_id,
                "userType": user_type,
                "resourcePerms": resource_perms,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.generate_api_key_body_resource_perms import GenerateAPIKeyBodyResourcePerms

        d = dict(src_dict)
        organisation_id = UUID(d.pop("organisationId"))

        user_type = APIKeyOrgUserType(d.pop("userType"))

        resource_perms = GenerateAPIKeyBodyResourcePerms.from_dict(d.pop("resourcePerms"))

        generate_api_key_body = cls(
            organisation_id=organisation_id,
            user_type=user_type,
            resource_perms=resource_perms,
        )

        generate_api_key_body.additional_properties = d
        return generate_api_key_body

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
