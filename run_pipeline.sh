#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="/Users/kusumathatavarthi/jira_ai_chatbot_artifacts"
ENV_FILE="$ROOT_DIR/.env.bootstrap"
DATA_DIR="$ROOT_DIR/data"
SNAPSHOT_BASE="$DATA_DIR/snapshots"
INDEX_BASE="$ROOT_DIR/rag_index"

usage() {
  cat <<'EOF'
Usage:
  run_pipeline.sh --question "..." [options]

Required:
  --question "..."                Question to ask chatbot

Optional:
  --projects "KAN,ENG"            Jira project keys (default: KAN)
  --mode full|incremental          Ingest mode (default: incremental)
  --provider openai|hash           Index embedding provider (default: openai)
  --llm none|openai|claude         Answer mode (default: none)
  --project-filter "KAN"          Retrieval project filter for chatbot
  --chunk-types "issue,comment,changelog"
  --top-k 8                        Retrieval top-k (default: 8)
  --jql-extra "status != Done"    Extra JQL applied during ingestion
  --since "2026-02-27T00:00:00Z"  Optional explicit incremental lower bound

Examples:
  ./run_pipeline.sh --question "What blockers are in KAN?"
  ./run_pipeline.sh --mode full --provider hash --llm none --question "Summarize risks"
  OPENAI_API_KEY=... ./run_pipeline.sh --provider openai --llm openai --question "What changed today?"
EOF
}

QUESTION=""
PROJECTS="KAN"
MODE="incremental"
PROVIDER="openai"
LLM_PROVIDER="none"
PROJECT_FILTER=""
CHUNK_TYPES="issue,comment,changelog"
TOP_K="8"
JQL_EXTRA=""
SINCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --question)
      QUESTION="$2"; shift 2 ;;
    --projects)
      PROJECTS="$2"; shift 2 ;;
    --mode)
      MODE="$2"; shift 2 ;;
    --provider)
      PROVIDER="$2"; shift 2 ;;
    --llm)
      LLM_PROVIDER="$2"; shift 2 ;;
    --project-filter)
      PROJECT_FILTER="$2"; shift 2 ;;
    --chunk-types)
      CHUNK_TYPES="$2"; shift 2 ;;
    --top-k)
      TOP_K="$2"; shift 2 ;;
    --jql-extra)
      JQL_EXTRA="$2"; shift 2 ;;
    --since)
      SINCE="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1 ;;
  esac
done

if [[ -z "$QUESTION" ]]; then
  echo "Missing required --question"
  usage
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [[ -z "${JIRA_EMAIL:-}" || -z "${JIRA_API_TOKEN:-}" || -z "${JIRA_SITE:-}" ]]; then
  echo "Please set JIRA_EMAIL, JIRA_API_TOKEN, and JIRA_SITE in $ENV_FILE"
  exit 1
fi

if [[ "$JIRA_SITE" == "https://id.atlassian.com" ]]; then
  echo "JIRA_SITE cannot be https://id.atlassian.com"
  echo "Set it to your tenant URL: https://<tenant>.atlassian.net"
  exit 1
fi

mkdir -p "$DATA_DIR" "$SNAPSHOT_BASE" "$INDEX_BASE"

echo "[1/3] Ingesting Jira data ($MODE)..."
INGEST_CMD=(
  /usr/local/bin/python3 "$ROOT_DIR/ingest_jira.py"
  --site "$JIRA_SITE"
  --projects "$PROJECTS"
  --mode "$MODE"
  --output-dir "$DATA_DIR"
)

if [[ -n "$JQL_EXTRA" ]]; then
  INGEST_CMD+=(--jql-extra "$JQL_EXTRA")
fi

if [[ -n "$SINCE" ]]; then
  INGEST_CMD+=(--since "$SINCE")
fi

"${INGEST_CMD[@]}"

if [[ ! -f "$DATA_DIR/checkpoint.json" ]]; then
  echo "Missing checkpoint after ingestion: $DATA_DIR/checkpoint.json"
  exit 1
fi

LATEST_SNAPSHOT=$(python3 - <<PY
import json
from pathlib import Path
cp = Path("$DATA_DIR/checkpoint.json")
obj = json.loads(cp.read_text(encoding="utf-8"))
print(obj.get("last_snapshot_dir", ""))
PY
)

if [[ -z "$LATEST_SNAPSHOT" || ! -d "$LATEST_SNAPSHOT" ]]; then
  echo "Could not resolve latest snapshot directory from checkpoint"
  exit 1
fi

echo "[2/3] Building vector index ($PROVIDER) from snapshot: $LATEST_SNAPSHOT"
INDEX_CMD=(
  /usr/local/bin/python3 "$ROOT_DIR/index_rag.py"
  --snapshot-dir "$LATEST_SNAPSHOT"
  --output-dir "$INDEX_BASE"
)

if [[ "$PROVIDER" == "hash" ]]; then
  INDEX_CMD+=(--provider hash)
else
  INDEX_CMD+=(--provider openai --fallback-to-hash)
fi

"${INDEX_CMD[@]}"

SNAPSHOT_ID=$(basename "$LATEST_SNAPSHOT")
INDEX_DIR="$INDEX_BASE/$SNAPSHOT_ID"

if [[ ! -d "$INDEX_DIR" ]]; then
  echo "Index directory not found: $INDEX_DIR"
  exit 1
fi

echo "[3/3] Asking chatbot ($LLM_PROVIDER)..."
ASK_CMD=(
  /usr/local/bin/python3 "$ROOT_DIR/chatbot_cli.py"
  --index-dir "$INDEX_DIR"
  --question "$QUESTION"
  --top-k "$TOP_K"
  --chunk-types "$CHUNK_TYPES"
  --llm-provider "$LLM_PROVIDER"
)

if [[ -n "$PROJECT_FILTER" ]]; then
  ASK_CMD+=(--project "$PROJECT_FILTER")
fi

"${ASK_CMD[@]}"
