#!/usr/bin/env python3
"""Regenerate the checked-in Infuse-IoT OpenAPI client.

The script runs ``openapi-python-client`` against a supplied OpenAPI YAML file,
locates the generated package in a temporary staging directory, and atomically
replaces ``src/infuse_iot/api_client`` while preserving its existing README.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TARGET_CLIENT = Path("src/infuse_iot/api_client")
GENERATED_PACKAGE = "infuse_api_client"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_spec_path(spec_path: Path) -> None:
    if not spec_path.exists():
        raise RuntimeError(f"API specification does not exist: {spec_path}")
    if not spec_path.is_file():
        raise RuntimeError(f"API specification is not a file: {spec_path}")


def run_generator(spec_path: Path, staging_dir: Path) -> Path:
    command = ["openapi-python-client", "generate", "--path", str(spec_path)]
    print(f"Generating API client in {staging_dir}")
    try:
        subprocess.run(command, cwd=staging_dir, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("openapi-python-client was not found. Install it and rerun this script.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"openapi-python-client failed with exit code {exc.returncode}") from exc

    matches = sorted(staging_dir.glob(f"*/{GENERATED_PACKAGE}"))
    if not matches:
        raise RuntimeError(f"generated package {GENERATED_PACKAGE!r} was not found under {staging_dir}")
    if len(matches) > 1:
        raise RuntimeError(
            "multiple generated client packages were found: " + ", ".join(str(match) for match in matches)
        )
    return matches[0]


def replace_client(generated_client: Path, target_client: Path) -> None:
    readme = None
    readme_path = target_client / "README.md"
    if readme_path.exists():
        readme = readme_path.read_bytes()

    target_parent = target_client.parent
    with tempfile.TemporaryDirectory(prefix="api-client-backup-", dir=target_parent) as backup:
        backup_client = Path(backup) / target_client.name
        if target_client.exists():
            shutil.move(str(target_client), backup_client)

        try:
            shutil.move(str(generated_client), target_client)
            if readme is not None:
                (target_client / "README.md").write_bytes(readme)
        except Exception:
            if target_client.exists():
                shutil.rmtree(target_client)
            if backup_client.exists():
                shutil.move(str(backup_client), target_client)
            raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate src/infuse_iot/api_client from an OpenAPI YAML file.")
    parser.add_argument(
        "spec_path",
        help="Path to the downloaded OpenAPI YAML file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    root = repo_root()
    spec_path = Path(args.spec_path).expanduser()
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec_path = spec_path.resolve()
    target_client = root / TARGET_CLIENT

    try:
        validate_spec_path(spec_path)

        with tempfile.TemporaryDirectory(prefix="api-client-gen-", dir=root) as staging:
            generated_client = run_generator(spec_path, Path(staging))
            replace_client(generated_client, target_client)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Regenerated {target_client.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
