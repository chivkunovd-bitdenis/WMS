#!/usr/bin/env bash
# stop hook: if .cursor/QUEUE.md has open tasks, auto-continue orchestrator queue mode.
set -euo pipefail

input=$(cat)
loop_count=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('loop_count',0))" 2>/dev/null || echo "0")
loop_limit=25

queue_file=".cursor/QUEUE.md"
if [[ ! -f "$queue_file" ]]; then
  echo '{}'
  exit 0
fi

if [[ "$loop_count" -ge "$loop_limit" ]]; then
  echo '{}'
  exit 0
fi

# Open task: line with MP-/TASK- id, no trailing " done" or " blocked"
has_open=$(
  grep -E '(MP-|TASK-)[0-9]+' "$queue_file" 2>/dev/null \
    | grep -viE '(^#|^\s*$|^\s*\|)' \
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
    f"orchestrator, continuous, queue mode. Прочитай .cursor/QUEUE.md и .cursor/SESSION_HANDOFF.md. "
    f"parallel_workers: {workers}. Раздай следующую пачку: до {workers} builder параллельно (run_in_background), "
    f"строго 1 открытая задача QUEUE на 1 builder. "
    f"На каждую: builder → verifier → fix до 3 раз. "
    f"Закрывай задачу только суффиксом ' done' в QUEUE после verifier READY. "
    f"Обнови TASKLOG и SESSION_HANDOFF. Без новых чатов, без вопросов владельцу."
)
print(json.dumps({"followup_message": msg}))
PY
