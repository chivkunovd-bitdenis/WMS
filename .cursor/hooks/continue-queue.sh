#!/usr/bin/env bash
# stop hook: auto-continue orchestrator while docs/PARALLEL_AGENT_TASKS.md has open tasks.
set -euo pipefail

input=$(cat)
loop_count=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('loop_count',0))" 2>/dev/null || echo "0")
loop_limit=25

backlog_file="docs/PARALLEL_AGENT_TASKS.md"
if [[ ! -f "$backlog_file" ]]; then
  echo '{}'
  exit 0
fi

if [[ "$loop_count" -ge "$loop_limit" ]]; then
  echo '{}'
  exit 0
fi

# Open task: table row with task id (PACK-01, PRINT-01, …), id cell without done/blocked
has_open=$(
  grep -E '^\|[[:space:]]*(PACK|PRINT|LEDGER|IMPORT|POOLS|POOLCARD|REPRINTS|PENDING|SHARED|BACKEND|CROSS|FINAL|CZ)-' "$backlog_file" 2>/dev/null \
    | grep -viE '\bdone\b' \
    | grep -viE '\bblocked\b' \
    | head -1 \
    || true
)

if [[ -z "$has_open" ]]; then
  echo '{}'
  exit 0
fi

if [[ -f ".cursor/SESSION_HANDOFF.md" ]]; then
  workers=$(grep -E 'parallel_workers:\s*[0-9]+' ".cursor/SESSION_HANDOFF.md" 2>/dev/null | head -1 | grep -oE '[0-9]+' || echo "4")
else
  workers=4
fi

python3 - <<PY
import json
workers = ${workers}
msg = (
    f"orchestrator, continuous, queue mode. Прочитай docs/PARALLEL_AGENT_TASKS.md и .cursor/SESSION_HANDOFF.md. "
    f"parallel_workers: {workers}. Планирование: lane, files, depends_on (docs/CURSOR_QUEUE_LANES_RU.md). "
    f"До {workers} builder параллельно, строго 1 задача на 1 builder. "
    f"builder → verifier → fix до 3 раз. "
    f"Закрытие: ' done' в колонке id после verifier READY. "
    f"Обнови TASKLOG и SESSION_HANDOFF. Commit без команды владельца не делать."
)
print(json.dumps({"followup_message": msg}))
PY
