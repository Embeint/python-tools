# Infuse-IoT Python Tools

## Installation

Clone source code from Github and install as a local pip package.

```
git clone git@github.com:Embeint/python-tools.git
pip install -e python-tools
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
infuse --help
usage: infuse [-h] <command> ...

options:
  -h, --help         show this help message and exit

commands:
  <command>
    csv_annotate     Annotate CSV data
    csv_plot         Plot CSV data
    gateway          Connect to a local gateway device
    rpc              Run remote procedure calls on devices
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
