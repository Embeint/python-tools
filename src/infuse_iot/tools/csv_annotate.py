#!/usr/bin/env python3

"""Annotate CSV data"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import ValidFile


class SubCommand(InfuseCommand):
    NAME = "csv_annotate"
    HELP = "Annotate CSV data"
    DESCRIPTION = "Annotate CSV data"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--file", "-f", required=True, type=ValidFile)
        parser.add_argument("--default", "-d", type=str, default="N/A", help="Default label")

    def __init__(self, args):
        self.file = args.file
        self.labels = [args.default]
        self.selection = []

    def make_plots(self):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.2)
        for col in self.df.columns.values[1:]:
            fig.add_trace(
                go.Scatter(x=self.df["time"], y=self.df[col], name=col),
                row=2 if col == "labels" else 1,
                col=1,
            )

        return fig

    def run(self):
        import pandas as pd
        from dash import Dash, Input, Output, State, callback, dcc, html

        # Read data, add label column
        self.df = pd.read_csv(self.file, parse_dates=["time"])
        self.df.insert(
            len(self.df.columns),
            "labels",
            [self.labels[0] for _ in range(self.df.shape[0])],
        )

        app = Dash()
        app.layout = html.Div(
            [
                dcc.Graph(id="graph", figure=self.make_plots()),
                html.Button("Label selection", id="button-label-selection", n_clicks=0),
                html.Div(
                    [
                        dcc.Input(id="input-on-submit", type="text"),
                        html.Button("Add new label", id="button-label-add"),
                    ]
                ),
                dcc.RadioItems(id="label-current", options=self.labels),
                html.Button("Remove label", id="button-label-remove"),
            ]
        )

        @callback(
            Output("label-current", "options", True),
            Input("button-label-add", "n_clicks"),
            State("input-on-submit", "value"),
            prevent_initial_call=True,
        )
        def label_add(n_clicks, value):
            self.labels.append(value)
            return self.labels

        @callback(
            Output("label-current", "options", True),
            Input("button-label-remove", "n_clicks"),
            State("label-current", "value"),
            prevent_initial_call=True,
        )
        def label_remove(n_clicks, value):
            try:
                self.labels.remove(value)
            except ValueError:
                pass
            return self.labels

        @callback(Input("graph", "relayoutData"))
        def store_relayout_data(relayoutData):
            if relayoutData.get("autosize", False) or relayoutData.get("xaxis.autorange", False):
                self.selection = [
                    self.df["time"][0],
                    self.df["time"][self.df.shape[0] - 1],
                ]
            else:
                self.selection = [
                    pd.Timestamp(relayoutData["xaxis.range[0]"]),
                    pd.Timestamp(relayoutData["xaxis.range[1]"]),
                ]

        @callback(
            Output("graph", "figure"),
            Input("button-label-selection", "n_clicks"),
            State("label-current", "value"),
            prevent_initial_call=True,
        )
        def label_current_selection(n_clicks, value):
            self.df.loc[
                (self.df["time"] >= self.selection[0]) & (self.df["time"] <= self.selection[1]),
                "labels",
            ] = value
            return self.make_plots()

        app.run_server(debug=True)
