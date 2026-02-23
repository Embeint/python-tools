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

    def __init__(self, args):
        self.files = args.files
        self.field = args.field
        self.start = args.start

    def run(self):
        import pandas as pd
        import plotly.express as px
        from dash import Dash, dcc, html

        figures = []
        for file in self.files:
            df = pd.read_csv(file)

            mask = df["time"] >= self.start
            filtered_df = df.loc[mask]

            if self.field:
                y_data = filtered_df[self.field]
            else:
                y_data = filtered_df.columns.values[1:]

            fig = px.line(
                filtered_df,
                x="time",
                y=y_data,
                title=str(file),
            )
            figures.append(dcc.Graph(figure=fig))

        app = Dash()
        app.layout = html.Div(figures)

        app.run(debug=True)
