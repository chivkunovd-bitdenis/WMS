#!/usr/bin/env bash
# Merge task/<id> into integration branch (queue autopilot).
# Usage:
#   ./scripts/queue-integrate.sh PACK-01        # one task
#   ./scripts/queue-integrate.sh --all          # backlog order, skip already merged
#   INTEGRATION_BRANCH=feat/foo ./scripts/queue-integrate.sh CROSS-01
set -euo pipefail

INTEGRATION_BRANCH="${INTEGRATION_BRANCH:-feat/cz-ux-fixes}"

ORDER=(
  SHARED-01
  PACK-01 PACK-02 PACK-03 PACK-04 PACK-05 PACK-06 PACK-07 PACK-08 PACK-09
  PRINT-01 PRINT-02 PRINT-03 PRINT-04 PRINT-05
  LEDGER-01 LEDGER-02 LEDGER-03 LEDGER-04 LEDGER-05 LEDGER-06
  IMPORT-01 IMPORT-02 IMPORT-03 IMPORT-04 IMPORT-05
  POOLS-01 POOLS-02 POOLS-03 POOLS-04 POOLS-05 POOLS-06
  POOLCARD-02 POOLCARD-03 POOLCARD-01
  REPRINTS-01 REPRINTS-02 REPRINTS-03
  BACKEND-01
  PENDING-01
  CROSS-01 CROSS-02 CROSS-03 CROSS-04
  FINAL-01 FINAL-02 FINAL-03
)

integrate_one() {
  local id="$1"
  local task_branch="task/${id}"

  if ! git rev-parse --verify "${task_branch}" >/dev/null 2>&1; then
    echo "SKIP ${id}: branch ${task_branch} not found"
    return 0
  fi

  if git merge-base --is-ancestor "${task_branch}" "${INTEGRATION_BRANCH}" 2>/dev/null; then
    echo "SKIP ${id}: already in ${INTEGRATION_BRANCH}"
  else
    echo "MERGE ${id}: ${task_branch} -> ${INTEGRATION_BRANCH}"
    if ! git merge --no-ff "${task_branch}" -m "integrate(${id}): merge ${task_branch} into ${INTEGRATION_BRANCH}"; then
      echo "FAILED ${id}: merge conflict — resolve on ${INTEGRATION_BRANCH}, commit, re-run" >&2
      return 1
    fi
  fi

  mkdir -p .cursor/state
  touch ".cursor/state/${id}.integrated"
}

main() {
  if ! git rev-parse --verify "${INTEGRATION_BRANCH}" >/dev/null 2>&1; then
    echo "ERROR: integration branch ${INTEGRATION_BRANCH} does not exist" >&2
    exit 1
  fi

  git checkout "${INTEGRATION_BRANCH}"

  if [[ "${1:-}" == "--all" ]]; then
    for id in "${ORDER[@]}"; do
      integrate_one "${id}" || {
        echo ""
        echo "STOPPED on ${id}. Fix conflicts on ${INTEGRATION_BRANCH}, commit, then re-run:" >&2
        echo "  ./scripts/queue-integrate.sh --all" >&2
        exit 1
      }
    done
    echo "DONE: all task branches merged into ${INTEGRATION_BRANCH}"
    return 0
  fi

  if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <TASK-ID> | --all" >&2
    exit 1
  fi

  integrate_one "$1"
}

main "$@"
