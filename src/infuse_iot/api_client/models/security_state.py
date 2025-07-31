from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SecurityState")


@_attrs_define
class SecurityState:
    """
    Attributes:
        cloud_public_key (str): Cloud public ECC key as a base64 encoded string
        device_public_key (str): Device public ECC key as a base64 encoded string
        network_id (int): Current network ID
        challenge (str): Challenge used in request as a base64 encoded string
        challenge_response_type (int): Type of the challenge response
        challenge_response (str): Challenge response as a base64 encoded string
    """

    cloud_public_key: str
    device_public_key: str
    network_id: int
    challenge: str
    challenge_response_type: int
    challenge_response: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        cloud_public_key = self.cloud_public_key

        device_public_key = self.device_public_key

        network_id = self.network_id

        challenge = self.challenge

        challenge_response_type = self.challenge_response_type

        challenge_response = self.challenge_response

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "cloudPublicKey": cloud_public_key,
                "devicePublicKey": device_public_key,
                "networkId": network_id,
                "challenge": challenge,
                "challengeResponseType": challenge_response_type,
                "challengeResponse": challenge_response,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        cloud_public_key = d.pop("cloudPublicKey")

        device_public_key = d.pop("devicePublicKey")

        network_id = d.pop("networkId")

        challenge = d.pop("challenge")

        challenge_response_type = d.pop("challengeResponseType")

        challenge_response = d.pop("challengeResponse")

        security_state = cls(
            cloud_public_key=cloud_public_key,
            device_public_key=device_public_key,
            network_id=network_id,
            challenge=challenge,
            challenge_response_type=challenge_response_type,
            challenge_response=challenge_response,
        )

        security_state.additional_properties = d
        return security_state

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
