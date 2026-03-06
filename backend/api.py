#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import chatbot_cli as engine


RAG_INDEX_ROOT = Path("/Users/kusumathatavarthi/jira_ai_chatbot_artifacts/rag_index")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2)
    index_dir: str = ""
    top_k: int = Field(8, ge=1, le=50)
    project: str = ""
    chunk_types: List[str] = ["issue", "comment", "changelog"]
    llm_provider: str = Field("none", pattern="^(none|openai|claude)$")
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    claude_model: str = "claude-3-5-sonnet-latest"
    max_context_chars: int = Field(12000, ge=1000, le=40000)


class AskResponse(BaseModel):
    question: str
    clean_question: str
    executive: bool
    index_dir_used: str
    answer: str
    citations: List[str]
    retrieval: List[Dict[str, Any]]


app = FastAPI(title="Jira Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_INDEX_CACHE: Dict[str, Any] = {}


def load_bundle_cached(index_dir: str):
    cache_key = str(Path(index_dir).resolve())
    if cache_key in _INDEX_CACHE:
        return _INDEX_CACHE[cache_key]

    manifest, rows, index = engine.load_index_bundle(Path(cache_key))
    _INDEX_CACHE[cache_key] = (manifest, rows, index)
    return manifest, rows, index


def resolve_latest_index_dir() -> str:
    if not RAG_INDEX_ROOT.exists():
        raise RuntimeError(f"RAG index root not found: {RAG_INDEX_ROOT}")

    candidates = []
    for item in RAG_INDEX_ROOT.iterdir():
        if not item.is_dir():
            continue
        if (item / "index.faiss").exists() and (item / "metadata.jsonl").exists() and (item / "manifest.json").exists():
            candidates.append(item)

    if not candidates:
        raise RuntimeError(f"No valid index bundles found under: {RAG_INDEX_ROOT}")

    latest = sorted(candidates, key=lambda p: p.name)[-1]
    return str(latest)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/index/latest")
def latest_index() -> Dict[str, str]:
    return {"index_dir": resolve_latest_index_dir()}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    try:
        index_dir = req.index_dir.strip() if req.index_dir and req.index_dir.strip() else resolve_latest_index_dir()
        manifest, rows, index = load_bundle_cached(index_dir)

        is_executive = "executive summary" in req.question.lower()
        clean_question = req.question.replace("executive summary", "").strip()
        if not clean_question:
            clean_question = req.question.strip()
        priority_filter = engine.detect_priority_filter(clean_question)

        project_filter = req.project.strip().upper()
        chunk_types = {item.strip().lower() for item in req.chunk_types if item.strip()}

        retrieval_error: Optional[str] = None
        chunks = []
        try:
            chunks = engine.vector_retrieve(
                question=clean_question,
                manifest=manifest,
                rows=rows,
                index=index,
                top_k=req.top_k,
                project=project_filter,
                chunk_types=chunk_types,
                priority_filter=priority_filter,
            )
        except Exception as exc:
            retrieval_error = str(exc)

        if not chunks:
            filtered_rows = [
                row
                for row in rows
                if engine.passes_filters(
                    row,
                    project_filter,
                    chunk_types,
                    priority_filter=priority_filter,
                )
            ]
            chunks = engine.lexical_fallback(clean_question, filtered_rows, req.top_k)

        if not chunks and priority_filter == "p1":
            return AskResponse(
                question=req.question,
                clean_question=clean_question,
                executive=is_executive,
                index_dir_used=index_dir,
                answer="No Priority 1 (P1) tickets found for the current filters in indexed Jira data.",
                citations=[],
                retrieval=[],
            )

        context, citations = engine.build_context(chunks, max_chars=req.max_context_chars)

        if req.llm_provider == "openai":
            answer = engine.call_openai_answer(
                clean_question,
                context,
                model=req.openai_model,
                base_url=req.openai_base_url,
                executive=is_executive,
            )
        elif req.llm_provider == "claude":
            answer = engine.call_claude_answer(
                clean_question,
                context,
                model=req.claude_model,
                executive=is_executive,
            )
        else:
            answer = engine.extractive_answer(clean_question, chunks, citations)

        if retrieval_error:
            answer = f"[Retrieval note: {retrieval_error}]\n\n{answer}"

        retrieval_rows = [
            {
                "row_id": chunk.row_id,
                "score": chunk.score,
                "issue_key": chunk.metadata.get("issue_key"),
                "chunk_type": chunk.metadata.get("chunk_type"),
                "project_key": chunk.metadata.get("project_key"),
            }
            for chunk in chunks
        ]

        return AskResponse(
            question=req.question,
            clean_question=clean_question,
            executive=is_executive,
            index_dir_used=index_dir,
            answer=answer,
            citations=citations,
            retrieval=retrieval_rows,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
