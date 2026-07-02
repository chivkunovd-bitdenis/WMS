#!/usr/bin/env bash
# Push current commit to origin/staging → Railway auto-deploy (watch branch: staging).
# Prod is NOT touched (prod deploys only from main via deploy.yml + VPS).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: not a git repository" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree has uncommitted changes — commit or stash first" >&2
  git status --short
  exit 1
fi

SOURCE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
SOURCE_SHA="$(git rev-parse HEAD)"

echo "==> Railway staging deploy"
echo "    source: ${SOURCE_BRANCH} @ ${SOURCE_SHA:0:12}"
echo "    target: origin/staging (Railway watches this branch)"
echo "    prod:   unchanged (main + VPS only)"

git push origin "HEAD:staging"

echo ""
echo "==> Pushed. Railway will build only changed services (watchPatterns in railway.toml)."
echo "    Open your staging URL bookmark when deploy finishes (~2–6 min)."
echo ""
echo "Optional smoke (set WMS_STAGING_URL from Railway dashboard):"
echo "  WMS_STAGING_URL=https://your-web.up.railway.app ./scripts/railway-staging-smoke.sh"
