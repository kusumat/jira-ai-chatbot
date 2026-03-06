#!/usr/bin/env python3
"""
CLI chatbot over Jira RAG index.

- Loads FAISS index + metadata.jsonl + manifest.json from an index bundle directory
- Retrieves top-k chunks for a question
- Supports optional role/mock filters (project/chunk type)
- Produces citation-backed answer with LLM (OpenAI/Claude) or extractive fallback
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask questions over Jira FAISS index")
    parser.add_argument("--index-dir", required=True, help="Path containing index.faiss, metadata.jsonl, manifest.json")
    parser.add_argument("--question", required=True, help="User question")
    parser.add_argument("--top-k", type=int, default=8, help="Top chunks to return after filtering")
    parser.add_argument("--project", default="", help="Optional project key filter, e.g. KAN")
    parser.add_argument("--chunk-types", default="", help="Optional comma filter: issue,comment,changelog")
    parser.add_argument("--llm-provider", choices=["none", "openai", "claude"], default="none")
    parser.add_argument("--openai-model", default="gpt-4o-mini")
    parser.add_argument("--openai-base-url", default="https://api.openai.com/v1")
    parser.add_argument("--claude-model", default="claude-3-5-sonnet-latest")
    parser.add_argument("--max-context-chars", type=int, default=12000)
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    return parser.parse_args()


@dataclass
class RetrievedChunk:
    row_id: int
    score: float
    text: str
    metadata: Dict[str, Any]


class HashEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> np.ndarray:
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


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_index_bundle(index_dir: Path):
    try:
        import faiss  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Missing faiss-cpu dependency: {exc}")

    manifest_path = index_dir / "manifest.json"
    metadata_path = index_dir / "metadata.jsonl"
    index_path = index_dir / "index.faiss"

    missing = [str(p) for p in [manifest_path, metadata_path, index_path] if not p.exists()]
    if missing:
        raise RuntimeError(f"Missing index artifacts: {', '.join(missing)}")

    manifest = read_json(manifest_path)
    metadata_rows = read_jsonl(metadata_path)
    index = faiss.read_index(str(index_path))

    return manifest, metadata_rows, index


def embed_query_with_openai(question: str, model: str, base_url: str) -> np.ndarray:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing for OpenAI query embedding")

    resp = requests.post(
        f"{base_url.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "input": [question]},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI embeddings failed ({resp.status_code}): {resp.text}")

    data = resp.json().get("data", [])
    if len(data) != 1:
        raise RuntimeError("Unexpected embedding response")
    return np.array([data[0]["embedding"]], dtype=np.float32)


def lexical_fallback(question: str, rows: List[Dict[str, Any]], top_k: int) -> List[RetrievedChunk]:
    q_tokens = set(re.findall(r"[a-zA-Z0-9_\-]+", question.lower()))
    scored: List[RetrievedChunk] = []
    for row in rows:
        text = row.get("text", "")
        t_tokens = set(re.findall(r"[a-zA-Z0-9_\-]+", text.lower()))
        overlap = len(q_tokens & t_tokens)
        if overlap == 0:
            continue
        score = overlap / max(len(q_tokens), 1)
        scored.append(
            RetrievedChunk(
                row_id=int(row.get("row_id", -1)),
                score=float(score),
                text=text,
                metadata=row.get("metadata", {}),
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def detect_priority_filter(question: str) -> Optional[str]:
    lowered = question.lower()
    if re.search(r"\bp1\b|\bpriority\s*1\b|\bpriority\s*one\b", lowered):
        return "p1"
    return None


def is_priority_one(priority_value: str) -> bool:
    value = (priority_value or "").strip().lower()
    if not value:
        return False
    p1_tokens = [
        "p1",
        "priority 1",
        "priority one",
        "highest",
        "blocker",
        "critical",
        "sev1",
        "severity 1",
        "sev-1",
        "s1",
    ]
    if any(token in value for token in p1_tokens):
        return True
    return bool(re.fullmatch(r"p[\s\-_:]*1", value))


def passes_filters(
    row: Dict[str, Any],
    project: str,
    chunk_types: set[str],
    priority_filter: Optional[str] = None,
) -> bool:
    metadata = row.get("metadata", {})
    row_project = (metadata.get("project_key") or "").upper()
    row_chunk_type = (metadata.get("chunk_type") or "").lower()
    row_priority = str(metadata.get("priority") or "")

    if project and row_project != project.upper():
        return False
    if chunk_types and row_chunk_type not in chunk_types:
        return False
    if priority_filter == "p1" and not is_priority_one(row_priority):
        return False
    return True


def vector_retrieve(
    question: str,
    manifest: Dict[str, Any],
    rows: List[Dict[str, Any]],
    index: Any,
    top_k: int,
    project: str,
    chunk_types: set[str],
    priority_filter: Optional[str] = None,
) -> List[RetrievedChunk]:
    provider = manifest.get("embedding_provider", "")
    embedding_model = manifest.get("embedding_model", "")

    if provider == "hash":
        dim = int(manifest.get("dimension", 384))
        query_vec = HashEmbedder(dim=dim).embed([question])
    elif provider == "openai":
        query_vec = embed_query_with_openai(question, model=embedding_model, base_url="https://api.openai.com/v1")
    else:
        raise RuntimeError(f"Unsupported embedding_provider in manifest: {provider}")

    query_vec = normalize_vectors(query_vec).astype(np.float32)

    search_k = min(max(top_k * 8, 30), len(rows))
    if search_k == 0:
        return []

    distances, indices = index.search(query_vec, search_k)

    results: List[RetrievedChunk] = []
    for score, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(rows):
            continue
        row = rows[int(idx)]
        if not passes_filters(
            row,
            project=project,
            chunk_types=chunk_types,
            priority_filter=priority_filter,
        ):
            continue
        results.append(
            RetrievedChunk(
                row_id=int(row.get("row_id", idx)),
                score=float(score),
                text=row.get("text", ""),
                metadata=row.get("metadata", {}),
            )
        )
        if len(results) >= top_k:
            break

    return results


def build_context(chunks: List[RetrievedChunk], max_chars: int) -> Tuple[str, List[str]]:
    context_blocks: List[str] = []
    citations: List[str] = []
    running = 0

    for i, chunk in enumerate(chunks, start=1):
        issue_key = str(chunk.metadata.get("issue_key") or "UNKNOWN")
        chunk_type = str(chunk.metadata.get("chunk_type") or "unknown")
        citation = issue_key
        if citation not in citations:
            citations.append(citation)

        block = (
            f"[Evidence {i}] issue={issue_key} type={chunk_type} score={chunk.score:.4f}\n"
            f"{chunk.text}\n"
        )
        if running + len(block) > max_chars:
            break
        context_blocks.append(block)
        running += len(block)

    return "\n".join(context_blocks), citations


def call_openai_answer(question: str, context: str, model: str, base_url: str, executive: bool = False) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY missing for OpenAI answer generation")

    if executive:
        style_instruction = (
            "Provide a concise executive-level summary. "
            "Focus on business impact, delivery risk, and timeline implications. "
            "Avoid deep technical details."
        )
    else:
        style_instruction = (
            "Provide a detailed answer using retrieved Jira evidence. "
            "Include reasoning."
        )

    system_prompt = (
        "You are a Jira project assistant. "
        "Use only provided evidence. "
        "If evidence is insufficient, explicitly say so. "
        "Always reference issue keys in the answer. "
        + style_instruction
    )
    user_prompt = (
        f"Question:\n{question}\n\n"
        f"Evidence:\n{context}\n\n"
        "Return:\n"
        "1) Concise answer\n"
        "2) Key findings\n"
        "3) Citations (issue keys)\n"
        "4) Confidence (High/Medium/Low)"
    )

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI chat failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def call_claude_answer(question: str, context: str, model: str, executive: bool = False) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing for Claude answer generation")

    prompt = (
        "You are a Jira project assistant. Use only evidence below. If insufficient, say so. "
        "Include issue key citations.\n\n"
        f"Question:\n{question}\n\nEvidence:\n{context}\n"
    )

    payload = {
        "model": model,
        "max_tokens": 700,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Claude failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    content = data.get("content", [])
    texts = [item.get("text", "") for item in content if item.get("type") == "text"]
    return "\n".join(texts).strip()


def extractive_answer(question: str, chunks: List[RetrievedChunk], citations: List[str]) -> str:
    by_issue: Dict[str, List[RetrievedChunk]] = defaultdict(list)
    for chunk in chunks:
        issue = str(chunk.metadata.get("issue_key") or "UNKNOWN")
        by_issue[issue].append(chunk)

    lines = [f"Question: {question}"]
    if not chunks:
        lines.append("\nSummary")
        lines.append("- Insufficient evidence found in indexed Jira data.")
        return "\n".join(lines)

    owner_query = bool(re.search(r"\bwho\b.*\bworking\b|\bowner\b|\bassignee\b", question.lower()))
    p1_query = detect_priority_filter(question) == "p1"

    ranked_issues = sorted(by_issue.items(), key=lambda item: max(x.score for x in item[1]), reverse=True)

    issue_rows: List[Dict[str, str]] = []
    owners: Dict[str, List[str]] = defaultdict(list)

    for issue_key, issue_chunks in ranked_issues[:5]:
        best = sorted(issue_chunks, key=lambda x: x.score, reverse=True)[0]
        metadata = best.metadata
        assignee = str(metadata.get("assignee") or "Unassigned")
        status = str(metadata.get("status") or "Unknown")
        priority = str(metadata.get("priority") or "Unknown")
        snippet = best.text[:180] + ("..." if len(best.text) > 180 else "")

        issue_rows.append(
            {
                "issue_key": issue_key,
                "assignee": assignee,
                "status": status,
                "priority": priority,
                "snippet": snippet,
            }
        )
        owners[assignee].append(issue_key)

    lines.append("\nExecutive Summary")
    if p1_query:
        lines.append(f"- Found {len(issue_rows)} P1-related issue candidates in current retrieval window.")
    else:
        lines.append(f"- Found {len(issue_rows)} top relevant issues in current retrieval window.")

    if owner_query or p1_query:
        lines.append("\nWho is working on these tickets")
        sorted_owners = sorted(owners.items(), key=lambda item: len(item[1]), reverse=True)
        for owner, issues in sorted_owners:
            lines.append(f"- {owner}: {len(issues)} ticket(s) ({', '.join(issues)})")

    lines.append("\nIssue Details")
    for row in issue_rows:
        lines.append(
            f"- {row['issue_key']} | Priority: {row['priority']} | Status: {row['status']} | Assignee: {row['assignee']}"
        )
        lines.append(f"  Context: {row['snippet']}")

    score_avg = sum(c.score for c in chunks) / max(len(chunks), 1)
    confidence = "High" if score_avg >= 0.45 else "Medium" if score_avg >= 0.2 else "Low"
    lines.append("\nConfidence")
    lines.append(f"- {confidence}")
    lines.append("\nCitations")
    lines.append(f"- {', '.join(citations) if citations else 'None'}")
    return "\n".join(lines)


def to_json_output(question: str, answer: str, chunks: List[RetrievedChunk], citations: List[str]) -> Dict[str, Any]:
    return {
        "question": question,
        "answer": answer,
        "citations": citations,
        "retrieval": [
            {
                "row_id": chunk.row_id,
                "score": chunk.score,
                "issue_key": chunk.metadata.get("issue_key"),
                "chunk_type": chunk.metadata.get("chunk_type"),
                "project_key": chunk.metadata.get("project_key"),
            }
            for chunk in chunks
        ],
    }


def main() -> int:
    args = parse_args()

    index_dir = Path(args.index_dir)
    if not index_dir.exists():
        print(f"Index directory not found: {index_dir}", file=sys.stderr)
        return 1

    project_filter = args.project.strip().upper()
    chunk_types = {part.strip().lower() for part in args.chunk_types.split(",") if part.strip()}

    try:
        manifest, rows, index = load_index_bundle(index_dir)

        chunks = []
        retrieval_error: Optional[str] = None
        try:
            is_executive = "executive summary" in args.question.lower()
            clean_question = args.question.replace("executive summary", "").strip()
            if not clean_question:
                clean_question = args.question.strip()
            priority_filter = detect_priority_filter(clean_question)
            chunks = vector_retrieve(
                question=clean_question,
                manifest=manifest,
                rows=rows,
                index=index,
                top_k=args.top_k,
                project=project_filter,
                chunk_types=chunk_types,
                priority_filter=priority_filter,
            )
        except Exception as exc:
            retrieval_error = str(exc)
            priority_filter = detect_priority_filter(args.question)
            clean_question = args.question.strip()
            is_executive = "executive summary" in args.question.lower()

        if not chunks:
            filtered_rows = [
                row
                for row in rows
                if passes_filters(
                    row,
                    project_filter,
                    chunk_types,
                    priority_filter=priority_filter,
                )
            ]
            chunks = lexical_fallback(clean_question, filtered_rows, args.top_k)

        if not chunks and priority_filter == "p1":
            answer = "No Priority 1 (P1) tickets found for the current filters in indexed Jira data."
            citations: List[str] = []
            if args.json:
                print(json.dumps(to_json_output(clean_question, answer, chunks, citations), indent=2))
            else:
                print(answer)
                print("\nCitations: None")
            return 0

        context, citations = build_context(chunks, max_chars=args.max_context_chars)

        if args.llm_provider == "openai":
            answer = call_openai_answer(
                clean_question,
                context,
                model=args.openai_model,
                base_url=args.openai_base_url,
                executive=is_executive,
            )
        elif args.llm_provider == "claude":
            answer = call_claude_answer(
                clean_question,
                context,
                model=args.claude_model,
                executive=is_executive,
            )
        else:
            answer = extractive_answer(clean_question, chunks, citations)

        if retrieval_error:
            answer = f"[Retrieval note: {retrieval_error}]\n\n{answer}"

        if args.json:
            print(json.dumps(to_json_output(clean_question, answer, chunks, citations), indent=2))
        else:
            print(answer)
            print(f"\nCitations: {', '.join(citations) if citations else 'None'}")

        return 0
    except Exception as exc:
        print(f"Chatbot failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
