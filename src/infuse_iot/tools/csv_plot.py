#!/usr/bin/env python3

"""Plot CSV data"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import ValidFile


class SubCommand(InfuseCommand):
    NAME = "csv_plot"
    HELP = "Plot CSV data"
    DESCRIPTION = "Plot CSV data"

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

    def __init__(self, args):
        self.files = args.files
        self.field = args.field
        self.start = args.start
        self.group = args.group

    def run(self):
        import pandas as pd
        import plotly.express as px
        import plotly.graph_objects as go
        from dash import Dash, dcc, html

        fig: None | go.Figure = None
        figures: list[dcc.Graph] = []
        if self.group:
            fig = go.Figure()

        for file in self.files:
            df = pd.read_csv(file)

            mask = df["time"] >= self.start
            filtered_df = df.loc[mask]

            y_data = filtered_df[self.field] if self.field else filtered_df.columns.values[1:]
            if self.group:
                assert fig is not None
                fig.add_trace(go.Scatter(x=filtered_df["time"], y=y_data, name=str(file.name), mode="lines"))
            else:
                fig = px.line(
                    filtered_df,
                    x="time",
                    y=y_data,
                    title=str(file),
                )
                figures.append(dcc.Graph(figure=fig))

        app = Dash()
        if self.group:
            figures = [dcc.Graph(figure=fig, style={"height": "90vh"})]
        app.layout = html.Div(figures)

        app.run(debug=True)
