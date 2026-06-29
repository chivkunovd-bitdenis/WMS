#!/usr/bin/env bash
# Integration guard for queue autopilot — branch/worktree/state sanity.
#
# Usage:
#   ./scripts/queue-integration-guard.sh PACK-01     # before integrate (after adversarial APPROVE)
#   ./scripts/queue-integration-guard.sh --audit-done   # resume: .done must match integration
#   ./scripts/queue-integration-guard.sh --pre-worktree PACK-01  # before builder starts
set -euo pipefail

INTEGRATION_BRANCH="${INTEGRATION_BRANCH:-feat/cz-ux-fixes}"
STATE_DIR=".cursor/state"
WT_ROOT=".cursor/wt"

fail() {
  echo "GUARD FAIL: $*" >&2
  exit 1
}

ok() {
  echo "GUARD OK: $*"
}

skip_docs_only() {
  local id="$1"
  case "${id}" in
    CZ-000) return 0 ;;
    FINAL-03) return 0 ;;
  esac
  return 1
}

require_integration_branch() {
  if ! git rev-parse --verify "${INTEGRATION_BRANCH}" >/dev/null 2>&1; then
    fail "integration branch ${INTEGRATION_BRANCH} does not exist"
  fi
}

guard_pre_worktree() {
  local id="$1"
  local task_branch="task/${id}"

  require_integration_branch

  if skip_docs_only "${id}"; then
    ok "${id} docs/barrier — pre-worktree skip"
    exit 0
  fi

  local int_head
  int_head="$(git rev-parse "${INTEGRATION_BRANCH}")"
  ok "integration HEAD ${INTEGRATION_BRANCH}@${int_head:0:12} — use for new worktree"

  if [[ -d "${WT_ROOT}/${id}" ]]; then
    local wt_branch
    wt_branch="$(git -C "${WT_ROOT}/${id}" branch --show-current 2>/dev/null || true)"
    if [[ "${wt_branch}" != "${task_branch}" ]]; then
      fail "${id} worktree ${WT_ROOT}/${id} on '${wt_branch:-detached}', expected ${task_branch}"
    fi
    ok "worktree ${id} on ${task_branch}"
  fi
}

guard_task() {
  local id="$1"
  local task_branch="task/${id}"

  require_integration_branch

  if skip_docs_only "${id}"; then
    ok "${id} docs/barrier — integrate guard skip"
    exit 0
  fi

  if [[ -f "${STATE_DIR}/${id}.done" ]] && [[ ! -f "${STATE_DIR}/${id}.integrated" ]]; then
    if ! git merge-base --is-ancestor "${task_branch}" "${INTEGRATION_BRANCH}" 2>/dev/null; then
      fail "${id} has .done but not .integrated and task/${id} not in ${INTEGRATION_BRANCH} — run queue-integrate.sh ${id}"
    fi
  fi

  if ! git rev-parse --verify "${task_branch}" >/dev/null 2>&1; then
    fail "branch ${task_branch} not found — builder must commit in worktree first"
  fi

  if git merge-base --is-ancestor "${task_branch}" "${INTEGRATION_BRANCH}" 2>/dev/null; then
    ok "${id} already merged into ${INTEGRATION_BRANCH}"
    exit 0
  fi

  if [[ -d "${WT_ROOT}/${id}" ]]; then
    local wt_branch
    wt_branch="$(git -C "${WT_ROOT}/${id}" branch --show-current 2>/dev/null || true)"
    if [[ "${wt_branch}" != "${task_branch}" ]]; then
      fail "${id} worktree on '${wt_branch:-detached}', expected ${task_branch} — builder must fix"
    fi
    if [[ -n "$(git -C "${WT_ROOT}/${id}" status --porcelain)" ]]; then
      fail "${id} worktree has uncommitted changes — builder must commit before integrate"
    fi
  fi

  local behind
  behind="$(git rev-list --count "${task_branch}..${INTEGRATION_BRANCH}" 2>/dev/null || echo 0)"
  if [[ "${behind}" -gt 20 ]]; then
    echo "GUARD WARN: ${id} task branch is ${behind} commits behind ${INTEGRATION_BRANCH} — builder should rebase before merge" >&2
  fi

  ok "${id} ready for integrate (${task_branch} -> ${INTEGRATION_BRANCH})"
}

guard_audit_done() {
  require_integration_branch

  local failed=0
  shopt -s nullglob
  for done_file in "${STATE_DIR}"/*.done; do
    local id
    id="$(basename "${done_file}" .done)"
    if skip_docs_only "${id}"; then
      continue
    fi
    local task_branch="task/${id}"
    if ! git rev-parse --verify "${task_branch}" >/dev/null 2>&1; then
      echo "AUDIT FAIL: ${id} .done but no ${task_branch}" >&2
      failed=1
      continue
    fi
    if git merge-base --is-ancestor "${task_branch}" "${INTEGRATION_BRANCH}" 2>/dev/null; then
      continue
    fi
    if [[ -f "${STATE_DIR}/${id}.integrated" ]]; then
      echo "AUDIT WARN: ${id} .integrated but branch not ancestor — re-run queue-integrate.sh ${id}" >&2
      failed=1
      continue
    fi
    echo "AUDIT FAIL: ${id} .done without merge into ${INTEGRATION_BRANCH}" >&2
    failed=1
  done

  if [[ "${failed}" -ne 0 ]]; then
    fail "audit found .done tasks not in integration branch — run queue-integrate.sh --all or per-id"
  fi

  ok "all .done tasks are integrated into ${INTEGRATION_BRANCH}"
}

main() {
  case "${1:-}" in
    --audit-done)
      guard_audit_done
      ;;
    --pre-worktree)
      [[ $# -eq 2 ]] || fail "usage: $0 --pre-worktree <TASK-ID>"
      guard_pre_worktree "$2"
      ;;
    --help|-h)
      echo "Usage: $0 <TASK-ID> | --audit-done | --pre-worktree <TASK-ID>"
      exit 0
      ;;
    "")
      fail "usage: $0 <TASK-ID> | --audit-done | --pre-worktree <TASK-ID>"
      ;;
    *)
      guard_task "$1"
      ;;
  esac
}

main "$@"
