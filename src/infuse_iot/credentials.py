#!/usr/bin/env python3

import keyring


def set_api_key(api_key):
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
