#!/usr/bin/env python3

"""Plot CSV data"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import math
from typing import Any

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import ValidFile


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
            bucket = y.iloc[start:end]
            if bucket.empty:
                continue

            bucket = bucket.dropna()
            if bucket.empty:
                indices.add(start)
                continue

            try:
                indices.add(bucket.idxmin())
                indices.add(bucket.idxmax())
            except TypeError:
                indices.add(start)

        sorted_indices = sorted(indices)
        return x.iloc[sorted_indices], y.iloc[sorted_indices]

    def run(self):
        import pandas as pd
        import plotly.graph_objects as go
        from dash import Dash, Input, Output, dcc, html
        from dash.exceptions import PreventUpdate

        relayout_ignore = object()

        def timestamp_for_series(value, series):
            timestamp = pd.Timestamp(value)
            if series.dt.tz is not None and timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize(series.dt.tz)
            elif series.dt.tz is None and timestamp.tzinfo is not None:
                timestamp = timestamp.tz_localize(None)
            return timestamp

        def data_frame_range(data_frame, x_range):
            if x_range is None:
                return data_frame

            start = timestamp_for_series(x_range[0], data_frame["time"])
            end = timestamp_for_series(x_range[1], data_frame["time"])
            return data_frame.loc[(data_frame["time"] >= start) & (data_frame["time"] <= end)].reset_index(drop=True)

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
            df = pd.read_csv(file, parse_dates=["time"])

            start = timestamp_for_series(self.start, df["time"])
            mask = df["time"] >= start
            filtered_df = df.loc[mask].reset_index(drop=True)

            y_columns = [self.field] if self.field else filtered_df.columns.values[1:]
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
