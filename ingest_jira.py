#!/usr/bin/env python3
"""
Ingest Jira issues, comments, and changelog for chatbot retrieval.
Supports full and incremental sync.

Outputs each sync as JSONL snapshot files:
- issues.jsonl
- comments.jsonl
- changelog.jsonl
- manifest.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth


SAFETY_WINDOW_MINUTES = 2
DEFAULT_FIELDS = [
    "summary",
    "description",
    "status",
    "assignee",
    "reporter",
    "priority",
    "labels",
    "issuetype",
    "project",
    "created",
    "updated",
    "resolution",
    "resolutiondate",
    "parent",
]


@dataclass
class JiraConfig:
    site: str
    email: str
    api_token: str
    timeout: int = 45
    max_retries: int = 4
    sleep_ms: int = 80


class JiraClient:
    def __init__(self, config: JiraConfig) -> None:
        self.site = config.site.rstrip("/")
        self.timeout = config.timeout
        self.max_retries = config.max_retries
        self.sleep_ms = max(config.sleep_ms, 0)
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config.email, config.api_token)
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
        last_error: Optional[str] = None

        for attempt in range(self.max_retries + 1):
            response = self.session.request(
                method,
                url,
                params=params,
                json=payload,
                timeout=self.timeout,
            )
            status = response.status_code

            if status < 400:
                if self.sleep_ms:
                    time.sleep(self.sleep_ms / 1000.0)
                if not response.text:
                    return {}
                return response.json()

            is_retryable = status in (429, 500, 502, 503, 504)
            if is_retryable and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = int(retry_after)
                else:
                    delay = min(2 ** attempt, 16)
                time.sleep(delay)
                last_error = f"HTTP {status}: {response.text}"
                continue

            raise RuntimeError(f"{method} {path} failed ({status}): {response.text}")

        raise RuntimeError(last_error or f"{method} {path} failed")

    def search_issues(
        self,
        jql: str,
        start_at: int,
        max_results: int,
        fields: Iterable[str],
    ) -> Dict[str, Any]:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields),
        }
        return self._request("GET", "/rest/api/3/search/jql", params=params)

    def get_issue_comments(self, issue_key: str, start_at: int, max_results: int) -> Dict[str, Any]:
        params = {
            "startAt": start_at,
            "maxResults": max_results,
            "orderBy": "created",
        }
        return self._request("GET", f"/rest/api/3/issue/{issue_key}/comment", params=params)

    def get_issue_changelog(self, issue_key: str, start_at: int, max_results: int) -> Dict[str, Any]:
        params = {
            "startAt": start_at,
            "maxResults": max_results,
        }
        return self._request("GET", f"/rest/api/3/issue/{issue_key}/changelog", params=params)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jira full/incremental ingestion for chatbot RAG")
    parser.add_argument("--site", required=True, help="Jira site URL, e.g. https://tenant.atlassian.net")
    parser.add_argument("--projects", required=True, help="Comma-separated project keys, e.g. KAN,ENG")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    parser.add_argument("--since", help="Optional ISO datetime for incremental lower bound, e.g. 2026-02-27T10:00:00Z")
    parser.add_argument("--jql-extra", default="", help="Optional extra JQL condition, e.g. status != Done")
    parser.add_argument("--output-dir", default="/Users/kusumathatavarthi/jira_ai_chatbot_artifacts/data")
    parser.add_argument("--state-file", default="")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--comment-page-size", type=int, default=100)
    parser.add_argument("--changelog-page-size", type=int, default=100)
    parser.add_argument("--max-issues", type=int, default=0, help="Optional cap for a sync run (0 = unlimited)")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--sleep-ms", type=int, default=80)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso8601(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_jira_datetime(dt: datetime) -> str:
    local = dt.astimezone(timezone.utc)
    return local.strftime("%Y/%m/%d %H:%M")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_checkpoint(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_checkpoint(path: Path, data: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def append_jsonl(path: Path, item: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def build_jql(projects: List[str], mode: str, since_dt: Optional[datetime], jql_extra: str) -> str:
    projects_quoted = ",".join(projects)
    clauses = [f"project in ({projects_quoted})"]

    if mode == "incremental" and since_dt is not None:
        clauses.append(f'updated >= "{to_jira_datetime(since_dt)}"')

    extra = jql_extra.strip()
    if extra:
        clauses.append(f"({extra})")

    return " AND ".join(clauses) + " ORDER BY updated ASC"


def iter_issue_comments(client: JiraClient, issue_key: str, page_size: int) -> Iterable[Dict[str, Any]]:
    start_at = 0
    while True:
        data = client.get_issue_comments(issue_key, start_at=start_at, max_results=page_size)
        items = data.get("comments", [])
        for comment in items:
            yield comment

        total = data.get("total", 0)
        start_at += len(items)
        if start_at >= total or not items:
            break


def iter_issue_changelog(client: JiraClient, issue_key: str, page_size: int) -> Iterable[Dict[str, Any]]:
    start_at = 0
    while True:
        data = client.get_issue_changelog(issue_key, start_at=start_at, max_results=page_size)
        items = data.get("values", [])
        for history in items:
            yield history

        total = data.get("total", 0)
        start_at += len(items)
        if start_at >= total or not items:
            break


def normalize_issue_record(issue: Dict[str, Any], sync_id: str) -> Dict[str, Any]:
    fields = issue.get("fields", {})
    return {
        "sync_id": sync_id,
        "id": issue.get("id"),
        "key": issue.get("key"),
        "fields": fields,
    }


def normalize_comment_record(issue_key: str, issue_id: str, comment: Dict[str, Any], sync_id: str) -> Dict[str, Any]:
    return {
        "sync_id": sync_id,
        "issue_id": issue_id,
        "issue_key": issue_key,
        "comment_id": comment.get("id"),
        "comment": comment,
    }


def normalize_changelog_record(issue_key: str, issue_id: str, history: Dict[str, Any], sync_id: str) -> Dict[str, Any]:
    return {
        "sync_id": sync_id,
        "issue_id": issue_id,
        "issue_key": issue_key,
        "history_id": history.get("id"),
        "history": history,
    }


def determine_since_dt(args: argparse.Namespace, checkpoint: Dict[str, Any]) -> Tuple[Optional[datetime], str]:
    if args.mode == "full":
        return None, "full-mode"

    if args.since:
        return parse_iso8601(args.since), "cli-since"

    last_success = checkpoint.get("last_successful_sync_utc")
    if last_success:
        dt = parse_iso8601(last_success) - timedelta(minutes=SAFETY_WINDOW_MINUTES)
        return dt, "checkpoint"

    return None, "no-checkpoint"


def run_ingestion(args: argparse.Namespace) -> Dict[str, Any]:
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    state_file = Path(args.state_file) if args.state_file else output_dir / "checkpoint.json"
    checkpoint = load_checkpoint(state_file)

    email = required_env("JIRA_EMAIL")
    token = required_env("JIRA_API_TOKEN")

    config = JiraConfig(
        site=args.site,
        email=email,
        api_token=token,
        timeout=args.timeout,
        max_retries=args.retries,
        sleep_ms=args.sleep_ms,
    )
    client = JiraClient(config)

    projects = [segment.strip().upper() for segment in args.projects.split(",") if segment.strip()]
    if not projects:
        raise RuntimeError("No valid project keys supplied in --projects")

    since_dt, since_source = determine_since_dt(args, checkpoint)
    jql = build_jql(projects, args.mode, since_dt, args.jql_extra)

    sync_started = utc_now()
    sync_id = sync_started.strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = output_dir / "snapshots" / sync_id
    ensure_dir(snapshot_dir)

    issues_path = snapshot_dir / "issues.jsonl"
    comments_path = snapshot_dir / "comments.jsonl"
    changelog_path = snapshot_dir / "changelog.jsonl"

    # Ensure all output files exist even if no data is written
    for p in [issues_path, comments_path, changelog_path]:
        p.touch()

    start_at = 0
    total_issues_seen = 0
    total_comments_seen = 0
    total_histories_seen = 0
    updated_max: Optional[datetime] = None

    while True:
        page = client.search_issues(
            jql=jql,
            start_at=start_at,
            max_results=args.page_size,
            fields=DEFAULT_FIELDS,
        )
        issues = page.get("issues", [])

        if not issues:
            break

        for issue in issues:
            if args.max_issues > 0 and total_issues_seen >= args.max_issues:
                break

            issue_record = normalize_issue_record(issue, sync_id=sync_id)
            append_jsonl(issues_path, issue_record)
            total_issues_seen += 1

            issue_key = issue.get("key", "")
            issue_id = issue.get("id", "")

            updated_raw = issue.get("fields", {}).get("updated")
            if updated_raw:
                try:
                    dt = parse_iso8601(updated_raw)
                    if updated_max is None or dt > updated_max:
                        updated_max = dt
                except Exception:
                    pass

            for comment in iter_issue_comments(client, issue_key=issue_key, page_size=args.comment_page_size):
                append_jsonl(
                    comments_path,
                    normalize_comment_record(issue_key=issue_key, issue_id=issue_id, comment=comment, sync_id=sync_id),
                )
                total_comments_seen += 1

            for history in iter_issue_changelog(client, issue_key=issue_key, page_size=args.changelog_page_size):
                append_jsonl(
                    changelog_path,
                    normalize_changelog_record(issue_key=issue_key, issue_id=issue_id, history=history, sync_id=sync_id),
                )
                total_histories_seen += 1

        if args.max_issues > 0 and total_issues_seen >= args.max_issues:
            break

        start_at += len(issues)
        total = page.get("total", 0)
        if start_at >= total:
            break

    sync_completed = utc_now()

    manifest = {
        "sync_id": sync_id,
        "mode": args.mode,
        "projects": projects,
        "since_source": since_source,
        "since_utc": since_dt.isoformat() if since_dt else None,
        "jql": jql,
        "counts": {
            "issues": total_issues_seen,
            "comments": total_comments_seen,
            "changelog_items": total_histories_seen,
        },
        "files": {
            "issues": str(issues_path),
            "comments": str(comments_path),
            "changelog": str(changelog_path),
        },
        "started_utc": sync_started.isoformat(),
        "completed_utc": sync_completed.isoformat(),
        "max_issue_updated_utc": updated_max.isoformat() if updated_max else None,
    }

    with (snapshot_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    checkpoint.update(
        {
            "last_successful_sync_utc": sync_completed.isoformat(),
            "last_sync_mode": args.mode,
            "last_projects": projects,
            "last_jql": jql,
            "last_snapshot_dir": str(snapshot_dir),
            "last_max_issue_updated_utc": updated_max.isoformat() if updated_max else checkpoint.get("last_max_issue_updated_utc"),
        }
    )

    if args.mode == "full":
        checkpoint["last_full_sync_utc"] = sync_completed.isoformat()
    else:
        checkpoint["last_incremental_sync_utc"] = sync_completed.isoformat()

    write_checkpoint(state_file, checkpoint)
    return manifest


def main() -> int:
    args = parse_args()

    try:
        manifest = run_ingestion(args)
        print("Sync completed")
        print(json.dumps(manifest, indent=2))
        return 0
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
