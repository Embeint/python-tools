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
        parser.add_argument("--file", "-f", required=True, type=ValidFile)
        parser.add_argument("--start", type=str, default="2024-01-01", help="Display data after")

    def __init__(self, args):
        self.file = args.file
        self.start = args.start

    def run(self):
        import pandas as pd
        import plotly.express as px
        from dash import Dash, dcc, html

        df = pd.read_csv(self.file)

        mask = df["time"] >= self.start
        filtered_df = df.loc[mask]

        fig = px.line(
            filtered_df,
            x="time",
            y=filtered_df.columns.values[1:],
            title=str(self.file),
        )

        app = Dash()
        app.layout = html.Div([dcc.Graph(figure=fig)])

        app.run(debug=True)
