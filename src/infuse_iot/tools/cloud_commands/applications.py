#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import glob
import pathlib
import sys
from uuid import UUID

from tabulate import tabulate

import infuse_iot.api_client.models as models
from infuse_iot.api_client import Client
from infuse_iot.api_client.api.application import (
    create_application,
    create_release,
    create_release_diff,
    get_application_by_organisation_id_and_application_id,
    get_applications_by_organisation_id,
    get_diffs_by_organisation_id_and_application_id_and_release_id,
    get_release_by_organisation_id_and_application_id_and_release_id,
    get_releases_by_organisation_id_and_application_id,
)
from infuse_iot.api_client.api.board import (
    get_board_by_id,
    get_boards,
)
from infuse_iot.api_client.api.organisation import (
    get_all_organisations,
    get_organisation_by_id,
)
from infuse_iot.api_client.types import File
from infuse_iot.util.api import fetch_all
from infuse_iot.util.argparse import (
    ValidRelease,
    add_subparsers_with_list,
)
from infuse_iot.util.console import choose_one, user_confirm, user_response
from infuse_iot.util.version import Version

from .base import CloudSubCommand, require_response


class Applications(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_coap = parser.add_parser("apps", help="Application release management")
        parser_coap.set_defaults(command_class=cls)

        tool_parser = add_subparsers_with_list(parser_coap, dest="_cloud_apps_command")

        list_parser = tool_parser.add_parser("list", help="List all application releases")
        list_parser.add_argument("--org", "-o", type=str, help="Organisation ID")
        list_parser.set_defaults(command_fn=cls.list)

        info_parser = tool_parser.add_parser("info", help="Display summary of application releases")
        info_parser.add_argument("--org", "-o", type=str, required=True, help="Organisation ID")
        info_parser.add_argument("--app", "-a", type=lambda x: int(x, 16), required=True, help="Application ID (hex)")
        info_parser.add_argument("--rel", "-r", type=str, help="Release ID")
        info_parser.add_argument("--coap", action="store_true", help="Display CoAP file information")
        info_parser.set_defaults(command_fn=cls.info)

        upload_parser = tool_parser.add_parser("upload", help="Upload application release")
        upload_parser.add_argument("--org", "-o", type=str, help="Organisation ID")
        upload_parser.add_argument("--board", "-b", type=str, help="Board ID")
        upload_parser.add_argument("--name", "-n", type=str, help="Application name override")
        upload_parser.add_argument("--release", "-r", type=ValidRelease, required=True, help="Release to upload")
        upload_parser.set_defaults(command_fn=cls.upload)

    def list(self, client: Client):
        org: UUID
        if self.args.org is None:
            orgs = fetch_all(get_all_organisations, client=client)
            orgs = require_response(orgs, "Organisation query")
            options = [f"{o.name:20s} ({o.id})" for o in orgs]

            idx, _val = choose_one("Organisation", options)
            org = orgs[idx].id
            print(f"Selected organisation '{orgs[idx].name}' ({orgs[idx].id})")
        else:
            org = UUID(self.args.org)

        applications = fetch_all(get_applications_by_organisation_id, client=client, id=org)

        applications = require_response(applications, "Application query")

        app_list = []
        for app in applications:
            app_list.append(
                [
                    f"0x{app.id:08X}",
                    app.name,
                    app.description,
                ]
            )
        print(
            tabulate(
                app_list,
                headers=["ID", "Name", "Description"],
            )
        )

    def _info_one(self, client: Client):
        application = get_application_by_organisation_id_and_application_id.sync(
            client=client,
            id=UUID(self.args.org),
            application_id=self.args.app,
        )
        application = require_response(application, "Get application")
        release = get_release_by_organisation_id_and_application_id_and_release_id.sync(
            client=client, id=UUID(self.args.org), application_id=self.args.app, release_id=self.args.rel
        )
        release = require_response(release, "Get release")
        diffs = fetch_all(
            get_diffs_by_organisation_id_and_application_id_and_release_id,
            client=client,
            id=UUID(self.args.org),
            application_id=self.args.app,
            release_id=self.args.rel,
        )
        diffs = require_response(diffs, "Get diffs")

        version = release.version
        version_str = f"{version.major}.{version.minor}.{version.revision}+{version.build_num:08x}"

        print(
            tabulate(
                [
                    ["Application Name", application.name],
                    ["Application Description", application.description],
                    ["Board Target", release.board_target],
                    ["Version", version_str],
                ],
                tablefmt="simple",
            )
        )

        other_apps = fetch_all(get_applications_by_organisation_id, client=client, id=UUID(self.args.org))
        other_apps = require_response(other_apps, "Application query")

        diff_info = []
        for diff in diffs:
            source_app_id = self.args.app
            from_release = get_release_by_organisation_id_and_application_id_and_release_id.sync(
                client=client, id=UUID(self.args.org), application_id=source_app_id, release_id=diff.from_release_id
            )
            if not isinstance(from_release, models.ApplicationRelease):
                # Try the other applications in the organisation
                for other_app in other_apps:
                    from_release = get_release_by_organisation_id_and_application_id_and_release_id.sync(
                        client=client,
                        id=UUID(self.args.org),
                        application_id=other_app.id,
                        release_id=diff.from_release_id,
                    )
                    if isinstance(from_release, models.ApplicationRelease):
                        source_app_id = other_app.id
                        break
            if not isinstance(from_release, models.ApplicationRelease):
                print(f"Failed to query information about source release {diff.from_release_id}")
                continue
            from_version = from_release.version
            from_version_str = (
                f"{from_version.major}.{from_version.minor}.{from_version.revision}+{from_version.build_num:08x}"
            )
            diff_info.append(
                [f"0x{source_app_id:08x}", from_version_str, diff.file.coap_path, diff.file.len_, diff.file.crc]
            )

        if len(diff_info) > 0:
            print("~~~ Diffs ~~~")
            print(tabulate(diff_info, headers=["From App", "From Version", "Path", "Length", "CRC"]))

    def _info_all(self, client: Client):
        releases = fetch_all(
            get_releases_by_organisation_id_and_application_id,
            client=client,
            id=UUID(self.args.org),
            application_id=self.args.app,
        )

        releases = require_response(releases, "Release query")

        release_list = []
        for release in releases:
            version = release.version
            version_str = f"{version.major}.{version.minor}.{version.revision}+{version.build_num:08x}"
            info = [
                f"{release.board_target}",
                version_str,
                f"{release.id}",
            ]
            if self.args.coap:
                info += [release.file.coap_path, str(release.file.len_), str(release.file.crc)]
            else:
                info += [
                    f"{release.file.len_ / 1024:.2f} kB",
                    str(release.created_at),
                ]
            release_list.append(info)
        if self.args.coap:
            headers = ["Board Target", "Version", "ID", "Path", "Length", "CRC"]
        else:
            headers = ["Board Target", "Version", "ID", "Full OTA", "Created"]
        print(
            tabulate(
                release_list,
                headers=headers,
            )
        )

    def info(self, client: Client):
        if self.args.rel:
            self._info_one(client)
        else:
            self._info_all(client)

    def upload(self, client: Client):
        try:
            self._board = UUID(self.args.board) if self.args.board else None
        except ValueError:
            sys.exit(f"Board ID: '{self.args.board}' is not a valid UUID")
        try:
            self._org = UUID(self.args.org) if self.args.org else None
        except ValueError:
            sys.exit(f"Organisation ID: '{self.args.org}' is not a valid UUID")

        release: ValidRelease = self.args.release
        release_app_meta = release.metadata["application"]
        name = self.args.name or release_app_meta["primary"]
        app_id = release_app_meta["id"]
        board_target = release_app_meta["board"]
        version = Version.from_string(release_app_meta["version"])

        if self._org is None:
            orgs = fetch_all(get_all_organisations, client=client)
            orgs = require_response(orgs, "Organisation query")
            options = [f"{o.name:20s} ({o.id})" for o in orgs]

            idx, _val = choose_one("Organisation", options)
            self._org = orgs[idx].id
            self._org_name = orgs[idx].name
        else:
            org = get_organisation_by_id.sync(client=client, id=self._org)
            if not isinstance(org, models.Organisation):
                sys.exit(f"Failed to query org for ID {self._org}")
            self._org_name = org.name

        if self._board is None:
            boards = fetch_all(get_boards, client=client, organisation_id=self._org)
            boards = require_response(boards, "Board query")
            options = [f"{b.name:20s} ({b.id})" for b in boards]

            idx, _val = choose_one("Board", options)
            self._board = boards[idx].id
            self._board_name = boards[idx].name
        else:
            board = get_board_by_id.sync(client=client, id=self._board)
            if not isinstance(board, models.Board):
                sys.exit(f"Failed to query board for ID {self._board}")
            self._board_name = board.name

        application = get_application_by_organisation_id_and_application_id.sync(
            client=client, id=self._org, application_id=app_id
        )

        if application is None or (isinstance(application, models.Error) and application.code == 404):
            dialog = f"Application 0x{app_id:08x} does not exist in organisation {self._org_name}, create?"
            if not user_confirm(dialog):
                return
            print(f"Creating application 0x{app_id:08x} in organisation {self._org_name}")
            description = user_response("Application description:")
            body = models.NewApplication(id=app_id, name=name, description=description)
            application = create_application.sync(client=client, id=self._org, body=body)

        if not isinstance(application, models.Application):
            sys.exit(f"Unexpected internal type {type(application)}")

        ota_files = glob.glob(str(release.dir / "ota-*.bin"))
        if len(ota_files) == 0:
            # Old release folder, try and find the right file
            app_folder = release.dir / release_app_meta["primary"] / "zephyr"
            tfm_file = app_folder / "tfm_s_zephyr_ns_signed.bin"
            std_file = app_folder / "zephyr.signed.bin"
            if tfm_file.exists():
                ota_files = [str(tfm_file)]
            elif std_file.exists():
                ota_files = [str(std_file)]
            if len(ota_files) == 1 and not user_confirm(f"Use file {ota_files[0]} for upload?"):
                sys.exit()
        if len(ota_files) != 1:
            sys.exit(f"Unexpected OTA file search result {ota_files}")

        def get_all_releases(org: UUID, board: UUID, app_id: int) -> dict[Version, models.ApplicationRelease]:
            releases = fetch_all(
                get_releases_by_organisation_id_and_application_id,
                client=client,
                id=org,
                application_id=app_id,
            )
            releases = require_response(releases, "Release query")

            by_version: dict[Version, models.ApplicationRelease] = {}
            for r in releases:
                if r.board_id != board:
                    continue
                v = Version(r.version.major, r.version.minor, r.version.revision, r.version.build_num)
                by_version[v] = r
            return by_version

        cloud_releases_by_version = get_all_releases(self._org, self._board, app_id)
        cloud_release = cloud_releases_by_version.get(version)
        if cloud_release is not None:
            print(f"Found release for application '0x{app_id:08x} {str(version)}' ({cloud_release.id})")
        else:
            dialog = (
                f"Create release for application '0x{app_id:08x} {str(version)}'"
                + f" in organisation '{self._org_name}' for board '{self._board_name}'?"
            )
            if not user_confirm(dialog):
                return

            with open(ota_files[0], "rb") as f:
                ota_file = File(f, ota_files[0], None)

                release_obj = models.CreateReleaseBody(
                    file=ota_file,
                    file_diff_len=str(0),
                    version_major=str(version.major),
                    version_minor=str(version.minor),
                    version_revision=str(version.revision),
                    version_build_num=str(version.build_num),
                    board_id=self._board,
                    board_target=board_target,
                )

                rsp = create_release.sync(
                    client=client,
                    id=self._org,
                    application_id=app_id,
                    body=release_obj,
                )
                rsp = require_response(rsp, "Create release")
                print(f"Release created with ID '{rsp.id}'")
                cloud_release = rsp

        def upload_diffs_from_application(
            org: UUID,
            board: UUID,
            application: models.Application,
            releases_from_version: dict[Version, models.ApplicationRelease],
            diff_folder: pathlib.Path,
        ):
            for path in diff_folder.iterdir():
                if path.is_dir():
                    try:
                        other_app_id = int(path.stem, 16)
                    except ValueError:
                        print(f"{path.stem} does not appear to be an application ID")
                        continue
                    other_application = get_application_by_organisation_id_and_application_id.sync(
                        client=client, id=org, application_id=other_app_id
                    )
                    if not isinstance(other_application, models.Application):
                        print(f"Could not retrieve application with ID {path.stem}")
                        continue
                    other_application_releases = get_all_releases(org, board, other_application.id)
                    upload_diffs_from_application(org, board, other_application, other_application_releases, path)
                    continue
                elif path.suffix != ".bin":
                    continue
                try:
                    diff_from_version = Version.from_string(path.stem)
                except ValueError:
                    print(f"Couldn't parse diff files version '{path.stem}'")
                    continue
                from_version = releases_from_version.get(diff_from_version)
                if from_version is None:
                    print(f"Version {diff_from_version} doesn't exist on cloud for application 0x{application.id:08x}")
                    continue

                with open(path, "rb") as f:
                    diff_file = File(f, str(path), None)

                    create_body = models.CreateReleaseDiffBody(file=diff_file, from_release_id=from_version.id)
                    diff_rsp = create_release_diff.sync(
                        client=client,
                        id=org,
                        application_id=app_id,
                        release_id=cloud_release.id,
                        body=create_body,
                    )
                    prefix = f"{str(diff_from_version)} -> {str(version)}"
                    if isinstance(diff_rsp, models.Error):
                        print(f"{prefix}: <{diff_rsp.code}> {diff_rsp.message}")
                    elif isinstance(diff_rsp, models.ApplicationReleaseDiff):
                        print(f"{prefix}: Diff created with ID '{diff_rsp.id}'")
                    else:
                        print(f"{prefix}: No response")

        # Upload any diffs
        diff_folder = release.dir / "diffs"
        if not diff_folder.exists():
            return
        upload_diffs_from_application(self._org, self._board, application, cloud_releases_by_version, diff_folder)
