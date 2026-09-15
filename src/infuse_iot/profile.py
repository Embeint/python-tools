#!/usr/bin/env python3

"""Infuse-IoT profile storage."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import platformdirs

PROFILE_STORE_FILENAME = "profiles.json"


@dataclass(frozen=True)
class Profile:
    creation_time: str


def profile_store_path() -> Path:
    return Path(platformdirs.user_config_dir("infuse-iot", "Embeint")) / PROFILE_STORE_FILENAME


@dataclass(frozen=True)
class ProfileConfig:
    active_profile: str | None
    profiles: dict[str, Profile]


def load_profile_config() -> ProfileConfig:
    path = profile_store_path()
    if not path.exists():
        return ProfileConfig(active_profile=None, profiles={})

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return ProfileConfig(
        active_profile=data["active_profile"],
        profiles={name: Profile(**profile) for name, profile in data["profiles"].items()},
    )


def save_profile_config(config: ProfileConfig) -> None:
    path = profile_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "active_profile": config.active_profile,
                "profiles": {name: asdict(profile) for name, profile in config.profiles.items()},
            },
            f,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")


def load_raw_profile_config() -> dict | None:
    path = profile_store_path()
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_profiles() -> dict[str, Profile]:
    return load_profile_config().profiles


def save_profiles(profiles: dict[str, Profile]) -> None:
    config = load_profile_config()
    save_profile_config(ProfileConfig(active_profile=config.active_profile, profiles=profiles))


def configure_profile(name: str) -> tuple[Profile, bool]:
    config = load_profile_config()
    if name in config.profiles:
        return config.profiles[name], False

    profile = Profile(creation_time=datetime.now(timezone.utc).isoformat())
    config.profiles[name] = profile
    if config.active_profile is None:
        config = ProfileConfig(active_profile=name, profiles=config.profiles)
    save_profile_config(config)
    return profile, True


def get_active_profile_name() -> str | None:
    return load_profile_config().active_profile


def set_active_profile(name: str) -> None:
    config = load_profile_config()
    if name not in config.profiles:
        raise ValueError(f"profile does not exist: {name}")

    save_profile_config(ProfileConfig(active_profile=name, profiles=config.profiles))
