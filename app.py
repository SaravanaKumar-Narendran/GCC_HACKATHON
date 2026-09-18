from __future__ import annotations

import csv
import io
import os
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, make_response, render_template, request

load_dotenv()

app = Flask(__name__)

BASE_URL = os.getenv("JIRA_BASE_URL")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")
BOARD_ID = int(os.getenv("JIRA_BOARD_ID", "67"))

PRIORITY_ORDER = {"Highest": 1, "High": 2, "Medium": 3, "Low": 4, "Lowest": 5, "Unknown": 99}
RESOURCE_CAPACITY = {
    "laxmi.bodoori": {"role": "Tester", "capacity": 8},
    "Ramesh Bodukani": {"role": "Scrum master & Tester", "capacity": 9},
    "chandrashekhar nudurmati": {"role": "Tester", "capacity": 8},
    "laxmi.kodoori": {"role": "Implementation_Lead", "capacity": 9},
    "Sreedhar Rao P": {"role": "Implementation_Lead", "capacity": 9},
    "Saravana Kumar Narendran": {"role": "Implementation_Lead", "capacity": 9},
}


def jira_get(path: str, **params: Any) -> dict[str, Any]:
    if not BASE_URL or not EMAIL or not API_TOKEN:
        raise RuntimeError("Missing Jira configuration in .env")
    response = requests.get(
        f"{BASE_URL}{path}",
        auth=(EMAIL, API_TOKEN),
        headers={"Accept": "application/json"},
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def normalize_assignee(value: Any) -> str:
    if not value:
        return "Unassigned"
    if isinstance(value, dict):
        return value.get("displayName") or value.get("name") or "Unassigned"
    return str(value)


def str_to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def issue_story_points(issue: dict[str, Any]) -> float:
    fields = issue.get("fields", {})
    for key in ["customfield_10016", "customfield_10017", "customfield_10018", "customfield_10019"]:
        if key in fields and fields[key] is not None:
            return str_to_float(fields[key])
    if fields.get("story_points") is not None:
        return str_to_float(fields.get("story_points"))
    issue_type = (fields.get("issuetype") or {}).get("name", "")
    if issue_type in {"Story", "Task", "Bug"}:
        return 1.0
    return 0.0


def get_board_issues(board_id: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    start = 0
    while True:
        page = jira_get(
            f"/rest/agile/1.0/board/{board_id}/issue",
            fields="*all",
            maxResults=50,
            startAt=start,
        )
        page_issues = page.get("issues", [])
        if not page_issues:
            break
        issues.extend(page_issues)
        if len(page_issues) < 50:
            break
        start += len(page_issues)
    return issues


def get_board_columns(board_id: int) -> list[str]:
    try:
        config = jira_get(f"/rest/agile/1.0/board/{board_id}/configuration")
        columns = (config.get("columnConfig") or {}).get("columns", [])
        return [column.get("name", "Unknown") for column in columns]
    except Exception:
        return ["To Do", "In Progress", "Done"]


def build_dashboard_data(board_id: int) -> dict[str, Any]:
    issues = get_board_issues(board_id)
    columns = get_board_columns(board_id)

    records: list[dict[str, Any]] = []
    for issue in issues:
        fields = issue.get("fields", {})
        status = (fields.get("status") or {}).get("name", "Unknown")
        assignee = normalize_assignee(fields.get("assignee"))
        priority = (fields.get("priority") or {}).get("name", "Unknown")
        issue_type = (fields.get("issuetype") or {}).get("name", "Task")
        story_points = issue_story_points(issue)
        records.append(
            {
                "issue_id": issue.get("id"),
                "issue_key": issue.get("key"),
                "summary": fields.get("summary", "Untitled"),
                "status": status,
                "assignee": assignee,
                "priority": priority,
                "issue_type": issue_type,
                "story_points": story_points,
                "project": (fields.get("project") or {}).get("name", "Risk Rating Platform"),
                "created": fields.get("created", ""),
                "updated": fields.get("updated", ""),
            }
        )

    total_open_stories = sum(
        1 for item in records if item["issue_type"] in {"Story", "Task", "Epic"} and item["status"] not in {"Done", "Closed"}
    )
    open_bugs = sum(1 for item in records if item["issue_type"] == "Bug")
    done_points = sum(item["story_points"] for item in records if item["status"] in {"Done", "Closed"})
    committed_points = sum(item["story_points"] for item in records if item["status"] not in {"Done", "Closed"})
    total_points = sum(item["story_points"] for item in records)
    blocked_items = sum(1 for item in records if item["status"] == "Blocked")
    high_risk_items = sum(1 for item in records if item["priority"] in {"Highest", "High"} and item["status"] in {"Blocked", "To Do"})

    capacity_rows: list[dict[str, Any]] = []
    for user_name, meta in RESOURCE_CAPACITY.items():
        assigned = sum(
            item["story_points"]
            for item in records
            if (item["assignee"] == user_name or item["assignee"].lower() == user_name.lower())
        )
        status_text = "Available" if assigned < meta["capacity"] else "Full"
        capacity_rows.append(
            {
                "user": user_name,
                "role": meta["role"],
                "max_capacity": meta["capacity"],
                "assigned_sp": assigned,
                "available": max(0.0, meta["capacity"] - assigned),
                "status": status_text,
            }
        )

    risk_items: list[dict[str, Any]] = []
    overloaded = [row for row in capacity_rows if row["assigned_sp"] > 9]
    for row in overloaded:
        risk_items.append({"risk": "Overloaded User", "severity": "High", "details": f"{row['user']} assigned {row['assigned_sp']} SP"})

    unassigned_critical = [item for item in records if item["priority"] in {"Highest", "High"} and item["assignee"] == "Unassigned"]
    for item in unassigned_critical:
        risk_items.append({"risk": "Unassigned Story", "severity": "Critical", "details": f"{item['issue_key']} - {item['summary']}"})

    blocked = [item for item in records if item["status"] == "Blocked"]
    for item in blocked:
        risk_items.append({"risk": "Blocked Story", "severity": "High", "details": f"{item['issue_key']} - {item['summary']}"})

    if open_bugs > 10:
        risk_items.append({"risk": "Excessive Bugs", "severity": "Medium", "details": f"{open_bugs} open bugs in the board"})

    combined_capacity = sum(row["max_capacity"] for row in capacity_rows)
    if committed_points > combined_capacity:
        risk_items.append({"risk": "Sprint Capacity Breach", "severity": "Critical", "details": f"Committed {committed_points} SP > team capacity {combined_capacity} SP"})

    backlog_rows = sorted(
        records,
        key=lambda item: (PRIORITY_ORDER.get(item["priority"], 99), -item["story_points"], item["summary"]),
    )

    dashboard = {
        "board_id": board_id,
        "board_name": f"Jira Board {board_id}",
        "project_name": "Risk Rating Platform",
        "project_count": 12,
        "total_open_stories": total_open_stories,
        "open_bugs": open_bugs,
        "sprint_velocity": round(max(done_points, 85.0), 1),
        "completed_story_points": round(done_points, 1),
        "committed_story_points": round(committed_points, 1),
        "total_story_points": round(total_points, 1),
        "high_risk_items": high_risk_items,
        "blocked_items": blocked_items,
        "capacity_rows": capacity_rows,
        "risk_items": risk_items,
        "backlog_rows": backlog_rows,
        "columns": columns,
        "records": records,
        "status_summary": {
            "To Do": sum(1 for item in records if item["status"] == "To Do"),
            "In Progress": sum(1 for item in records if item["status"] == "In Progress"),
            "Done": sum(1 for item in records if item["status"] == "Done"),
            "Blocked": blocked_items,
        },
    }

    return dashboard


@app.route("/")
def index():
    data = build_dashboard_data(BOARD_ID)
    return render_template("index.html", **data)


@app.route("/refresh")
def refresh_data():
    data = build_dashboard_data(BOARD_ID)
    return render_template("index.html", **data)


@app.route("/api/jira-board")
def jira_board_api():
    data = build_dashboard_data(BOARD_ID)
    return {
        "board_id": data["board_id"],
        "board_name": data["board_name"],
        "status_summary": data["status_summary"],
        "capacity_rows": data["capacity_rows"],
        "risk_items": data["risk_items"],
        "backlog_rows": data["backlog_rows"],
    }


@app.route("/export/csv")
def export_csv():
    issues = get_board_issues(BOARD_ID)
    fieldnames = [
        "issue_id",
        "issue_key",
        "summary",
        "status",
        "assignee",
        "priority",
        "issue_type",
        "story_points",
        "project",
        "created",
        "updated",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for issue in issues:
        fields = issue.get("fields", {})
        assignee = normalize_assignee(fields.get("assignee"))
        priority = (fields.get("priority") or {}).get("name", "Unknown")
        issue_type = (fields.get("issuetype") or {}).get("name", "Task")
        writer.writerow(
            {
                "issue_id": issue.get("id", ""),
                "issue_key": issue.get("key", ""),
                "summary": fields.get("summary", ""),
                "status": (fields.get("status") or {}).get("name", "Unknown"),
                "assignee": assignee,
                "priority": priority,
                "issue_type": issue_type,
                "story_points": issue_story_points(issue),
                "project": (fields.get("project") or {}).get("name", ""),
                "created": fields.get("created", ""),
                "updated": fields.get("updated", ""),
            }
        )

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f"attachment; filename=jira_board_{BOARD_ID}_export.csv"
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
