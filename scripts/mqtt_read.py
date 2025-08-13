#!/usr/bin/env python3

"""Read device packets from the Infuse-IoT Cloud MQTT broker"""

__author__ = "Jace Galvin"
__copyright__ = "Copyright 2025, Embeint Inc"

import argparse
import base64
import enum
import json
import sys

import paho.mqtt.client as mqtt
import tabulate

from infuse_iot.common import InfuseType
from infuse_iot.epacket.interface import ID as InterfaceID


class OutputFormat(enum.Enum):
    JSON = "json"
    TABLE = "table"


class ConnectionError(Exception):
    pass


def get_enum_name(enum, value):
    try:
        return enum(value).name
    except ValueError:
        return None


def get_payload_type(payload_type):
    return get_enum_name(InfuseType, payload_type)


def print_metadata_table(data):
    metadata_table = [
        ["Device ID", data["deviceId"]],
        ["Packet ID", data["packetId"]],
        ["Timestamp", data["time"]],
        ["Payload Type", get_payload_type(data["payloadType"])],
        ["Sequence", data["sequence"]],
        ["Key ID", base64.b64decode(data["keyId"]).hex()],
    ]

    print("[Metadata]")
    print(tabulate.tabulate(metadata_table, tablefmt="grid"))


def get_interface_type(interface_type):
    return get_enum_name(InterfaceID, interface_type)


def print_route_table(route):
    route_table = [
        ["Type", get_interface_type(route["type"])],
    ]

    if "sequence" in route["interfaceData"]:
        route_table.append(["Sequence", route["interfaceData"]["sequence"]])
    if "entropy" in route["interfaceData"]:
        route_table.append(["Entropy", route["interfaceData"]["entropy"]])

    if "udp" in route:
        route_table.append(["UDP Address", route["udp"]["address"]])
        route_table.append(["Arrival Time", route["udp"]["time"]])

    print("[Route]")
    print(tabulate.tabulate(route_table, tablefmt="grid"))


def flatten_tdf(tdf, parent_key=""):
    items = []
    for k, v in tdf.items():
        new_key = f"{parent_key}->{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_tdf(v, new_key).items())
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v)))  # Convert lists to JSON string
        else:
            items.append((new_key, v))
    return dict(items)


def print_tdfs_table(tdfs, packet_time):
    table = []
    for tdf in tdfs:
        tdf_id = tdf["id"]
        tdf_name = tdf["name"]

        tdf_time = tdf.get("time", packet_time)

        for key, value in flatten_tdf(tdf["fields"]).items():
            table.append([tdf_id, tdf_name, key, value, tdf_time])

    print("[TDFs]")
    print(tabulate.tabulate(table, headers=["TDF ID", "Name", "Field", "Value", "Time"], tablefmt="grid"))


def print_table(data):
    print_metadata_table(data)

    route = data["route"]
    print_route_table(route)

    if "tdf" in data:
        print_tdfs_table(data["tdf"], data["time"])

    print()


def on_message(client, userdata, message):
    payload = message.payload.decode("utf-8")
    output = userdata["output"]
    if output == OutputFormat.JSON:
        print(payload)
    elif output == OutputFormat.TABLE:
        data = json.loads(payload)
        print_table(data)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        raise ConnectionError(reason_code)

    print("Connected to broker.")

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    topic = userdata["topic"]
    client.subscribe(topic)


def main(host, port, username, password, organisation, device, output):
    topic = f"organisation/{organisation}"
    if device:
        topic += f"/device/{device}"
    else:
        topic += "/#"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata={"topic": topic, "output": output})
    print(f"Connecting to {host}:{port} as {username}...")
    client.username_pw_set(username, password)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(host, port, 60)
        client.loop_forever(retry_first_connection=False)
    except KeyboardInterrupt:
        print("Exiting...")
        client.disconnect()
    except ConnectionError as e:
        sys.exit(f"Connection failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read device packets from the Infuse-IoT Cloud MQTT broker",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--broker",
        "-b",
        type=str,
        default="mqtt.dev.infuse-iot.com",
        help="MQTT broker address",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=1883,
        help="MQTT broker port",
    )
    parser.add_argument(
        "--username",
        "-u",
        type=str,
        required=True,
        help="MQTT username",
    )
    parser.add_argument("--password", "-P", type=str, required=True, help="MQTT password")
    parser.add_argument(
        "--organisation",
        "--org",
        "-O",
        type=str,
        required=True,
        help="ID of organisation to read packets from",
    )
    parser.add_argument(
        "--device",
        "-d",
        type=lambda x: int(x, 0),
        required=False,
        help="Infuse ID of device to read packets from (in hex)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=OutputFormat,
        default=OutputFormat.JSON,
        choices=list(OutputFormat),
        help="Output format",
    )

    args = parser.parse_args()

    main(args.broker, args.port, args.username, args.password, args.organisation, args.device, args.output)
