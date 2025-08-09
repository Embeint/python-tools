#!/usr/bin/env python3

import keyring
import yaml


def set_api_key(api_key: str) -> None:
    """
    Save the Infuse-IoT API key to the keyring module
    """
    keyring.set_password("infuse-iot", "api-key", api_key)


def get_api_key() -> str:
    """
    Retrieve the Infuse-IoT API key from the keyring module
    """
    key = keyring.get_password("infuse-iot", "api-key")
    if key is None:
        raise FileNotFoundError("API key does not exist in keyring")
    return key


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


def load_network(network_id: int):
    """
    Retrieve an Infuse-IoT network key from the keyring module
    """
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
    return keyring.get_password("infuse-iot", "custom-definitions")


def delete_custom_definitions_path() -> None:
    """
    Delete the location of custom Infuse-IoT definitions on the filesystem
    """
    return keyring.delete_password("infuse-iot", "custom-definitions")
