#!/usr/bin/env python3
"""
Build a FAISS index from Jira ingestion snapshots.

Input snapshot files:
- issues.jsonl
- comments.jsonl
- changelog.jsonl

Output index bundle:
- index.faiss
- metadata.jsonl
- manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FAISS RAG index from Jira snapshot JSONL files")
    parser.add_argument("--snapshot-dir", required=True, help="Path to a snapshot directory containing issues/comments/changelog JSONL")
    parser.add_argument("--output-dir", default="/Users/kusumathatavarthi/jira_ai_chatbot_artifacts/rag_index", help="Directory to write index artifacts")
    parser.add_argument("--provider", choices=["openai", "hash"], default="openai", help="Embedding provider")
    parser.add_argument("--openai-model", default="text-embedding-3-small")
    parser.add_argument("--openai-base-url", default="https://api.openai.com/v1")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--chunk-size", type=int, default=1200)
    parser.add_argument("--chunk-overlap", type=int, default=120)
    parser.add_argument("--max-comments-per-issue", type=int, default=200)
    parser.add_argument("--max-changelog-per-issue", type=int, default=400)
    parser.add_argument("--fallback-to-hash", action="store_true", help="Use local hash embeddings if OpenAI key is missing")
    return parser.parse_args()


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def adf_to_text(node: Any) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return " ".join(part for part in (adf_to_text(item) for item in node) if part).strip()
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    if node_type == "text":
        return node.get("text", "")

    content = node.get("content", [])
    text = " ".join(part for part in (adf_to_text(item) for item in content) if part).strip()

    if node_type in {"paragraph", "heading"}:
        return text + "\n"
    return text


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    cleaned = compact(text)
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: List[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        snippet = cleaned[start:end].strip()
        if snippet:
            chunks.append(snippet)
        if end == len(cleaned):
            break
        start += step
    return chunks


@dataclass
class Chunk:
    chunk_id: str
    issue_key: str
    issue_id: str
    chunk_type: str
    text: str
    metadata: Dict[str, Any]


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed(self, texts: Sequence[str], batch_size: int) -> np.ndarray:
        all_vectors: List[List[float]] = []
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            payload = {"model": self.model, "input": list(batch)}
            resp = requests.post(f"{self.base_url}/embeddings", headers=headers, json=payload, timeout=60)
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenAI embeddings failed ({resp.status_code}): {resp.text}")
            data = resp.json().get("data", [])
            if len(data) != len(batch):
                raise RuntimeError("Embedding response length mismatch")
            all_vectors.extend(item["embedding"] for item in data)

        arr = np.array(all_vectors, dtype=np.float32)
        return arr


class HashEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str], batch_size: int) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            token_counts: Dict[int, float] = defaultdict(float)
            tokens = re.findall(r"[a-zA-Z0-9_\-]+", text.lower())
            if not tokens:
                tokens = ["empty"]
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dim
                token_counts[idx] += 1.0
            for idx, value in token_counts.items():
                vectors[i, idx] = value
        return vectors


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def build_chunks(
    issues: List[Dict[str, Any]],
    comments: List[Dict[str, Any]],
    changelog: List[Dict[str, Any]],
    chunk_size: int,
    overlap: int,
    max_comments_per_issue: int,
    max_changelog_per_issue: int,
) -> List[Chunk]:
    comments_by_issue: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in comments:
        key = row.get("issue_key")
        if key:
            comments_by_issue[key].append(row)

    changelog_by_issue: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in changelog:
        key = row.get("issue_key")
        if key:
            changelog_by_issue[key].append(row)

    chunks: List[Chunk] = []

    for issue_row in issues:
        key = issue_row.get("key", "")
        issue_id = issue_row.get("id", "")
        fields = issue_row.get("fields", {})

        summary = fields.get("summary") or ""
        description = compact(adf_to_text(fields.get("description")))
        issue_type = (fields.get("issuetype") or {}).get("name")
        status = ((fields.get("status") or {}).get("name"))
        assignee = ((fields.get("assignee") or {}).get("displayName"))
        priority = ((fields.get("priority") or {}).get("name"))
        labels = fields.get("labels") or []
        project_key = ((fields.get("project") or {}).get("key"))
        updated = fields.get("updated")

        base_text = (
            f"Issue {key}\n"
            f"Type: {issue_type or 'Unknown'}\n"
            f"Status: {status or 'Unknown'}\n"
            f"Priority: {priority or 'Unknown'}\n"
            f"Assignee: {assignee or 'Unassigned'}\n"
            f"Labels: {', '.join(labels) if labels else 'None'}\n"
            f"Summary: {summary}\n"
            f"Description: {description or 'No description'}"
        )

        for idx, piece in enumerate(chunk_text(base_text, chunk_size, overlap)):
            chunk_id = f"{key}:issue:{idx}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    issue_key=key,
                    issue_id=issue_id,
                    chunk_type="issue",
                    text=piece,
                    metadata={
                        "issue_key": key,
                        "issue_id": issue_id,
                        "project_key": project_key,
                        "status": status,
                        "assignee": assignee,
                        "priority": priority,
                        "labels": labels,
                        "updated": updated,
                        "chunk_type": "issue",
                        "chunk_index": idx,
                    },
                )
            )

        issue_comments = comments_by_issue.get(key, [])[:max_comments_per_issue]
        for c_idx, comment_row in enumerate(issue_comments):
            comment = comment_row.get("comment", {})
            author = (comment.get("author") or {}).get("displayName")
            created = comment.get("created")
            body_text = compact(adf_to_text(comment.get("body")))
            if not body_text:
                continue
            comment_text = f"Issue {key} Comment by {author or 'Unknown'} at {created or 'Unknown'}: {body_text}"
            for idx, piece in enumerate(chunk_text(comment_text, chunk_size, overlap)):
                chunk_id = f"{key}:comment:{c_idx}:{idx}"
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        issue_key=key,
                        issue_id=issue_id,
                        chunk_type="comment",
                        text=piece,
                        metadata={
                            "issue_key": key,
                            "issue_id": issue_id,
                            "project_key": project_key,
                            "status": status,
                            "assignee": assignee,
                            "priority": priority,
                            "chunk_type": "comment",
                            "comment_id": comment.get("id"),
                            "comment_index": c_idx,
                            "chunk_index": idx,
                            "comment_created": created,
                        },
                    )
                )

        issue_changes = changelog_by_issue.get(key, [])[:max_changelog_per_issue]
        for h_idx, change_row in enumerate(issue_changes):
            history = change_row.get("history", {})
            author = (history.get("author") or {}).get("displayName")
            created = history.get("created")
            items = history.get("items") or []
            parts = []
            for item in items:
                field = item.get("field")
                from_value = item.get("fromString")
                to_value = item.get("toString")
                parts.append(f"{field}: {from_value} -> {to_value}")
            if not parts:
                continue
            change_text = f"Issue {key} Change by {author or 'Unknown'} at {created or 'Unknown'}: {'; '.join(parts)}"
            for idx, piece in enumerate(chunk_text(change_text, chunk_size, overlap)):
                chunk_id = f"{key}:change:{h_idx}:{idx}"
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        issue_key=key,
                        issue_id=issue_id,
                        chunk_type="changelog",
                        text=piece,
                        metadata={
                            "issue_key": key,
                            "issue_id": issue_id,
                            "project_key": project_key,
                            "status": status,
                            "assignee": assignee,
                            "priority": priority,
                            "chunk_type": "changelog",
                            "history_id": history.get("id"),
                            "history_index": h_idx,
                            "chunk_index": idx,
                            "history_created": created,
                        },
                    )
                )

    return chunks


def select_embedder(args: argparse.Namespace):
    if args.provider == "hash":
        return HashEmbedder(), "hash"

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        return OpenAIEmbedder(api_key=api_key, model=args.openai_model, base_url=args.openai_base_url), "openai"

    if args.fallback_to_hash:
        return HashEmbedder(), "hash"

    raise RuntimeError("OPENAI_API_KEY is required for --provider openai; or pass --fallback-to-hash")


def find_snapshot_files(snapshot_dir: Path) -> Tuple[Path, Path, Path]:
    issues = snapshot_dir / "issues.jsonl"
    comments = snapshot_dir / "comments.jsonl"
    changelog = snapshot_dir / "changelog.jsonl"

    if not issues.exists():
        raise RuntimeError(f"Missing required snapshot file: {issues}")
    # comments and changelog are optional; create empty if missing
    for optional in [comments, changelog]:
        if not optional.exists():
            optional.touch()
    return issues, comments, changelog


def main() -> int:
    args = parse_args()
    snapshot_dir = Path(args.snapshot_dir)
    if not snapshot_dir.exists():
        print(f"Snapshot directory does not exist: {snapshot_dir}", file=sys.stderr)
        return 1

    try:
        import faiss  # type: ignore
    except Exception as exc:
        print("Missing dependency: faiss-cpu. Install with: pip install faiss-cpu", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        return 1

    try:
        issues_file, comments_file, changelog_file = find_snapshot_files(snapshot_dir)
        issues = read_jsonl(issues_file)
        comments = read_jsonl(comments_file)
        changelog = read_jsonl(changelog_file)

        chunks = build_chunks(
            issues=issues,
            comments=comments,
            changelog=changelog,
            chunk_size=args.chunk_size,
            overlap=args.chunk_overlap,
            max_comments_per_issue=args.max_comments_per_issue,
            max_changelog_per_issue=args.max_changelog_per_issue,
        )
        if not chunks:
            raise RuntimeError("No chunks generated from snapshot")

        embedder, provider_used = select_embedder(args)
        texts = [chunk.text for chunk in chunks]
        vectors = embedder.embed(texts, batch_size=args.batch_size)
        vectors = normalize_vectors(vectors).astype(np.float32)

        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)

        snapshot_id = snapshot_dir.name
        out_dir = Path(args.output_dir) / snapshot_id
        ensure_dir(out_dir)

        index_path = out_dir / "index.faiss"
        metadata_path = out_dir / "metadata.jsonl"
        manifest_path = out_dir / "manifest.json"

        faiss.write_index(index, str(index_path))

        metadata_rows = []
        for i, chunk in enumerate(chunks):
            metadata_rows.append(
                {
                    "row_id": i,
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                }
            )
        write_jsonl(metadata_path, metadata_rows)

        manifest = {
            "created_at_utc": datetime.utcnow().isoformat() + "Z",
            "snapshot_dir": str(snapshot_dir),
            "output_dir": str(out_dir),
            "embedding_provider": provider_used,
            "embedding_model": args.openai_model if provider_used == "openai" else "hash-384",
            "dimension": dim,
            "counts": {
                "issues": len(issues),
                "comments": len(comments),
                "changelog": len(changelog),
                "chunks": len(chunks),
                "vectors": int(index.ntotal),
            },
            "files": {
                "index": str(index_path),
                "metadata": str(metadata_path),
            },
        }
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)

        print("RAG index built successfully")
        print(json.dumps(manifest, indent=2))
        return 0
    except Exception as exc:
        print(f"Index build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
