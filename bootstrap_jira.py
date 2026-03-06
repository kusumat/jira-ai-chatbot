#!/usr/bin/env python3
"""
Bootstrap Jira resources for chatbot demo:
- (Optional) create project
- Create 20 sample issues in a given project
- Add comments to each issue

Note:
- Creating Jira users usually requires Atlassian Org Admin APIs and may not be enabled
  for normal Jira project admin tokens. This script provides a best-effort method if
  org-level details are supplied, otherwise skips user creation.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth


ISSUE_BLUEPRINTS = [
    ("Story", "Implement login workflow", "As a user, I want to log in securely."),
    ("Task", "Set up CI pipeline", "Configure build, lint, and test jobs."),
    ("Bug", "Fix null pointer in payment flow", "App crashes when payment token is missing."),
    ("Story", "Add profile page", "As a user, I want to view and edit my profile."),
    ("Task", "Create API health endpoint", "Expose health endpoint for monitoring."),
    ("Bug", "Resolve timezone issue in reports", "Dates are shifted for PST users."),
    ("Story", "Build notifications center", "As a user, I want to view all notifications."),
    ("Task", "Improve SQL indexes", "Optimize slow queries on ride history."),
    ("Bug", "Fix duplicate booking requests", "Race condition causes duplicate rides."),
    ("Story", "Add password reset", "As a user, I can reset forgotten password."),
    ("Task", "Document onboarding", "Create setup docs for new developers."),
    ("Bug", "Patch XSS in comments", "Sanitize user-provided comment text."),
    ("Story", "Create admin dashboard", "As an admin, I can view KPI summaries."),
    ("Task", "Add Redis caching", "Cache frequent lookups for low latency."),
    ("Bug", "Fix failed OTP retries", "Retry policy blocks valid attempts."),
    ("Story", "Introduce role permissions", "As admin, I can assign roles."),
    ("Task", "Add structured logging", "Capture request IDs and trace IDs."),
    ("Bug", "Fix webhook signature check", "Valid signatures fail in edge cases."),
    ("Story", "Add export CSV", "As a manager, I can export monthly data."),
    ("Task", "Prepare release checklist", "Create release gate and rollback steps."),
]

COMMENT_TEMPLATES = [
    "Investigating root cause; update in next standup.",
    "Shared workaround in team channel; proper fix pending review.",
    "Validated in staging; awaiting QA sign-off.",
    "Need product clarification on acceptance criteria.",
    "Potential blocker identified: dependency team response pending.",
]


@dataclass
class JiraConfig:
    site: str
    email: str
    api_token: str


class JiraClient:
    def __init__(self, config: JiraConfig, timeout: int = 30) -> None:
        self.site = config.site.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config.email, config.api_token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.site}{path}"
        resp = self.session.request(method, url, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} failed ({resp.status_code}): {resp.text}")
        if not resp.text:
            return {}
        return resp.json()

    def create_project(self, key: str, name: str, lead_account_id: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "key": key,
            "name": name,
            "projectTypeKey": "software",
            "projectTemplateKey": "com.pyxis.greenhopper.jira:gh-kanban-template",
            "description": "Project created by bootstrap script for AI chatbot demo",
        }
        if lead_account_id:
            payload["leadAccountId"] = lead_account_id
        return self._request("POST", "/rest/api/3/project", payload)

    def get_project(self, key: str) -> Dict[str, Any]:
        return self._request("GET", f"/rest/api/3/project/{key}")

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

    def create_issue(self, project_key: str, summary: str, description: str, issue_type: str) -> Dict[str, Any]:
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": self.to_adf_paragraph(description),
                "issuetype": {"name": issue_type},
            }
        }
        return self._request("POST", "/rest/api/3/issue", payload)

    def get_project_issue_types(self, project_key: str) -> List[str]:
        data = self._request(
            "GET",
            f"/rest/api/3/issue/createmeta?projectKeys={project_key}&expand=projects.issuetypes",
        )
        projects = data.get("projects", [])
        if not projects:
            return []
        issue_types = projects[0].get("issuetypes", [])
        return [item.get("name", "") for item in issue_types if item.get("name")]

    def add_comment(self, issue_key: str, comment: str) -> Dict[str, Any]:
        payload = {"body": self.to_adf_paragraph(comment)}
        return self._request("POST", f"/rest/api/3/issue/{issue_key}/comment", payload)

    def create_user_org_admin_best_effort(
        self,
        email: str,
        display_name: str,
        org_id: Optional[str],
        admin_api_key: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Best-effort Atlassian Org Admin user invitation.
        Requires org-level permissions and an admin API key.
        Endpoint availability may vary by Atlassian plan/tenant settings.
        """
        if not org_id or not admin_api_key:
            return None

        url = f"https://api.atlassian.com/admin/v1/orgs/{org_id}/users"
        headers = {
            "Authorization": f"Bearer {admin_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "email": email,
            "display_name": display_name,
            "products": ["jira-software"],
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"Create user failed ({resp.status_code}): {resp.text}")
        return resp.json() if resp.text else {"status": "invited"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Jira project with 20 sample tickets and comments")
    parser.add_argument("--site", required=True, help="Jira site URL, e.g. https://your-domain.atlassian.net")
    parser.add_argument("--project-key", default="KAN", help="Project key (default: KAN)")
    parser.add_argument("--project-name", default="Kanban AI Demo", help="Project name")
    parser.add_argument("--create-project", action="store_true", help="Create project if not present")
    parser.add_argument("--ticket-count", type=int, default=20, help="Number of tickets to create")
    parser.add_argument("--create-user-email", help="Optional: org-level user invite email")
    parser.add_argument("--create-user-name", default="Jira Chatbot Integration User", help="Optional: display name for invited user")
    parser.add_argument("--sleep-ms", type=int, default=100, help="Delay between creates to reduce API bursts")
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def seed_issues(client: JiraClient, project_key: str, ticket_count: int, sleep_ms: int) -> List[str]:
    created: List[str] = []
    available_issue_types = client.get_project_issue_types(project_key)
    available_lut = {name.lower(): name for name in available_issue_types}

    if not available_issue_types:
        raise RuntimeError(f"No issue types available for project {project_key}")

    preferred_fallbacks = ["Task", "Story", "Bug"]
    fallback_issue_type = None
    for candidate in preferred_fallbacks:
        if candidate.lower() in available_lut:
            fallback_issue_type = available_lut[candidate.lower()]
            break
    if not fallback_issue_type:
        fallback_issue_type = available_issue_types[0]

    for i in range(ticket_count):
        issue_type, base_summary, base_description = ISSUE_BLUEPRINTS[i % len(ISSUE_BLUEPRINTS)]
        chosen_issue_type = available_lut.get(issue_type.lower(), fallback_issue_type)
        summary = f"[{project_key}] {base_summary} #{i + 1}"
        description = f"{base_description}\n\nGenerated for chatbot integration testing."

        issue = client.create_issue(project_key, summary, description, chosen_issue_type)
        issue_key = issue.get("key")
        if not issue_key:
            raise RuntimeError(f"Issue created without key: {json.dumps(issue)}")

        comment_count = random.choice([1, 2])
        for _ in range(comment_count):
            comment = random.choice(COMMENT_TEMPLATES)
            client.add_comment(issue_key, comment)

        created.append(issue_key)
        print(f"Created issue: {issue_key}")
        time.sleep(max(sleep_ms, 0) / 1000.0)

    return created


def main() -> int:
    args = parse_args()

    try:
        email = required_env("JIRA_EMAIL")
        api_token = required_env("JIRA_API_TOKEN")

        config = JiraConfig(site=args.site, email=email, api_token=api_token)
        client = JiraClient(config)

        if args.create_user_email:
            org_id = os.getenv("ATLASSIAN_ORG_ID")
            admin_api_key = os.getenv("ATLASSIAN_ADMIN_API_KEY")
            try:
                result = client.create_user_org_admin_best_effort(
                    email=args.create_user_email,
                    display_name=args.create_user_name,
                    org_id=org_id,
                    admin_api_key=admin_api_key,
                )
                if result is None:
                    print("Skipped user creation: set ATLASSIAN_ORG_ID and ATLASSIAN_ADMIN_API_KEY for org-level invite.")
                else:
                    print(f"User creation result: {json.dumps(result)}")
            except Exception as exc:
                print(f"User creation failed (continuing): {exc}")

        if args.create_project:
            try:
                project = client.create_project(args.project_key, args.project_name)
                print(f"Created project: {project.get('key', args.project_key)}")
            except Exception as exc:
                print(f"Project creation failed or already exists ({exc}); verifying project access...")
                client.get_project(args.project_key)
                print(f"Project exists and is accessible: {args.project_key}")
        else:
            client.get_project(args.project_key)
            print(f"Using existing project: {args.project_key}")

        created = seed_issues(client, args.project_key, args.ticket_count, args.sleep_ms)
        print(f"Done. Created {len(created)} issues.")
        print("Issue keys:", ", ".join(created))
        return 0

    except Exception as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
