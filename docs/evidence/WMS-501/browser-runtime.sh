#!/bin/sh
set -eu
ROOT=/Users/deniscivkunov/Projects/WMS/.worktrees/wms501-performance-isolation-audit
[ "$(pwd -P)" = "$ROOT" ] || exit 2
case "${1:-}" in
 backend|seed)
  if [ "$1" = backend ];then SCRIPT=browser-fault-app.py;else SCRIPT=browser-seed.py;fi
  exec env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin PYTHONPATH=backend DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_browser2 JWT_SECRET_KEY=wms501-local-browser-synthetic-test-key WMS_DATA_DIR="$ROOT/.audit-runtime/browser-data" WMS_ALLOW_PUBLIC_REGISTRATION=true CELERY_BROKER_URL=memory:// /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python "docs/evidence/WMS-501/$SCRIPT" ;;
 frontend)
  cd frontend
  VITE_API_PROXY=http://127.0.0.1:18451 exec npm run dev -- --host 127.0.0.1 --port 5541 --strictPort ;;
 *) exit 2;;
esac
