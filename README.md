# Infuse-IoT Python Tools

## Installation

Install from PyPI with ``pip`` or ``pipx``:

```
pip install infuse-iot
```

## Register Autocomplete

To register for autocompletion (tab complete).

```
autoload -Uz compinit
compinit
eval "$(register-python-argcomplete infuse)"
```

## Usage

```
> infuse --help
usage: infuse [-h] [--version] <command> ...

options:
  -h, --help         show this help message and exit
  --version          show program's version number and exit

commands:
  <command>
    bt_log           Connect to remote Bluetooth device serial logs
    cloud            Infuse-IoT cloud interaction
    credentials      Manage Infuse-IoT credentials
    csv_annotate     Annotate CSV data
    csv_plot         Plot CSV data
    data_logger_sync
                     Synchronise data logger state from remote devices
    gateway          Connect to a local gateway device
    localhost        Run a local server for TDF viewing
    native_bt        Native Bluetooth gateway
    ota_upgrade      Automatically OTA upgrade observed devices
    provision        Provision device on Infuse Cloud
    rpc              Run remote procedure calls on devices
    rpc_cloud        Manage remote procedure calls through Infuse-IoT cloud
    serial_throughput
                     Test serial throughput to local gateway
    tdf_csv          Save received TDFs in CSV files
    tdf_list         Display received TDFs in a list
```

## Credential Storage

Under linux, the preferred credential storage provider for the python ``keyring``
package is provided by ``gnome-keyring``. The available backends can be listed with
``keyring --list-backends``.

```
sudo apt install gnome-keyring
```

### WSL Issues

Under WSL, they keyring has been observed to consistently raise
``secretstorage.exceptions.PromptDismissedException: Prompt dismissed``.
This can be resolved by adding the following to ``~/.bashrc`` and reloading
the terminal.
```
dbus-update-activation-environment --all > /dev/null 2>&1
```
