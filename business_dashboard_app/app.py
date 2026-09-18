import os
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

app = Flask(__name__)
BASE_URL = (os.getenv("JIRA_BASE_URL") or "https://saravana-kumar-narendran.atlassian.net").rstrip("/")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")

REPORT_CONFIG = {
    "flow-and-velocity": {
        "title": "Flow and Velocity KPIs",
        "description": "Delivery flow, pace, and throughput across the portfolio.",
    },
    "quality-and-stability": {
        "title": "Quality and Stability KPIs",
        "description": "Defect exposure, blocker concentration, and delivery stability.",
    },
    "predictability-and-dependency": {
        "title": "Predictability and Dependency KPIs",
        "description": "Dependency pressure and predictability signals across projects.",
    },
    "enterprise-aggregation": {
        "title": "Enterprise-Level Aggregation",
        "description": "Portfolio-level roll-up and cross-project view.",
    },
    "governance": {
        "title": "Recommended KPI Governance",
        "description": "Governance standards, escalation readiness, and controls.",
    },
    "summary": {
        "title": "Suggested Dashboard Summary",
        "description": "Executive summary of the current portfolio status.",
    },
}


def jira_get(path: str, **params: Any) -> dict[str, Any]:
    if not EMAIL or not API_TOKEN:
        raise RuntimeError("Missing Jira credentials")
    response = requests.get(
        f"{BASE_URL}{path}",
        auth=(EMAIL, API_TOKEN),
        headers={"Accept": "application/json"},
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def jira_get_with_fallback(candidates: list[str], **params: Any) -> dict[str, Any]:
    last_error: Exception | None = None
    for path in candidates:
        try:
            return jira_get(path, **params)
        except Exception as exc:  # pragma: no cover - defensive fallback
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("No Jira API candidates succeeded")


def get_all_projects() -> list[dict[str, str]]:
    try:
        data = jira_get_with_fallback([
            "/rest/api/3/project/search",
            "/rest/api/2/project",
        ], maxResults=200)
        if isinstance(data, dict) and "values" in data:
            projects = data.get("values", [])
        elif isinstance(data, list):
            projects = data
        else:
            projects = []
        return [
            {"key": project.get("key"), "name": project.get("name")}
            for project in projects
            if project.get("key")
        ]
    except Exception:
        return []


def calculate_risk_status(value: float, thresholds: tuple[float, float, float] = (0.2, 0.5, 0.75)) -> str:
    low, medium, high = thresholds
    if value >= high:
        return "Critical"
    if value >= medium:
        return "High"
    if value >= low:
        return "Medium"
    return "Low"


def get_story_points(issue: dict[str, Any]) -> float:
    fields = issue.get("fields") or {}
    candidates = [
        "customfield_10016",
        "customfield_10028",
        "customfield_10006",
        "customfield_10131",
        "storyPoints",
        "story_points",
    ]
    for key in candidates:
        value = fields.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
        if isinstance(value, dict):
            for nested_key in ("value", "raw"):
                inner = value.get(nested_key)
                if inner is None:
                    continue
                try:
                    return float(inner)
                except (TypeError, ValueError):
                    continue

    for key, value in fields.items():
        if not isinstance(key, str):
            continue
        normalized = key.lower()
        if "story" in normalized and ("point" in normalized or "estimate" in normalized):
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
    return 0.0


def issue_risk_bucket(item: dict[str, Any]) -> str:
    fields = item.get("fields") or {}
    priority = (fields.get("priority") or {}).get("name") or "Unknown"
    status = (fields.get("status") or {}).get("name") or "Unknown"
    score = 0.0
    if priority in {"Highest", "High"}:
        score += 0.5
    elif priority == "Medium":
        score += 0.25
    if status in {"Blocked", "To Do", "In Progress"}:
        score += 0.2
    if status == "Blocked":
        score += 0.2
    return calculate_risk_status(score, (0.2, 0.5, 0.75))


def get_project_severity(project_data: dict[str, Any]) -> str:
    risk = project_data.get("risk", {})
    total = project_data.get("count", 0) or 1
    high_critical = (risk.get("High", 0) + risk.get("Critical", 0)) / total
    if high_critical >= 0.5:
        return "Critical"
    if high_critical >= 0.3:
        return "High"
    if (risk.get("Medium", 0) / total) >= 0.25:
        return "Medium"
    return "Low"


def build_project_risk_pie_data(items: list[dict[str, Any]]) -> dict[str, list[Any]]:
    project_buckets: dict[str, dict[str, Any]] = {}
    total_story_points = 0.0
    for item in items:
        fields = item.get("fields") or {}
        project_name = (fields.get("project") or {}).get("name") or (item.get("project") or {}).get("name") or "Unknown"
        bucket = project_buckets.setdefault(
            project_name,
            {"story_points": 0.0, "count": 0, "risk": {"Low": 0.0, "Medium": 0.0, "High": 0.0, "Critical": 0.0}},
        )
        bucket["count"] += 1
        risk = issue_risk_bucket(item)
        bucket["risk"][risk] = bucket["risk"].get(risk, 0.0) + 1.0
        points = get_story_points(item)
        bucket["story_points"] += points
        total_story_points += points

    project_summary = []
    for project_name, project_data in project_buckets.items():
        share = 0.0
        if total_story_points:
            share = (project_data["story_points"] / total_story_points) * 100
        risk_breakdown = {risk: int(project_data["risk"].get(risk, 0.0)) for risk in ["Low", "Medium", "High", "Critical"]}
        summary = {
            "project": project_name,
            "story_points": round(project_data["story_points"], 1),
            "story_count": project_data["count"],
            "risk_breakdown": risk_breakdown,
            "severity": get_project_severity(project_data),
            "portfolio_share": round(share, 1),
            "risk_mix": "Low: {low} | Medium: {medium} | High: {high} | Critical: {critical}".format(
                low=risk_breakdown["Low"],
                medium=risk_breakdown["Medium"],
                high=risk_breakdown["High"],
                critical=risk_breakdown["Critical"],
            ),
        }
        project_summary.append(summary)

    project_summary = sorted(
        project_summary,
        key=lambda item: (item["story_points"], item["story_count"]),
        reverse=True,
    )[:5]

    split_labels: list[str] = []
    split_values: list[float] = []
    split_counts: list[int] = []

    for project in project_summary:
        for risk in ["Low", "Medium", "High", "Critical"]:
            risk_count = project["risk_breakdown"].get(risk, 0)
            if risk_count <= 0:
                continue
            split_labels.append(f"{project['project']} - {risk}")
            split_values.append(round(project["story_points"] * (risk_count / max(project["story_count"], 1)), 1))
            split_counts.append(risk_count)

    by_project_labels = [project["project"] for project in project_summary]
    by_project_values = [project["story_points"] for project in project_summary]
    by_project_counts = [project["story_count"] for project in project_summary]

    return {
        "project_summary": project_summary,
        "story_points_labels": by_project_labels,
        "story_points_values": by_project_values,
        "story_count_labels": by_project_labels,
        "story_count_values": by_project_counts,
        "risk_split_labels": split_labels,
        "risk_split_values": split_values,
        "risk_split_counts": split_counts,
    }


def build_issue_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items[:20]:
        key = item.get("key")
        project = item.get("project", {}).get("name") or "Unknown"
        priority = (item.get("priority") or {}).get("name") or "Unknown"
        status = (item.get("status") or {}).get("name") or "Unknown"
        risk_value = 0.0
        if priority in {"Highest", "High"}:
            risk_value += 0.5
        if status in {"Blocked", "To Do", "In Progress"}:
            risk_value += 0.2
        if status == "Blocked":
            risk_value += 0.2
        rows.append(
            {
                "issue_key": key,
                "issue_link": f"{BASE_URL}/browse/{key}" if key else "#",
                "project": project,
                "status": status,
                "priority": priority,
                "risk": calculate_risk_status(risk_value, (0.2, 0.5, 0.75)),
            }
        )
    return rows


def fetch_issues_for_projects(selected_projects: list[str] | None = None) -> list[dict[str, Any]]:
    projects = get_all_projects()
    if selected_projects:
        project_names = {p for p in selected_projects if p}
    else:
        project_names = {project["key"] for project in projects}

    if not project_names:
        return []

    project_names_sorted = sorted(project_names)
    query_variants = [
        "project in (" + ", ".join(project_names_sorted) + ") ORDER BY updated DESC",
        "project in (\"" + "\", \"".join(project_names_sorted) + "\") ORDER BY updated DESC",
        "projectKey in (" + ", ".join(project_names_sorted) + ") ORDER BY updated DESC",
    ]

    issues: list[dict[str, Any]] = []
    last_error: Exception | None = None

    for endpoint in [
        "/rest/api/3/search",
        "/rest/api/2/search",
        "/rest/api/3/search/jql",
    ]:
        for jql in query_variants:
            try:
                start_at = 0
                while True:
                    page = jira_get(
                        endpoint,
                        jql=jql,
                        fields="summary,project,status,priority,issuetype,updated,customfield_10016,customfield_10028,customfield_10006,customfield_10131",
                        maxResults=100,
                        startAt=start_at,
                    )
                    page_issues = page.get("issues", [])
                    if not page_issues:
                        return issues
                    issues.extend(page_issues)
                    if len(page_issues) < 100:
                        return issues
                    start_at += len(page_issues)
            except Exception as exc:  # pragma: no cover - defensive fallback
                last_error = exc
                issues = []
                continue

    if last_error is not None:
        return []
    return issues


def build_report_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)

    def fields_of(item: dict[str, Any]) -> dict[str, Any]:
        return item.get("fields") or {}

    open_items = sum(
        1
        for item in items
        if (fields_of(item).get("status") or {}).get("name") not in {"Done", "Closed"}
    )
    blocked_items = sum(
        1
        for item in items
        if (fields_of(item).get("status") or {}).get("name") == "Blocked"
    )
    open_bugs = sum(
        1
        for item in items
        if (fields_of(item).get("issuetype") or {}).get("name") == "Bug"
    )
    high_risk = sum(
        1
        for item in items
        if ((fields_of(item).get("priority") or {}).get("name") in {"High", "Highest"})
        and ((fields_of(item).get("status") or {}).get("name") in {"Blocked", "To Do", "In Progress"})
    )
    risk_score = min(100, round((high_risk * 18 + blocked_items * 12 + open_bugs * 10) / max(1, total) * 10, 1))
    return {
        "total": total,
        "open": open_items,
        "blocked": blocked_items,
        "bugs": open_bugs,
        "high_risk": high_risk,
        "risk_score": risk_score,
        "risk_status": calculate_risk_status(risk_score / 100.0),
    }


