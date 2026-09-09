#!/usr/bin/env bash
set -euo pipefail

# One final read-only review of the frozen production candidate. This does not
# schedule anything, deploy, alter credentials, or retry a usage-limited call.
python3 - <<'PY'
from datetime import datetime, timezone
ready = datetime(2026, 9, 9, 3, 10, 5, tzinfo=timezone.utc)
if datetime.now(timezone.utc) < ready:
    raise SystemExit('Opus review must wait until 2026-09-09 06:10:05 MSK; no CLI request sent.')
PY

review_dir=/Users/deniscivkunov/Projects/WMS/.worktrees/wms396-staging-release
request=/Users/deniscivkunov/Projects/WMS/.worktrees/wms396-stage/docs/reviews/wms-next-opus-request-20260909.txt
cd "$review_dir"
test "$(git rev-parse HEAD)" = 8cc97a07e6a8fa89e9506f7b79ef2474eb8a735b
test -z "$(git status --porcelain --untracked-files=no)"
test -s tmp/wms-next-frozen.diff
test -s "$request"
test ! -e tmp/wms-next-opus-result.json

claude -p --resume e4e0a5b1-2d0b-42bc-8dd9-3b919ef15f6b \
  --model claude-opus-4-7 --effort max \
  --tools Read,Grep,Glob --allowedTools Read,Grep,Glob \
  --permission-mode dontAsk --no-chrome --disable-slash-commands \
  --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
  --output-format json < "$request" > tmp/wms-next-opus-result.json
