#!/usr/bin/env python3

"""Plot CSV data"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

from infuse_iot.argparse import ValidFile
from infuse_iot.commands import InfuseCommand

class csv_plot(InfuseCommand):
    HELP = "Plot CSV data"
    DESCRIPTION = "Plot CSV data"

    def add_parser(cls, parser):
        parser.add_argument('--file', '-f', required=True, type=ValidFile)

    def __init__(self, args):
        self.file = args.file

    def run(self):
        from dash import Dash, dcc, html
        import pandas as pd
        import plotly.express as px

        df = pd.read_csv(self.file)
        fig = px.line(df, x = 'time', y = df.columns.values[1:], title=str(self.file))

        app = Dash()
        app.layout = html.Div([
            dcc.Graph(figure=fig)
        ])

        app.run_server(debug=True)
