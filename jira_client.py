import argparse
import json
import os
from typing import Any

import requests
from dotenv import load_dotenv


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=30
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._get("/rest/api/3/myself")

    def get_backlog(self, board_id: int, page_size: int = 50) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        start_at = 0

        while True:
            page = self._get(
                f"/rest/agile/1.0/board/{board_id}/backlog",
                startAt=start_at,
                maxResults=page_size,
            )
            page_issues = page.get("issues", [])
            issues.extend(page_issues)

            if len(page_issues) == 0 or len(issues) >= page.get("total", len(issues)):
                return issues
            start_at += len(page_issues)


def create_client() -> JiraClient:
    load_dotenv()
    required = {
        "JIRA_BASE_URL": os.getenv("JIRA_BASE_URL"),
        "JIRA_EMAIL": os.getenv("JIRA_EMAIL"),
        "JIRA_API_TOKEN": os.getenv("JIRA_API_TOKEN"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    return JiraClient(
        base_url=required["JIRA_BASE_URL"],
        email=required["JIRA_EMAIL"],
        api_token=required["JIRA_API_TOKEN"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read Jira Cloud health and backlog data.")
    parser.add_argument("--board-id", type=int, default=int(os.getenv("JIRA_BOARD_ID", "34")))
    parser.add_argument("--health-only", action="store_true")
    args = parser.parse_args()

    client = create_client()
    user = client.health()
    print(f"Connected to Jira as {user.get('displayName', user.get('emailAddress', 'unknown user'))}")

    if not args.health_only:
        backlog = client.get_backlog(args.board_id)
        print(json.dumps(backlog, indent=2))


if __name__ == "__main__":
    main()