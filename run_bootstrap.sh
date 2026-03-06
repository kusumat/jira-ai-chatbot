#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="/Users/kusumathatavarthi/jira_ai_chatbot_artifacts"
ENV_FILE="$ROOT_DIR/.env.bootstrap"

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

/usr/local/bin/python3 "$ROOT_DIR/bootstrap_jira.py" \
  --site "$JIRA_SITE" \
  --project-key KAN \
  --project-name "Kanban AI Demo" \
  --create-project \
  --ticket-count 20
