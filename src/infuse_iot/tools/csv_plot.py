#!/usr/bin/env python3

"""Plot CSV data"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import logging
import math
import time
from typing import Any
from zoneinfo import ZoneInfo

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import ValidFile

logger = logging.getLogger("infuse.csv_plot")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--files",
            "-f",
            required=True,
            type=ValidFile,
            nargs="+",
        )
        parser.add_argument("--start", type=str, default="2024-01-01", help="Display data after")
        parser.add_argument("--field", type=str, help="Single column to plot")
        parser.add_argument("--group", action="store_true", help="Group all lines onto a single plot")
        parser.add_argument(
            "--max-points",
            type=int,
            default=20_000,
            help="Maximum points to render per trace in the current view after min/max downsampling, or 0 to disable",
        )

    def __init__(self, args):
        self.files = args.files
        self.field = args.field
        self.start = args.start
        self.group = args.group
        self.max_points = args.max_points

    @staticmethod
    def _downsample_xy(x, y, max_points):
        if max_points <= 0 or len(y) <= max_points:
            return x, y

        bucket_count = max((max_points - 2) // 2, 1)
        bucket_size = math.ceil((len(y) - 2) / bucket_count)
        indices = {0, len(y) - 1}

        for start in range(1, len(y) - 1, bucket_size):
            end = min(start + bucket_size, len(y) - 1)
            bucket = y.slice(start, end - start)
            if bucket.is_empty():
                continue

            if bucket.null_count() == len(bucket):
                indices.add(start)
                continue

            try:
                indices.add(start + bucket.arg_min())
                indices.add(start + bucket.arg_max())
            except TypeError:
                indices.add(start)

        sorted_indices = sorted(indices)
        return x.gather(sorted_indices), y.gather(sorted_indices)

    def run(self):
        import plotly.graph_objects as go
        import polars as pl
        from dash import Dash, Input, Output, dcc, html
        from dash.exceptions import PreventUpdate
        from dateutil.parser import parse as parse_datetime

        relayout_ignore = object()

        def timestamp_for_dtype(value, dtype):
            timestamp = parse_datetime(value)
            time_zone = getattr(dtype, "time_zone", None)
            if time_zone is not None and timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=ZoneInfo(time_zone))
            elif time_zone is not None:
                timestamp = timestamp.astimezone(ZoneInfo(time_zone))
            elif timestamp.tzinfo is not None:
                timestamp = timestamp.replace(tzinfo=None)
            return timestamp

        def data_frame_range(data_frame, x_range):
            if x_range is None:
                return data_frame

            time_dtype = data_frame.schema["time"]
            start = timestamp_for_dtype(x_range[0], time_dtype)
            end = timestamp_for_dtype(x_range[1], time_dtype)
            return data_frame.filter((pl.col("time") >= start) & (pl.col("time") <= end))

        def relayout_range(relayout_data):
            if not relayout_data:
                return relayout_ignore

            if relayout_data.get("autosize", False) or relayout_data.get("xaxis.autorange", False):
                return None

            if "xaxis.range" in relayout_data:
                return relayout_data["xaxis.range"]

            if "xaxis.range[0]" in relayout_data and "xaxis.range[1]" in relayout_data:
                return [relayout_data["xaxis.range[0]"], relayout_data["xaxis.range[1]"]]

            return relayout_ignore

        def make_figure(datasets, title, x_range=None):
            figure = go.Figure()
            for data_frame, y_columns, trace_prefix in datasets:
                ranged_df = data_frame_range(data_frame, x_range)
                for column in y_columns:
                    x_data, y_data = self._downsample_xy(ranged_df["time"], ranged_df[column], self.max_points)
                    trace_name = f"{trace_prefix}: {column}" if trace_prefix else column
                    figure.add_trace(
                        go.Scattergl(
                            x=x_data,
                            y=y_data,
                            name=trace_name,
                            mode="lines",
                        )
                    )

            figure.update_layout(title=title, uirevision=title)
            if x_range is not None:
                figure.update_xaxes(range=x_range)
            return figure

        graphs: list[Any] = []
        graph_configs: list[Any] = []
        grouped_datasets: list[Any] = []

        for file in self.files:
            try:
                file_size = file.stat().st_size
                file_size_str = f" ({file_size / (1024 * 1024):.1f} MiB)"
            except OSError:
                file_size_str = ""

            load_start = time.perf_counter()
            logger.info("Loading CSV %s%s", file, file_size_str)
            lazy_df = pl.scan_csv(file, try_parse_dates=True)
            if self.field:
                lazy_df = lazy_df.select(["time", self.field])
            start = timestamp_for_dtype(self.start, lazy_df.collect_schema()["time"])
            filtered_df = lazy_df.filter(pl.col("time") >= start).collect()
            load_elapsed = time.perf_counter() - load_start
            logger.info(
                "Loaded CSV %s from %s: %d rows, %d columns in %.3f s",
                file,
                self.start,
                len(filtered_df),
                len(filtered_df.columns),
                load_elapsed,
            )

            y_columns = [self.field] if self.field else filtered_df.columns[1:]
            if self.group:
                grouped_datasets.append((filtered_df, y_columns, file.name))
            else:
                graph_id = f"csv-plot-{len(graphs)}"
                datasets = [(filtered_df, y_columns, "")]
                title = str(file)
                graphs.append(dcc.Graph(id=graph_id, figure=make_figure(datasets, title)))
                graph_configs.append((graph_id, datasets, title))

        app = Dash()
        if self.group:
            graphs = [
                dcc.Graph(
                    id="csv-plot-grouped",
                    figure=make_figure(grouped_datasets, "CSV data"),
                    style={"height": "90vh"},
                )
            ]
        app.layout = html.Div(graphs)

        if self.group:

            @app.callback(
                Output("csv-plot-grouped", "figure"),
                Input("csv-plot-grouped", "relayoutData"),
                prevent_initial_call=True,
            )
            def update_grouped_figure(relayout_data):
                x_range = relayout_range(relayout_data)
                if x_range is relayout_ignore:
                    raise PreventUpdate
                return make_figure(grouped_datasets, "CSV data", x_range)

        else:

            def register_update_callback(graph_id, datasets, title):
                @app.callback(Output(graph_id, "figure"), Input(graph_id, "relayoutData"), prevent_initial_call=True)
                def update_figure(relayout_data):
                    x_range = relayout_range(relayout_data)
                    if x_range is relayout_ignore:
                        raise PreventUpdate
                    return make_figure(datasets, title, x_range)

            for graph_id, datasets, title in graph_configs:
                register_update_callback(graph_id, datasets, title)

        app.run(debug=False)
