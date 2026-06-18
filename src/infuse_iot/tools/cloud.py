#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import glob
import sys
from typing import Any
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
    create_board,
    get_board_by_id,
    get_boards,
)
from infuse_iot.api_client.api.coap import get_coap_files
from infuse_iot.api_client.api.device import (
    create_device_application_update_by_device_id,
    get_device_application_state_by_device_id,
    get_device_application_updates_by_device_id,
    get_device_by_device_id,
    get_device_kv_entries_by_device_id,
    get_device_last_route_by_device_id,
    get_device_logger_states_by_device_id,
    get_device_state_by_id,
)
from infuse_iot.api_client.api.organisation import (
    create_organisation,
    get_all_organisations,
    get_organisation_by_id,
)
from infuse_iot.api_client.types import File, Unset
from infuse_iot.commands import InfuseCommand
from infuse_iot.credentials import get_api_key
from infuse_iot.util.argparse import ValidRelease
from infuse_iot.util.console import choose_one, user_confirm, user_response
from infuse_iot.util.version import Version


class CloudSubCommand:
    def __init__(self, args):
        self.args = args

    def run(self):
        """Run cloud sub-command"""

    def client(self):
        """Get API client object ready to use"""
        bearer = self.args.api_key if self.args.api_key else get_api_key()
        return Client(base_url="https://api.infuse-iot.com").with_headers({"x-api-key": f"Bearer {bearer}"})


