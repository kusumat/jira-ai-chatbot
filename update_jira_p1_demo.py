#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth


class JiraClient:
    def __init__(self, site: str, email: str, token: str, timeout: int = 30) -> None:
        self.site = site.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(email, token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.site}{path}"
        resp = self.session.request(method, url, params=params, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} failed ({resp.status_code}): {resp.text}")
        if not resp.text:
            return {}
        return resp.json()

    @staticmethod
    def to_adf_paragraph(text: str) -> Dict[str, Any]:
        return {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }

    def list_priorities(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/rest/api/3/priority")
        if isinstance(data, list):
            return data
        return []

    def search_issues(self, project_key: str, max_results: int) -> List[Dict[str, Any]]:
        data = self._request(
            "GET",
            "/rest/api/3/search/jql",
            params={
                "jql": f"project = {project_key} ORDER BY created ASC",
                "fields": "key,summary,priority,assignee,reporter,status",
                "maxResults": max_results,
                "startAt": 0,
            },
        )
        return data.get("issues", [])

    def update_issue_fields(self, issue_key: str, fields: Dict[str, Any]) -> None:
        self._request("PUT", f"/rest/api/3/issue/{issue_key}", payload={"fields": fields})

    def add_comment(self, issue_key: str, text: str) -> None:
        self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/comment",
            payload={"body": self.to_adf_paragraph(text)},
        )


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def choose_p1_priority(priorities: List[Dict[str, Any]]) -> Optional[str]:
    if not priorities:
        return None

    names = [str(item.get("name") or "") for item in priorities]
    preferred = ["P1", "Priority 1", "Highest", "Critical", "Blocker"]

    for target in preferred:
        for name in names:
            if name.lower() == target.lower():
                return name

    for name in names:
        lowered = name.lower()
        if any(token in lowered for token in ["highest", "critical", "blocker", "p1"]):
            return name

    return names[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mark demo tickets as P1 and assign owners for chatbot demo")
    parser.add_argument("--site", required=True)
    parser.add_argument("--project-key", default="KAN")
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        email = required_env("JIRA_EMAIL")
        token = required_env("JIRA_API_TOKEN")
        client = JiraClient(args.site, email, token)

        priorities = client.list_priorities()
        p1_name = choose_p1_priority(priorities)
        if not p1_name:
            raise RuntimeError("No priorities found in Jira tenant")

        issues = client.search_issues(args.project_key, max_results=max(args.limit, 1))
        issues = issues[: args.limit]
        if not issues:
            print("No issues found for demo update.")
            return 0

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        for issue in issues:
            issue_key = issue.get("key")
            fields = issue.get("fields", {})
            reporter = fields.get("reporter") or {}
            assignee = fields.get("assignee") or {}

            update_fields: Dict[str, Any] = {"priority": {"name": p1_name}}

            if not assignee and reporter.get("accountId"):
                update_fields["assignee"] = {"accountId": reporter["accountId"]}

            client.update_issue_fields(issue_key, update_fields)

            owner_name = (assignee.get("displayName") if assignee else None) or reporter.get("displayName") or "assigned owner"
            client.add_comment(
                issue_key,
                f"Realtime P1 update ({now}): issue escalated to {p1_name}. Current owner: {owner_name}."
            )
            print(f"Updated {issue_key} -> priority={p1_name}")

        print(f"Done. Updated {len(issues)} issues to {p1_name} for P1 demo queries.")
        return 0
    except Exception as exc:
        print(f"P1 demo update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
