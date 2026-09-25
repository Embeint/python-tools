#!/usr/bin/env python3

"""Dataset Helper scripts"""

__author__ = "Aeyohan Furtado"
__copyright__ = "Copyright 2026, Embeint Holdings Pty Ltd"


import argparse
import json
import sys

import polars

from infuse_iot.commands import InfuseCommand
from infuse_iot.time import InfuseTime
from infuse_iot.util.argparse import ValidFile, ValidOutputFile, add_subparsers_with_list, print_subcommands_if_missing


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        subcommands = add_subparsers_with_list(
            parser,
            dest="_dataset_command",
            title="dataset commands",
        )

        Extract.add_parser(subcommands)

    def __init__(self, args):
        self.args = args
        self.tool = args.command_class(args) if hasattr(args, "command_class") else None

    def run(self):
        """Run cloud sub-command"""
        if print_subcommands_if_missing(self.args):
            return
        assert self.tool is not None
        self.tool.run()


class Extract(SubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_extract = parser.add_parser("extract", help="Extract labelled data")

        parser_extract.add_argument(
            "--annotation", "-a", required=True, type=ValidFile, help="Annotation CSV file (time, timestamp, event)"
        )
        parser_extract.add_argument(
            "--data", "-d", required=True, type=ValidFile, help="Data CSV file to extract labelled windows from"
        )
        parser_extract.add_argument(
            "--output", "-o", required=True, type=ValidOutputFile, help="Output CSV file"
        )
        parser_extract.add_argument(
            "--labels", "-l", type=ValidFile, required=True, help="JSON file containing an ordered list of labels"
        )

        mode_subcommands = parser_extract.add_subparsers(
            dest="mode", required=True, title="extraction modes", metavar="<mode>"
        )

        window_parser = mode_subcommands.add_parser("window", help="Labels mark the start and end of an event window")
        window_parser.set_defaults(command_class=cls)
        window_parser.add_argument(
            "--start-suffix", default="start", help="Suffix appended to a label for the start of a window"
        )
        window_parser.add_argument(
            "--end-suffix", default="end", help="Suffix appended to a label for the end of a window"
        )

        instant_parser = mode_subcommands.add_parser("instant", help="Labels mark the exact moment of an event")
        instant_parser.set_defaults(command_class=cls)
        instant_parser.add_argument("--before", type=float, default=0.5, help="Seconds before the event to include")
        instant_parser.add_argument("--after", type=float, default=0.5, help="Seconds after the event to include")

    def __init__(self, args):
        self.args = args

    def _windows(self, annotation: polars.DataFrame, labels: list[str]):
        """Return a list of (label, start_unix, end_unix) windows"""
        windows: list[tuple[str, float, float]] = []
        label_indices: dict[str, int] = {}

        if self.args.mode == "window":
            # Labels contain start and end suffixes for their corresponding windows.
            start_suffix = self.args.start_suffix
            end_suffix = self.args.end_suffix
            start_labels = {}
            end_labels = {}
            base_labels = []

            # Determine and match start and end labels from reference labels.
            for label in labels:
                start = label.removesuffix(start_suffix)
                end = label.removesuffix(end_suffix)
                base = label.removesuffix(start_suffix).removesuffix(end_suffix)
                if base == label:
                    # This is not a start/end label
                    continue
                if start != label:
                    start_labels[base] = label
                    label_indices[base] = len(label_indices)
                if end != label:
                    end_labels[base] = label
                base_labels.append(base)

            # Remove duplicates from base_labels
            base_labels = list(dict.fromkeys(base_labels))

            # Ensure labels are matched correctly
            for base in base_labels[:]:
                if base not in start_labels or base not in end_labels:
                    print(f"Warning: {base} is missing start or end labels")
                    sys.exit()

            if not base_labels:
                print("Warning: No start/end labels found")

            # Search for and extract start and end windows from the annotation
            for base in base_labels:
                start_event = start_labels[base]
                end_event = end_labels[base]
                starts = annotation.filter(polars.col("event") == f"b'{start_event}'").sort("unix_time")["unix_time"]
                ends = annotation.filter(polars.col("event") == f"b'{end_event}'").sort("unix_time")["unix_time"]

                if len(starts) != len(ends):
                    print(f"Warning: {base} has {len(starts)} start events but "
                          f"{len(ends)} end events. Check annotation pairs are correct.")
                    sys.exit()

                for start, end in zip(starts, ends, strict=False):
                    windows.append((base, float(start), float(end)))
        else:
            # Search for events and add the before and after padding time.
            for label in labels:
                label_indices[label] = len(label_indices)
                events = annotation.filter(polars.col("event") == f"b'{label}'").sort("unix_time")["unix_time"]
                for event_time in events:
                    windows.append((label, float(event_time) - self.args.before, float(event_time) + self.args.after))

        return label_indices, windows

    def run(self):
        def _parse_time_column(df: polars.DataFrame, column: str = "time") -> polars.Series:
            """Parse a CSV time column (unix seconds or UTC timestamp string) into unix seconds (float)"""
            try:
                return df[column].cast(polars.Float64)
            except polars.exceptions.InvalidOperationError:
                pass

            return (
                df[column]
                .str.to_datetime(time_unit="us", time_zone="UTC", strict=False)
                .dt.timestamp(time_unit="us")
                .cast(polars.Float64)
                / 1_000_000
            )

        with open(self.args.labels, encoding="utf-8") as f:
            labels: list[str] = json.load(f)

        annotation = polars.read_csv(self.args.annotation)
        gps_to_unix = InfuseTime.unix_time_from_gps_seconds
        annotation = annotation.with_columns(
            annotation["timestamp"].map_elements(gps_to_unix, return_dtype=polars.Int64).alias("unix_time")
        )

        label_indices, windows = self._windows(annotation, labels)
        if not windows:
            print("No matching windows found")
            return

        data = polars.read_csv(self.args.data)
        data = data.with_columns(_parse_time_column(data).alias("unix_time"))

        extracted: list[polars.DataFrame] = []
        for window_count, (label, start, end) in enumerate(windows):
            clean_label = label.strip()
            subset = data.filter((polars.col("unix_time") >= start) & (polars.col("unix_time") <= end))
            subset = subset.with_columns(
                polars.lit(clean_label).alias("label"),
                polars.lit(label_indices[label]).alias("label_id"),
                polars.lit(window_count).alias("window_id"),
            )
            extracted.append(subset)

        result = polars.concat(extracted).drop("unix_time")
        result.write_csv(self.args.output)
        print(f"Extracted {len(result)} rows across {len(windows)} windows to {self.args.output}")