class Organisations(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_orgs = parser.add_parser("orgs", help="Infuse-IoT organisations")
        parser_orgs.set_defaults(command_class=cls)

        tool_parser = parser_orgs.add_subparsers(title="commands", metavar="<command>", required=True)

        list_parser = tool_parser.add_parser("list", help="List all organisations")
        list_parser.set_defaults(command_fn=cls.list)

        create_parser = tool_parser.add_parser("create", help="Create new organisation")
        create_parser.add_argument("--name", "-n", type=str, required=True)
        create_parser.set_defaults(command_fn=cls.create)

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def list(self, client: Client):
        org_list = []

        orgs = get_all_organisations.sync(client=client)
        if isinstance(orgs, models.Error) or orgs is None:
            sys.exit(f"Organisation query failed {orgs}")
        for o in orgs:
            org_list.append([o.name, o.id])

        print(
            tabulate(
                org_list,
                headers=["Name", "ID"],
            )
        )

    def create(self, client: Client):
        rsp = create_organisation.sync_detailed(
            client=client,
            body=models.NewOrganisation(self.args.name),
        )

        if rsp.parsed is None:
            print(f"<{rsp.status_code}>: {rsp.content.decode('utf-8')}")
        elif isinstance(rsp.parsed, models.Error):
            print(f"<{rsp.status_code}>: {rsp.parsed.message}")
        else:
            print(f"Created organisation {rsp.parsed.name} with ID {rsp.parsed.id}")


class Boards(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_boards = parser.add_parser("boards", help="Infuse-IoT hardware platforms")
        parser_boards.set_defaults(command_class=cls)

        tool_parser = parser_boards.add_subparsers(title="commands", metavar="<command>", required=True)

        list_parser = tool_parser.add_parser("list", help="List all hardware platforms")
        list_parser.set_defaults(command_fn=cls.list)

        create_parser = tool_parser.add_parser("create", help="Create new hardware platform")
        create_parser.add_argument("--name", "-n", type=str, required=True, help="New board name")
        create_parser.add_argument("--org", "-o", type=str, required=True, help="Organisation ID")
        create_parser.add_argument("--soc", "-s", type=str, required=True, help="Board system on chip")
        create_parser.add_argument("--desc", "-d", type=str, required=True, help="Board description")
        create_parser.set_defaults(command_fn=cls.create)

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def list(self, client: Client):
        board_list = []

        orgs = get_all_organisations.sync(client=client)
        if isinstance(orgs, models.Error) or orgs is None:
            sys.exit(f"Organisation query failed {orgs}")
        for org in orgs:
            boards = get_boards.sync(client=client, organisation_id=org.id)
            if isinstance(boards, models.Error) or boards is None:
                sys.exit(f"Boards query failed {boards}")

            for b in boards:
                board_list.append([b.name, b.id, b.soc, org.name, b.description])

        print(
            tabulate(
                board_list,
                headers=["Name", "ID", "SoC", "Organisation", "Description"],
            )
        )

    def create(self, client: Client):
        rsp = create_board.sync_detailed(
            client=client,
            body=models.NewBoard(
                name=self.args.name,
                description=self.args.desc,
                soc=self.args.soc,
                organisation_id=self.args.org,
            ),
        )

        if rsp.parsed is None:
            print(f"<{rsp.status_code}>: {rsp.content.decode('utf-8')}")
        elif isinstance(rsp.parsed, models.Error):
            print(f"<{rsp.status_code}>: {rsp.parsed.message}")
        else:
            print(f"Created board {rsp.parsed.name} with ID {rsp.parsed.id}")


class Device(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_boards = parser.add_parser("device", help="Infuse-IoT devices")
        parser_boards.set_defaults(command_class=cls)

        tool_parser = parser_boards.add_subparsers(title="commands", metavar="<command>", required=True)

        info_parser = tool_parser.add_parser("info", help="General device information")
        info_parser.set_defaults(command_fn=cls.info)
        info_parser.add_argument("--id", type=str, required=True, help="Infuse-IoT device ID")

        kv_parser = tool_parser.add_parser("kv_state", help="Key-Value device state")
        kv_parser.set_defaults(command_fn=cls.kv_state)
        kv_parser.add_argument("--id", type=str, required=True, help="Infuse-IoT device ID")
        kv_parser.add_argument("--schedules", action="store_true", help="Display task schedules")

        dfu_parser = tool_parser.add_parser("dfu", help="Manage device firmware upgrades")
        dfu_parser.set_defaults(command_fn=cls.dfu)
        dfu_parser.add_argument("--id", type=str, required=True, help="Infuse-IoT device ID")
        dfu_action = dfu_parser.add_mutually_exclusive_group(required=True)
        dfu_action.add_argument("--schedule", type=str, help="Release ID to upgrade to")
        dfu_action.add_argument("--status", action="store_true", help="Check DFU status")

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def info(self, client: Client):
        id_int = int(self.args.id, 0)
        id_str = f"{id_int:016x}"
        info = get_device_by_device_id.sync(client=client, device_id=id_str)
        if info is None:
            sys.exit(f"No device with Infuse-IoT ID {id_str} found")
        elif isinstance(info, models.Error):
            sys.exit(f"<{info.code}>: {info.message}")
        metadata: list[tuple[str, Any]] = []
        if info.metadata:
            metadata = [(f"Metadata.{k}", v) for k, v in info.metadata.additional_properties.items()]

        org = get_organisation_by_id.sync(client=client, id=info.organisation_id)
        board = get_board_by_id.sync(client=client, id=info.board_id)
        state = get_device_state_by_id.sync(client=client, id=info.id)
        route = get_device_last_route_by_device_id.sync(client=client, device_id=id_str)
        app = get_device_application_state_by_device_id.sync(client=client, device_id=id_str)
        logger_states = get_device_logger_states_by_device_id.sync(client=client, device_id=id_str)

        table: list[tuple[str, Any]] = [
            ("UUID", info.id),
            ("MCU ID", info.mcu_id),
            (
                "Organisation",
                f"{info.organisation_id} ({org.name if isinstance(org, models.Organisation) else 'Unknown'})",
            ),
            ("Board", f"{info.board_id} ({board.name if isinstance(board, models.Board) else 'Unknown'})"),
            ("Created", info.created_at),
            ("Updated", info.updated_at),
            *metadata,
        ]
        if isinstance(state, models.DeviceState):
            v = state.application_version

            table += [
                ("~~~State~~~", ""),
                ("Updated", state.updated_at),
            ]
            if state.application_id:
                table += [("Application ID", f"0x{state.application_id:08x}")]
            if v:
                table += [("Version", f"{v.major}.{v.minor}.{v.revision}+{v.build_num:08x}")]
            if isinstance(app, models.DeviceApplicationState):
                table += [("Release ID", app.release_id if app.release_id else "N/A")]
        if isinstance(route, models.UplinkRoute):
            table += [
                ("~~~Latest Route~~~", ""),
                ("Interface", route.interface.upper()),
            ]
            if route.bt_adv:
                table += [("BT Address", f"{route.bt_adv.address} ({route.bt_adv.type_})")]
            if route.udp:
                table += [("IP Address", route.udp.address)]

        if isinstance(logger_states, list) and len(logger_states) > 0:
            logger_names = {
                0: "Onboard",
                1: "Removable",
            }

            def val_or_na(value) -> str:
                if isinstance(value, Unset):
                    return "N/A"
                return str(value)

            for logger in logger_states:
                name = logger_names.get(logger.index, str(logger.index))
                table += [
                    (f"~~~{name} Logger Sync~~~", ""),
                    ("Enabled", logger.download_enabled),
                    ("Last Report Time", val_or_na(logger.last_reported_time)),
                    ("Last Downloaded Time", val_or_na(logger.last_downloaded_time)),
                    ("Reported Block", val_or_na(logger.last_reported_block)),
                    ("Downloaded Block", val_or_na(logger.last_downloaded_block)),
                ]
                if isinstance(logger.last_reported_block, int) and isinstance(logger.last_downloaded_block, int):
                    table += [("Block Lag", logger.last_reported_block - logger.last_downloaded_block)]

        print(tabulate(table))

    def _kv_display(self, table: list[tuple[str, Any]], name_base: str, dictionary: dict):
        for name, value in dictionary.items():
            if isinstance(value, dict):
                self._kv_display(table, f"{name_base}.{name}", value)
            else:
                table.append((f"{name_base}.{name}", value))

    def kv_state(self, client: Client):
        id_int = int(self.args.id, 0)
        id_str = f"{id_int:016x}"

        kv_state = get_device_kv_entries_by_device_id.sync(client=client, device_id=id_str)
        if not isinstance(kv_state, list):
            print(f"Unable to query KV state for {id_str}")
            return

        table: list[tuple[str, Any]] = []
        for element in kv_state:
            key = element.key_name if isinstance(element.key_name, str) else str(element.key_id)

            # Don't display task schedules unless requested
            if key == "TASK_SCHEDULES" and not self.args.schedules:
                continue

            if isinstance(element.data, Unset):
                if element.crc:
                    table.append((key, f"Write-only (CRC: 0x{element.crc:08x})"))
                else:
                    table.append((key, "Not set"))
            else:
                if isinstance(element.decoded, Unset):
                    table.append((key, element.data))
                else:
                    self._kv_display(table, key, element.decoded.additional_properties)

        print(tabulate(table))

    def dfu(self, client: Client):
        id_int = int(self.args.id, 0)
        id_str = f"{id_int:016x}"

        if self.args.schedule:
            body = models.NewDeviceApplicationUpdate(self.args.schedule)
            rsp = create_device_application_update_by_device_id.sync(client=client, device_id=id_str, body=body)

            if rsp is None:
                sys.exit("Create application updates: No response")
            elif isinstance(rsp, models.Error):
                sys.exit(f"<{rsp.code}>: {rsp.message}")
            elif isinstance(rsp, models.DeviceApplicationState):
                print(f"Device already on release {self.args.schedule}")
            elif isinstance(rsp, models.DeviceApplicationUpdate):
                print(f"DFU scheduled with ID {rsp.id}")
            else:
                raise NotImplementedError(f"Unknown response ({rsp})")
        elif self.args.status:
            updates = get_device_application_updates_by_device_id.sync(
                client=client,
                device_id=id_str,
            )
            if updates is None:
                sys.exit("Get application updates: No response")
            elif isinstance(updates, models.Error):
                sys.exit(f"<{updates.code}>: {updates.message}")

            for update in updates:
                print(
                    tabulate(
                        [
                            ["To Release", update.release_id],
                            ["Status", str(update.status)],
                            ["Attempts", str(update.attempt_count)],
                            ["Last Attempt", str(update.last_attempt_at)],
                            ["Completed", str(update.completed_at)],
                        ]
                    )
                )
        else:
            raise NotImplementedError("Unknown DFU subcommand")


class Coap(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_coap = parser.add_parser("coap", help="CoAP file server")
        parser_coap.set_defaults(command_class=cls)

        tool_parser = parser_coap.add_subparsers(title="commands", metavar="<command>", required=True)

        list_parser = tool_parser.add_parser("list", help="List all CoAP files")
        list_parser.set_defaults(command_fn=cls.list)

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def list(self, client: Client):
        files = get_coap_files.sync(client=client)

        if files is None:
            print("Failed to retrieve file list (No response)")
        elif isinstance(files, models.Error):
            print(f"<{files.code}>: {files.message}")
        else:
            sorted_list: list[str] = sorted(files.filenames)
            print("CoAP Files:")
            print("\t" + "\n\t".join(sorted_list))


class Applications(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_coap = parser.add_parser("apps", help="Application release management")
        parser_coap.set_defaults(command_class=cls)

        tool_parser = parser_coap.add_subparsers(title="commands", metavar="<command>", required=True)

        list_parser = tool_parser.add_parser("list", help="List all application releases")
        list_parser.add_argument("--org", "-o", type=str, required=True, help="Organisation ID")
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
        upload_parser.add_argument("--release", "-r", type=ValidRelease, required=True, help="Release to upload")
        upload_parser.set_defaults(command_fn=cls.upload)

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def list(self, client: Client):
        applications = get_applications_by_organisation_id.sync(client=client, id=UUID(self.args.org))

        if not isinstance(applications, list):
            print(f"Failed to retrieve application list {applications}")
            return

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
        if application is None:
            sys.exit("Get application: No response")
        elif isinstance(application, models.Error):
            sys.exit(f"<{application.code}>: {application.message}")
        release = get_release_by_organisation_id_and_application_id_and_release_id.sync(
            client=client, id=UUID(self.args.org), application_id=self.args.app, release_id=self.args.rel
        )
        if release is None:
            sys.exit("Get release: No response")
        elif isinstance(release, models.Error):
            sys.exit(f"<{release.code}>: {release.message}")
        diffs = get_diffs_by_organisation_id_and_application_id_and_release_id.sync(
            client=client, id=UUID(self.args.org), application_id=self.args.app, release_id=self.args.rel
        )
        if diffs is None:
            sys.exit("Get diffs: No response")
        elif isinstance(diffs, models.Error):
            sys.exit(f"<{diffs.code}>: {diffs.message}")

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
        diff_info = []
        for diff in diffs:
            from_release = get_release_by_organisation_id_and_application_id_and_release_id.sync(
                client=client, id=UUID(self.args.org), application_id=self.args.app, release_id=diff.from_release_id
            )
            if not isinstance(from_release, models.ApplicationRelease):
                print(f"Failed to query information about source release {diff.from_release_id}")
                continue
            from_version = from_release.version
            from_version_str = (
                f"{from_version.major}.{from_version.minor}.{from_version.revision}+{from_version.build_num:08x}"
            )
            diff_info.append([from_version_str, diff.file.coap_path, diff.file.len_, diff.file.crc])

        if len(diff_info) > 0:
            print("~~~ Diffs ~~~")
            print(tabulate(diff_info, headers=["From Version", "Path", "Length", "CRC"]))

    def _info_all(self, client: Client):
        releases = get_releases_by_organisation_id_and_application_id.sync(
            client=client, id=UUID(self.args.org), application_id=self.args.app
        )

        if releases is None:
            sys.exit("Failed to retrieve release list (No response)")
        elif isinstance(releases, models.Error):
            sys.exit(f"<{releases.code}>: {releases.message}")

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
        name = release_app_meta["primary"]
        app_id = release_app_meta["id"]
        board_target = release_app_meta["board"]
        version = Version.from_string(release_app_meta["version"])

        if self._org is None:
            orgs = get_all_organisations.sync(client=client)
            if isinstance(orgs, models.Error) or orgs is None:
                sys.exit(f"Organisation query failed {orgs}")
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
            boards = get_boards.sync(client=client, organisation_id=self._org)
            if isinstance(boards, models.Error) or boards is None:
                sys.exit(f"Board query failed {boards}")
            options = [f"{b.name:20s} ({b.id})" for b in boards]

            idx, _val = choose_one("Board", options)
            self._board = boards[idx].id
            self._board_name = boards[idx].name
        else:
            board = get_board_by_id.sync(client=client, id=self._board)
            if not isinstance(org, models.Board):
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
        if len(ota_files) != 1:
            sys.exit(f"Unexpected OTA file search result {ota_files}")

        releases = get_releases_by_organisation_id_and_application_id.sync(
            client=client,
            id=self._org,
            application_id=app_id,
        )
        if not isinstance(releases, list):
            sys.exit(f"Unexpected release query result {releases}")

        cloud_release: None | models.ApplicationRelease = None
        cloud_releases_by_version: dict[Version, models.ApplicationRelease] = {}
        for r in releases:
            v = Version(r.version.major, r.version.minor, r.version.revision, r.version.build_num)
            cloud_releases_by_version[v] = r
            if v == version:
                print(f"Found release for application '0x{app_id:08x} {str(version)}' ({r.id})")
                cloud_release = r

        if cloud_release is None:
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
                if rsp is None:
                    sys.exit("Create release: No response")
                elif isinstance(rsp, models.Error):
                    sys.exit(f"<{rsp.code}>: {rsp.message}")
                else:
                    print(f"Release created with ID '{rsp.id}'")
                    cloud_release = rsp

        # Upload any diffs
        diff_folder = release.dir / "diffs"
        if not diff_folder.exists():
            return
        for path in diff_folder.iterdir():
            if not path.is_file() or path.suffix != ".bin":
                continue
            try:
                diff_from_version = Version.from_string(path.stem)
            except ValueError:
                print(f"Couldn't parse diff files version '{path.stem}'")
                continue
            from_version = cloud_releases_by_version.get(diff_from_version)
            if from_version is None:
                print(f"Version {diff_from_version} doesn't exist on cloud")
                continue

            with open(path, "rb") as f:
                diff_file = File(f, str(path), None)

                create_body = models.CreateReleaseDiffBody(file=diff_file, from_release_id=from_version.id)
                diff_rsp = create_release_diff.sync(
                    client=client, id=self._org, application_id=app_id, release_id=cloud_release.id, body=create_body
                )
                prefix = f"{str(diff_from_version)} -> {str(version)}"
                if isinstance(diff_rsp, models.Error):
                    print(f"{prefix}: <{diff_rsp.code}> {diff_rsp.message}")
                elif isinstance(diff_rsp, models.ApplicationReleaseDiff):
                    print(f"{prefix}: Diff created with ID '{diff_rsp.id}'")
                else:
                    print(f"{prefix}: No response")


class SubCommand(InfuseCommand):
    NAME = "cloud"
    HELP = "Infuse-IoT cloud interaction"
    DESCRIPTION = "Infuse-IoT cloud interaction"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--api-key", type=str, help="Cloud API key to use instead of stored credentials")
        subparser = parser.add_subparsers(title="commands", metavar="<command>", required=True)

        Organisations.add_parser(subparser)
        Boards.add_parser(subparser)
        Device.add_parser(subparser)
        Coap.add_parser(subparser)
        Applications.add_parser(subparser)

    def __init__(self, args):
        self.tool = args.command_class(args)

    def run(self):
        self.tool.run()
