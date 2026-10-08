#!/usr/bin/env python3
"""WMS-652 deployment gate; GET-only, no deploy or repository mutations."""
import argparse
import json
import re
import subprocess
import sys
from urllib.parse import urlencode

from scripts.ci.ci_scope import is_generated_evidence_output

REQUIRED_JOBS = {"baseline", "backlog", "scope", "backend", "frontend-build", "охрана",
                 "print-regressions", "printer-windows", "wms686-mockup", "process-proof"}
HEAVY_JOBS = REQUIRED_JOBS - {"baseline", "backlog", "scope", "охрана", "process-proof"}
WORKFLOW_PATH = ".github/workflows/ci.yml"
ACTIONS_APP_ID = 15368


class GateError(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


def api_get(path):
    try:
        result = subprocess.run(
            ["gh", "api", "--method", "GET", "--hostname", "github.com", path],
            check=True, capture_output=True, text=True, timeout=45,
        )
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        # Do not echo CLI output or credentials into Actions logs.
        raise GateError("GitHub API недоступен или вернул некорректный JSON", 3) from exc


def pages(get, path, key, query=None):
    """Read every page; refuse changing/truncated snapshots and API's 1000-run cap."""
    rows, seen, expected = [], set(), None
    for page in range(1, 102):
        data = get(path + "?" + urlencode({**(query or {}), "per_page": 100, "page": page}))
        total = data["total_count"]
        if expected is None:
            expected = total
        if total != expected or (key == "workflow_runs" and total >= 1000):
            raise GateError("Неполный или изменившийся список GitHub; повторите проверку", 3)
        batch = data[key]
        for row in batch:
            if row["id"] in seen:
                raise GateError("Повтор записи между страницами GitHub; повторите проверку", 3)
            seen.add(row["id"])
            rows.append(row)
        if len(rows) == expected:
            return rows
        if not batch or len(rows) > expected:
            break
    raise GateError("GitHub не вернул полный список", 3)


def verify(get, repository, sha):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise GateError("Некорректное имя owner/repository")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GateError("Нужен полный SHA из 40 строчных hex-символов")
    root = f"repos/{repository}"
    workflow = get(f"{root}/actions/workflows/ci.yml")
    if workflow["path"] != WORKFLOW_PATH or workflow["state"] != "active":
        raise GateError("Доверенный workflow CI отсутствует или выключен")
    workflow_id = workflow["id"]

    def latest():
        runs = pages(get, f"{root}/actions/workflows/{workflow_id}/runs", "workflow_runs",
                     {"head_sha": sha, "branch": "etalon", "event": "push"})
        # Do not accept a check with a matching name from another workflow/ref/event.
        candidates = [r for r in runs if
                      r["workflow_id"] == workflow_id and
                      r["path"].split("@")[0] == WORKFLOW_PATH and
                      r["repository"]["full_name"] == repository and
                      r["head_repository"]["full_name"] == repository and
                      r["head_sha"] == sha and r["head_branch"] == "etalon" and
                      r["event"] == "push"]
        if not candidates:
            raise GateError("Нет push-CI etalon для указанного SHA; выкладка ожидает CI", 4)
        return max(candidates, key=lambda r: (r["run_number"], r["id"]))

    run = latest()
    if run["status"] != "completed":
        raise GateError("Последний CI ещё не завершён; выкладка ожидает CI", 4)
    if run["conclusion"] != "success":
        raise GateError("Последний CI не завершился успешно")
    suite = get(f"{root}/check-suites/{run['check_suite_id']}")
    if (suite["app"]["id"] != ACTIONS_APP_ID or suite["app"]["slug"] != "github-actions"
            or suite["head_sha"] != sha):
        raise GateError("CI не принадлежит GitHub Actions или проверял другой SHA")
    attempt = run["run_attempt"]
    jobs = pages(get, f"{root}/actions/runs/{run['id']}/attempts/{attempt}/jobs", "jobs")
    by_name = {}
    for name in sorted(REQUIRED_JOBS):
        matches = [job for job in jobs if job["name"] == name]
        if len(matches) != 1:
            raise GateError(f"Обязательная задача {name}: отсутствует либо имя неоднозначно")
        job = matches[0]
        if job["head_sha"] != sha or job["run_id"] != run["id"] or job["status"] != "completed":
            raise GateError(f"Обязательная задача {name} не подтверждает успех этого SHA")
        by_name[name] = job
    docs_only = any(by_name[name]["conclusion"] == "skipped" for name in HEAVY_JOBS)
    if docs_only and not prose_only_commit(get, root, sha):
        raise GateError("Тяжёлые проверки пропущены для изменения исполняемых файлов")
    for name, job in by_name.items():
        allowed = {"success", "skipped"} if docs_only and name in HEAVY_JOBS else {"success"}
        if job["conclusion"] not in allowed:
            raise GateError(f"Обязательная задача {name} не подтверждает успех этого SHA")
    # Detect a rerun/new run that appeared while reading jobs. Never reuse old green.
    current = latest()
    if any(current[k] != run[k] for k in ("id", "run_attempt", "status", "conclusion")):
        raise GateError("CI изменился во время проверки; повторите проверку", 4)
    return {"sha": sha, "run_id": run["id"], "run_attempt": attempt,
            "conclusion": "success", "docs_only": docs_only}


def prose_path(path):
    if path in {"AGENTS.md", "CLAUDE.md"} or path.startswith("docs/"):
        return path.endswith((".md", ".rst"))
    return path in {"README.md", "CONTRIBUTING.md"}


def prose_only_commit(get, root, sha):
    commit = get(f"{root}/git/commits/{sha}")
    parents = commit.get("parents")
    if not isinstance(parents, list) or not parents:
        return False
    refs = [parents[0]["sha"], sha]
    trees = []
    for ref in refs:
        commit_info = get(f"{root}/git/commits/{ref}")
        tree_sha = commit_info["tree"]["sha"]
        data = get(f"{root}/git/trees/{tree_sha}?recursive=1")
        if data.get("truncated") is not False:
            raise GateError("Нельзя проверить полный список изменённых файлов")
        # Recursive tree responses include directory objects whose SHAs change
        # whenever a child file changes. Scope only actual files, including
        # added and deleted blobs, so prose-only edits remain classifiable.
        entries = data["tree"]
        names = [row["path"] for row in entries]
        if len(names) != len(set(names)):
            raise GateError("Повтор пути в дереве Git")
        rows = {row["path"]: (row["sha"], row["mode"]) for row in entries
                if row.get("type") == "blob"}
        trees.append(rows)
    old, new = trees
    changed = [path for path in old.keys() | new.keys() if old.get(path) != new.get(path)]
    return bool(changed) and all(
        prose_path(path) or is_generated_evidence_output(path) for path in changed
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(api_get, args.repository, args.sha)))
    except GateError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except (KeyError, TypeError, ValueError) as exc:
        print(f"Некорректная структура ответа GitHub ({type(exc).__name__})", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
