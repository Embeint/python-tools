"""Register the local MCP server with desktop MCP hosts."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import add_server_port_parser

CLIENTS = {"claude-desktop": "Claude Desktop", "claude-code": "Claude Code", "cursor": "Cursor"}
INSTALL = 'pip install "infuse-iot[mcp]"'
# Not secrets, but select the credential store; hosts do not start servers from a login shell.
PASSED_ENVIRONMENT = ("PYTHON_KEYRING_BACKEND", "KEYRING_PROPERTY_FILE_PATH")


def config_path(client: str, platform: str = sys.platform, home: Path | None = None) -> Path:
    """The user-level JSON configuration of a desktop host that has one."""
    home = home or Path.home()
    if client == "cursor":
        return home / ".cursor" / "mcp.json"
    if platform == "darwin":
        directory = home / "Library" / "Application Support"
    elif platform == "win32":
        directory = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    else:
        directory = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return directory / "Claude" / "claude_desktop_config.json"


def update_config(path: Path, name: str, entry: dict | None) -> bool:
    """Add or replace `name`, or remove it if `entry` is `None`, keeping the rest of the file.

    The previous file is kept as `<name>.bak`. Returns whether the file changed.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    try:
        config = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        sys.exit(f"{path} is not valid JSON; fix or move it, then run this again")
    if not isinstance(config, dict) or not isinstance(config.setdefault("mcpServers", {}), dict):
        sys.exit(f"{path} does not hold an mcpServers object; fix or move it, then run this again")
    servers = config["mcpServers"]
    if entry is None:
        if name not in servers:
            return False
        del servers[name]
    elif servers.get(name) == entry:
        return False
    else:
        servers[name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    if text:
        path.with_name(path.name + ".bak").write_text(text, encoding="utf-8")
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return True


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--client",
            action="append",
            choices=sorted(CLIENTS),
            help="Host to configure; repeat for several (default: every host found)",
        )
        parser.add_argument("--name", default="infuse", help="Server name in the host (default infuse)")
        parser.add_argument("--allow-writes", action="store_true", help="Let the host queue device actions and updates")
        parser.add_argument(
            "--start-gateway",
            choices=["native_bt", "serial", "none"],
            default="native_bt",
            help="Gateway the server starts when none is running (default native_bt)",
        )
        parser.add_argument("--gateway-serial", help="Serial port for --start-gateway serial")
        parser.add_argument("--gateway-baud", type=int, default=115200, help="Baudrate for --start-gateway serial")
        parser.add_argument(
            "--scan-seconds", type=float, default=20.0, help="Scan period before reaching devices (default 20)"
        )
        parser.add_argument("--print", action="store_true", help="Print the server configuration, changing nothing")
        parser.add_argument("--remove", action="store_true", help="Remove the server from the hosts")
        add_server_port_parser(parser)

    def __init__(self, args):
        self.args = args

    def command(self) -> list[str]:
        """The `infuse mcp` command of this installation, by absolute path, since hosts do not use the shell PATH."""
        executable = shutil.which("infuse", path=str(Path(sys.executable).parent))
        command = [executable] if executable else [sys.executable, "-m", "infuse_iot"]
        command += [
            "mcp",
            "--server-port",
            str(self.args.server_sock[1]),
            "--scan-seconds",
            f"{self.args.scan_seconds:g}",
        ]
        if self.args.start_gateway != "none":
            command += ["--start-gateway", self.args.start_gateway]
        if self.args.start_gateway == "serial":
            command += ["--gateway-serial", self.args.gateway_serial, "--gateway-baud", str(self.args.gateway_baud)]
        if self.args.allow_writes:
            command.append("--allow-writes")
        return command

    def entry(self) -> dict:
        command = self.command()
        entry: dict = {"command": command[0], "args": command[1:]}
        environment = {key: os.environ[key] for key in PASSED_ENVIRONMENT if key in os.environ}
        if environment:
            entry["env"] = environment
        return entry

    @staticmethod
    def found() -> list[str]:
        found = [client for client in ("claude-desktop", "cursor") if config_path(client).parent.is_dir()]
        if shutil.which("claude"):
            found.append("claude-code")
        return found

    def run(self):
        if (self.args.start_gateway == "serial") != (self.args.gateway_serial is not None):
            sys.exit("--gateway-serial is needed for, and only used with, --start-gateway serial")
        if not 0 <= self.args.scan_seconds <= 60:
            sys.exit("--scan-seconds must be in 0..60")
        entry = self.entry()
        if self.args.print:
            print(json.dumps({"mcpServers": {self.args.name: entry}}, indent=2))
            return
        if not self.args.remove:
            # A registered server that cannot start only fails inside the host, without this explanation.
            if sys.version_info < (3, 11):
                sys.exit(
                    f"MCP needs Python 3.11 or newer, but this is Python {sys.version_info[0]}.{sys.version_info[1]}"
                )
            if importlib.util.find_spec("mcp") is None:
                sys.exit(f"MCP needs the optional extra: {INSTALL}")
        clients = self.args.client or self.found()
        if not clients:
            sys.exit("No Claude Desktop, Claude Code or Cursor installation found; use --client or --print")
        for client in dict.fromkeys(clients):
            if client == "claude-code":
                self._claude_code(entry)
                continue
            path = config_path(client)
            changed = update_config(path, self.args.name, None if self.args.remove else entry)
            action = "Removed from" if self.args.remove else "Registered with"
            if changed:
                print(f"{action} {CLIENTS[client]}: {path}; restart {CLIENTS[client]} to apply")
            else:
                print(f"{CLIENTS[client]} is already up to date: {path}")
        if not self.args.remove and self.args.start_gateway == "native_bt" and sys.platform == "darwin":
            print(
                "The host starts native_bt when needed, so macOS asks it for Bluetooth access on first use. "
                "If the host cannot use Bluetooth, run `infuse native_bt` in a terminal; the server uses it instead."
            )

    def _claude_code(self, entry: dict) -> None:
        claude = shutil.which("claude")
        if claude is None:
            sys.exit("Claude Code's `claude` command is not on PATH")
        # `add-json` fails for an existing name, so it is replaced
        subprocess.run([claude, "mcp", "remove", "--scope", "user", self.args.name], capture_output=True, check=False)
        if self.args.remove:
            print(f"Removed from Claude Code (user scope): {self.args.name}")
            return
        specification = json.dumps({"type": "stdio", **entry})
        result = subprocess.run(
            [claude, "mcp", "add-json", "--scope", "user", self.args.name, specification],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            sys.exit(f"`claude mcp add-json` failed: {(result.stderr or result.stdout).strip()}")
        print(f"Registered with Claude Code (user scope): {self.args.name}; start a new session to apply")
