#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth


REALTIME_SUMMARIES = [
    "[Realtime] P1 payment checkout intermittent failure",
    "[Realtime] Sprint risk: CI pipeline blocking release candidate",
    "[Realtime] P1 auth token expiry causing login drops",
    "[Realtime] Customer escalation: delayed export processing",
    "[Realtime] Incident follow-up: webhook signature mismatch",
    "[Realtime] Reliability: duplicate booking race condition",
    "[Realtime] Security patch rollout for comment sanitization",
    "[Realtime] Production readiness checklist gaps",
]

REALTIME_COMMENTS = [
    "Realtime update: triage completed; engineering owner assigned and ETA requested.",
    "Realtime update: issue reproduced in staging; mitigation in progress.",
    "Realtime update: blocker still active due to dependency confirmation pending.",
    "Realtime update: partial fix merged; monitoring production metrics.",
    "Realtime update: customer impact moderate; fallback communicated to support.",
    "Realtime update: release timeline at risk if not resolved by next standup.",
]


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
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }

    def search_issue_keys(self, project_key: str, max_results: int = 100) -> List[str]:
        data = self._request(
            "GET",
            "/rest/api/3/search/jql",
            params={
                "jql": f"project = {project_key} ORDER BY created ASC",
                "fields": "key",
                "maxResults": max_results,
                "startAt": 0,
            },
        )
        issues = data.get("issues", [])
        return [issue.get("key") for issue in issues if issue.get("key")]

    def update_issue(self, issue_key: str, summary: str, description: str) -> None:
        payload = {
            "fields": {
                "summary": summary,
                "description": self.to_adf_paragraph(description),
            }
        }
        self._request("PUT", f"/rest/api/3/issue/{issue_key}", payload=payload)

    def add_comment(self, issue_key: str, comment: str) -> None:
        payload = {"body": self.to_adf_paragraph(comment)}
        self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", payload=payload)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Jira ticket titles/descriptions/comments with realistic realtime content")
    parser.add_argument("--site", required=True, help="Jira site URL, e.g. https://tenant.atlassian.net")
    parser.add_argument("--project-key", default="KAN")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        email = required_env("JIRA_EMAIL")
        token = required_env("JIRA_API_TOKEN")
        client = JiraClient(args.site, email, token)

        issue_keys = client.search_issue_keys(args.project_key, max_results=max(args.limit, 1))[: args.limit]
        if not issue_keys:
            print("No issues found to update.")
            return 0

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        for i, issue_key in enumerate(issue_keys):
            summary = REALTIME_SUMMARIES[i % len(REALTIME_SUMMARIES)]
            description = (
                f"Realtime operational update for {issue_key}.\n"
                f"Current timestamp: {now}.\n"
                "Business impact: delivery timeline and customer experience at risk if unresolved.\n"
                "Action: owner to provide ETA and mitigation status in next standup."
            )
            comment = f"{random.choice(REALTIME_COMMENTS)} Updated at {now}."

            client.update_issue(issue_key, summary=summary, description=description)
            client.add_comment(issue_key, comment=comment)
            print(f"Updated {issue_key}")

        print(f"Done. Updated {len(issue_keys)} issues with realtime title/description/comment content.")
        return 0
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
