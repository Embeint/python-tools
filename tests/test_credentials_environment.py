"""Credential source selection without reading or changing the real keyring."""

import os
import unittest
from unittest.mock import patch

from infuse_iot import credentials


class EnvironmentCredentialTests(unittest.TestCase):
    def test_environment_key_takes_precedence(self):
        with (
            patch.dict(os.environ, {"INFUSE_API_KEY": "  environment-test-key  "}),
            patch.object(credentials.keyring, "get_password", side_effect=AssertionError("must not access keyring")),
            patch(
                "infuse_iot.profile.get_active_profile_api_key_id",
                side_effect=AssertionError("must not access profile"),
            ),
        ):
            self.assertEqual(credentials.get_api_key(), "environment-test-key")

    def test_environment_key_selects_platform_authentication(self):
        with patch.dict(os.environ, {"INFUSE_API_KEY": "ik_test-key"}):
            self.assertEqual(credentials.get_api_auth_header(), {"Authorization": "ApiKey ik_test-key"})

    def test_empty_environment_preserves_profile_fallback(self):
        with patch.dict(os.environ, {"INFUSE_API_KEY": " "}), patch(
            "infuse_iot.profile.get_active_profile_api_key_id", return_value="profile-id"
        ), patch.object(credentials.keyring, "get_password", return_value="profile-test-key") as lookup:
            self.assertEqual(credentials.get_api_key(), "profile-test-key")
            lookup.assert_called_once_with("infuse-iot", "profile-api-key-profile-id")

    def test_empty_environment_preserves_keyring_fallback(self):
        with patch.dict(os.environ, {"INFUSE_API_KEY": " "}), patch(
            "infuse_iot.profile.get_active_profile_api_key_id", return_value=None
        ), patch.object(
            credentials.keyring, "get_password", return_value="keyring-test-key"
        ) as lookup:
            self.assertEqual(credentials.get_api_key(), "keyring-test-key")
            lookup.assert_called_once_with("infuse-iot", "api-key")

    def test_missing_credentials_still_fail(self):
        with patch.dict(os.environ, {"INFUSE_API_KEY": ""}), patch(
            "infuse_iot.profile.get_active_profile_api_key_id", return_value=None
        ), patch.object(
            credentials.keyring, "get_password", return_value=None
        ), self.assertRaises(FileNotFoundError):
            credentials.get_api_key()

if __name__ == "__main__":
    unittest.main()
