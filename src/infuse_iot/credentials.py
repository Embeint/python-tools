#!/usr/bin/env python3

import keyring
import yaml


def set_api_key(api_key: str):
    """
    Save the Infuse-IoT API key to the keyring module
    """
    keyring.set_password("infuse-iot", "api-key", api_key)


def get_api_key():
    """
    Retrieve the Infuse-IoT API key from the keyring module
    """
    key = keyring.get_password("infuse-iot", "api-key")
    if key is None:
        raise FileNotFoundError("API key does not exist in keyring")
    return key


def save_network(network_id: int, network_info: str):
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