def build_report_data(selected_projects: list[str] | None = None) -> dict[str, Any]:
    issues = fetch_issues_for_projects(selected_projects)
    metrics = build_report_metrics(issues)
    rows = build_issue_rows(issues)
    pie_data = build_project_risk_pie_data(issues)
    report_data = {
        "selected_projects": selected_projects or [],
        "all_projects": [project["name"] for project in get_all_projects()],
        "metrics": metrics,
        "issue_rows": rows,
        "project_options": get_all_projects(),
        "project_risk_chart": pie_data,
    }
    return report_data


def get_report_sections() -> list[tuple[str, str]]:
    return [
        ("summary", "Suggested Dashboard Summary"),
        ("flow-and-velocity", "Flow and Velocity KPIs"),
        ("quality-and-stability", "Quality and Stability KPIs"),
        ("predictability-and-dependency", "Predictability and Dependency KPIs"),
        ("enterprise-aggregation", "Enterprise-Level Aggregation"),
        ("governance", "Recommended KPI Governance"),
    ]


def report_cards_for(section: str, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    if section == "flow-and-velocity":
        return [
            {"label": "Open Items", "value": metrics["open"], "status": calculate_risk_status(metrics["open"] / max(metrics["total"], 1))},
            {"label": "Blocked Items", "value": metrics["blocked"], "status": calculate_risk_status(metrics["blocked"] / max(metrics["total"], 1))},
            {"label": "Portfolio Risk", "value": f"{metrics['risk_score']}%", "status": calculate_risk_status(metrics["risk_score"] / 100.0)},
        ]
    if section == "quality-and-stability":
        return [
            {"label": "Open Bugs", "value": metrics["bugs"], "status": calculate_risk_status(metrics["bugs"] / max(metrics["total"], 1))},
            {"label": "High Risk Items", "value": metrics["high_risk"], "status": calculate_risk_status(metrics["high_risk"] / max(metrics["total"], 1))},
            {"label": "Risk Status", "value": metrics["risk_status"], "status": metrics["risk_status"]},
        ]
    if section == "predictability-and-dependency":
        return [
            {"label": "Projects in Scope", "value": len({issue.get("fields", {}).get("project", {}).get("name") for issue in fetch_issues_for_projects(request.args.getlist("project")) if issue.get("fields", {}).get("project", {}).get("name")}), "status": "Low"},
            {"label": "Risk Status", "value": metrics["risk_status"], "status": metrics["risk_status"]},
            {"label": "Exposure", "value": metrics["high_risk"], "status": calculate_risk_status(metrics["high_risk"] / max(metrics["total"], 1))},
        ]
    if section == "enterprise-aggregation":
        return [
            {"label": "Total Issues", "value": metrics["total"], "status": "Low"},
            {"label": "Open Issues", "value": metrics["open"], "status": calculate_risk_status(metrics["open"] / max(metrics["total"], 1))},
            {"label": "Portfolio Health", "value": f"{100 - metrics['risk_score']}%", "status": calculate_risk_status((100 - metrics["risk_score"]) / 100.0)},
        ]
    if section == "governance":
        return [
            {"label": "Governance Score", "value": "A" if metrics["blocked"] <= 2 and metrics["bugs"] <= 3 else "B" if metrics["blocked"] <= 5 and metrics["bugs"] <= 8 else "C", "status": calculate_risk_status((metrics["blocked"] + metrics["bugs"]) / max(metrics["total"], 1))},
            {"label": "Escalation Ready", "value": "Yes" if metrics["blocked"] <= 3 else "Review", "status": "Low" if metrics["blocked"] <= 3 else "High"},
            {"label": "Risk Status", "value": metrics["risk_status"], "status": metrics["risk_status"]},
        ]
    return [
        {"label": "Portfolio Risk", "value": f"{metrics['risk_score']}%", "status": calculate_risk_status(metrics["risk_score"] / 100.0)},
        {"label": "Open Bugs", "value": metrics["bugs"], "status": calculate_risk_status(metrics["bugs"] / max(metrics["total"], 1))},
        {"label": "Risk Status", "value": metrics["risk_status"], "status": metrics["risk_status"]},
    ]


@app.route("/")
def index():
    selected_projects = request.args.getlist("project")
    data = build_report_data(selected_projects or None)
    return render_template("index.html", data=data, selected_projects=selected_projects, report_sections=get_report_sections())


@app.route("/report/<section>")
def report(section: str):
    selected_projects = request.args.getlist("project")
    data = build_report_data(selected_projects or None)
    if section not in REPORT_CONFIG:
        section = "summary"
    report_title = REPORT_CONFIG[section]["title"]
    cards = report_cards_for(section, data["metrics"])
    rows = data["issue_rows"]
    return render_template(
        "report.html",
        report_title=report_title,
        description=REPORT_CONFIG[section]["description"],
        section=section,
        report_sections=get_report_sections(),
        cards=cards,
        rows=rows,
        selected_projects=selected_projects,
        project_options=data["project_options"],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
