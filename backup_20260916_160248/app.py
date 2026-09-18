from __future__ import annotations

import os
from collections import OrderedDict

from flask import Flask, render_template
import pandas as pd
import plotly.express as px


app = Flask(__name__)

DEFAULT_JQL = (
    'project = "Team 61" AND status in ("To Do", "In Progress", "Done", "Blocked") '
    'ORDER BY updated DESC'
)


@app.context_processor
def inject_common_data():
    return {"jql_query": DEFAULT_JQL}


def build_metric_frame() -> pd.DataFrame:
    data = OrderedDict(
        [
            ("Status", ["To Do", "In Progress", "Done", "Blocked"]),
            ("Count", [26, 18, 39, 7]),
        ]
    )
    return pd.DataFrame(data)


def build_traffic_light(df: pd.DataFrame) -> dict:
    blocked = int(df.loc[df["Status"] == "Blocked", "Count"].sum())
    if blocked >= 10:
        return {"color": "red", "status": "Critical", "message": "Blocked items are high; action required."}
    if blocked >= 5:
        return {"color": "yellow", "status": "Warning", "message": "A few items are blocked and should be reviewed."}
    return {"color": "green", "status": "Healthy", "message": "No major blockers for the current reporting window."}


def build_chart_payloads() -> dict:
    df = build_metric_frame()
    bar_chart = px.bar(df, x="Status", y="Count", title="Issue Status by Count")
    pie_chart = px.pie(df, names="Status", values="Count", title="Issue Distribution")

    return {
        "bar_chart": bar_chart.to_html(full_html=False, include_plotlyjs="cdn"),
        "pie_chart": pie_chart.to_html(full_html=False, include_plotlyjs="cdn"),
        "traffic_light": build_traffic_light(df),
        "total_issues": int(df["Count"].sum()),
        "resolved_or_done": int(df.loc[df["Status"].isin(["Done"]), "Count"].sum()),
        "blocked_items": int(df.loc[df["Status"] == "Blocked", "Count"].sum()),
    }


@app.route("/")
def index():
    chart_data = build_chart_payloads()
    return render_template("index.html", **chart_data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
