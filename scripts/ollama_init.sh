#!/bin/sh
set -eu

pull_url="${OLLAMA_PULL_BASE_URL:-http://ollama:11434}"

until curl -fsS "${pull_url}/api/tags" >/dev/null; do
  sleep 2
done

curl -fsS "${pull_url}/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"${OLLAMA_MODEL}\",\"stream\":false}"

curl -fsS "${pull_url}/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"${OLLAMA_EMBEDDING_MODEL}\",\"stream\":false}"
