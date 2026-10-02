from types import SimpleNamespace

import pytest
from dash import Dash

from infuse_iot.commands import InfuseCommand
from infuse_iot.tools.csv_annotate import SubCommand as Annotate
from infuse_iot.tools.csv_plot import SubCommand as Plot


@pytest.mark.parametrize("tool", ["plot", "plot_grouped", "annotate"])
def test_csv_tools_build_served_layout(tmp_path, monkeypatch, tool):
    path = tmp_path / "readings.csv"
    path.write_text("time,value\n2026-01-01T00:00:00,1\n2026-01-01T00:00:01,2\n", encoding="utf-8")
    apps = []
    monkeypatch.setattr(Dash, "run", lambda app, **_kwargs: apps.append(app))
    command: InfuseCommand
    if tool.startswith("plot"):
        command = Plot(
            SimpleNamespace(
                files=[path], field=None, start="2024-01-01", group=tool == "plot_grouped", max_points=20000
            )
        )
    else:
        command = Annotate(SimpleNamespace(file=path, default="N/A"))
    command.run()
    assert len(apps) == 1
    client = apps[0].server.test_client()
    assert client.get("/").status_code == 200
    response = client.get("/_dash-layout")
    assert response.status_code == 200
    assert b'"Graph"' in response.data
    dependencies = client.get("/_dash-dependencies")
    assert dependencies.status_code == 200
    graph = response.get_json()["props"]["children"][0]["props"]
    assert graph["figure"]["data"][0]["y"] == [1, 2]

    if tool.startswith("plot"):
        result = client.post(
            "/_dash-update-component",
            json={
                "output": f"{graph['id']}.figure",
                "outputs": {"id": graph["id"], "property": "figure"},
                "inputs": [
                    {
                        "id": graph["id"],
                        "property": "relayoutData",
                        "value": {"xaxis.range[0]": "2026-01-01T00:00:01", "xaxis.range[1]": "2026-01-01T00:00:02"},
                    }
                ],
                "state": [],
                "changedPropIds": [f"{graph['id']}.relayoutData"],
            },
        )
        assert result.status_code == 200
        assert result.get_json()["response"][graph["id"]]["figure"]["data"][0]["y"] == [2]
    else:
        no_output = next(item["output"] for item in dependencies.get_json() if item["no_output"])
        for value in (None, {"yaxis.range[0]": 0}):
            result = client.post(
                "/_dash-update-component",
                json={
                    "output": no_output,
                    "outputs": [],
                    "inputs": [{"id": "graph", "property": "relayoutData", "value": value}],
                    "state": [],
                    "changedPropIds": ["graph.relayoutData"],
                },
            )
            assert result.status_code == 204
        result = client.post(
            "/_dash-update-component",
            json={
                "output": "graph.figure",
                "outputs": {"id": "graph", "property": "figure"},
                "inputs": [{"id": "button-label-selection", "property": "n_clicks", "value": 1}],
                "state": [{"id": "label-current", "property": "value", "value": "walking"}],
                "changedPropIds": ["button-label-selection.n_clicks"],
            },
        )
        assert result.status_code == 200
        assert result.get_json()["response"]["graph"]["figure"]["data"][-1]["y"] == ["walking", "walking"]


def test_annotate_rejects_empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("time,value\n", encoding="utf-8")
    command = Annotate(SimpleNamespace(file=path, default="N/A"))
    with pytest.raises(ValueError, match="no readings"):
        command.run()
