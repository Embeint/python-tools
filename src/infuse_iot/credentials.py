#!/usr/bin/env python3

import keyring
import yaml

DEFAULT_NETWORK_KEY = (
    b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
    b"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
)


def set_profile_api_key(api_key_id: str, api_key: str) -> None:
    """
    Save a profile-specific Infuse-IoT API key to the keyring module
    """
    keyring.set_password("infuse-iot", f"profile-api-key-{api_key_id}", api_key)


def get_profile_api_key(api_key_id: str) -> str:
    """
    Retrieve a profile-specific Infuse-IoT API key from the keyring module
    """
    key = keyring.get_password("infuse-iot", f"profile-api-key-{api_key_id}")
    if key is None:
        raise FileNotFoundError(f"Profile API key {api_key_id} does not exist in keyring")
    return key


def set_api_key(api_key: str) -> None:
    """
    Save the Infuse-IoT API key to the keyring module
    """
    keyring.set_password("infuse-iot", "api-key", api_key)


def get_api_key() -> str:
    """
    Retrieve the Infuse-IoT API key from the keyring module
    """
    from infuse_iot.profile import get_active_profile_api_key_id

    profile_api_key_id = get_active_profile_api_key_id()
    if profile_api_key_id is not None:
        return get_profile_api_key(profile_api_key_id)

    key = keyring.get_password("infuse-iot", "api-key")
    if key is None:
        raise FileNotFoundError("API key does not exist in keyring")
    return key


def get_api_auth_header(api_key: str | None = None) -> dict[str, str]:
    """
    Retrieve the Infuse-IoT authentication header
    """
    key = api_key if api_key is not None else get_api_key()
    key_prefix = key[:2]
    if key_prefix == "ik":
        return {"Authorization": f"ApiKey {key}"}
    elif key_prefix == "ey":
        return {"x-api-key": f"Bearer {key}"}
    else:
        raise ValueError(f"Unexpected API key prefix '{key_prefix}'")


def delete_api_key() -> None:
    """
    Delete the Infuse-IoT API key from the keyring module
    """
    keyring.delete_password("infuse-iot", "api-key")


def save_network(network_id: int, network_info: str) -> None:
    """
    Save an Infuse-IoT network key to the keyring module
    """
    username = f"network-{network_id:06x}"
    keyring.set_password("infuse-iot", username, network_info)


def load_network(network_id: int) -> dict:
    """
    Retrieve an Infuse-IoT network key from the keyring module
    """
    if network_id == 0x000000:
        # Default network
        return {"id": 0, "key": DEFAULT_NETWORK_KEY}

    username = f"network-{network_id:06x}"
    key = keyring.get_password("infuse-iot", username)
    if key is None:
        raise FileNotFoundError(f"Network key {network_id:06x} does not exist in keyring")
    return yaml.safe_load(key)


def set_custom_tool_path(path: str):
    """
    Save the location of custom Infuse-IoT tools on the filesystem
    """
    keyring.set_password("infuse-iot", "custom-tools", path)


def get_custom_tool_path() -> str | None:
    """
    Retrieve the location of custom Infuse-IoT tools on the filesystem
    """
    from infuse_iot.profile import get_active_profile_custom_tool_path

    profile_path = get_active_profile_custom_tool_path()
    if profile_path is not None:
        return profile_path

    return keyring.get_password("infuse-iot", "custom-tools")


def delete_custom_tool_path() -> None:
    """
    Delete the location of custom Infuse-IoT tools on the filesystem
    """
    return keyring.delete_password("infuse-iot", "custom-tools")


def set_custom_definitions_path(path: str):
    """
    Save the location of custom Infuse-IoT definitions on the filesystem
    """
    keyring.set_password("infuse-iot", "custom-definitions", path)


def get_custom_definitions_path() -> str | None:
    """
    Retrieve the location of custom Infuse-IoT definitions on the filesystem
    """
    from infuse_iot.profile import get_active_profile_custom_definitions_path

    profile_path = get_active_profile_custom_definitions_path()
    if profile_path is not None:
        return profile_path

    return keyring.get_password("infuse-iot", "custom-definitions")


def delete_custom_definitions_path() -> None:
    """
    Delete the location of custom Infuse-IoT definitions on the filesystem
    """
    return keyring.delete_password("infuse-iot", "custom-definitions")
