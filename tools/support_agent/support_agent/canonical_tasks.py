"""Persist an author-confirmed agent task in the canonical Git backlog and requirements.

One ticket has one reserved number and one named branch. A retry first examines
that branch and its remote, so a lost push response cannot allocate a new task.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


class CanonicalTaskError(RuntimeError):
    pass


def _git(repo: Path, *args: str, cwd: Path | None = None) -> str:
    run = subprocess.run(["git", *args], cwd=cwd or repo, capture_output=True,
                         text=True, timeout=120, check=False)
    if run.returncode:
        raise CanonicalTaskError(f"git {args[0]} failed: {run.stderr.strip()[:180]}")
    return run.stdout.strip()


def persist_task(pipe: Any, ticket_id: int) -> dict[str, Any]:
    store, repo = pipe.store, Path(pipe.cfg.repo).resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        raise CanonicalTaskError("configured Git repository unavailable")
    agent = dict(store.data(ticket_id).get("agent") or {})
    version = agent.get("version")
    if not version or agent.get("author_confirmation", {}).get("version") != version:
        raise CanonicalTaskError("current author confirmation missing")
    if agent.get("document_sha") and agent.get("document_version") == version:
        remote = _remote_sha(repo, agent["document_branch"])
        if remote and remote != agent["document_sha"]:
            _git(repo, "fetch", "origin", agent["document_branch"])
            check = subprocess.run(["git", "merge-base", "--is-ancestor",
                                    agent["document_sha"], remote], cwd=repo, capture_output=True,
                                   timeout=30, check=False)
            if check.returncode:
                raise CanonicalTaskError("recorded task commit is not on its remote branch")
        elif not remote:
            raise CanonicalTaskError("recorded task commit is not on its remote branch")
        return {"number": agent["wms_number"], "sha": agent["document_sha"],
                "branch": agent["document_branch"]}
    if not getattr(pipe, "hotfix", None):
        raise CanonicalTaskError("Git allocator unavailable")
    if not agent.get("wms_number"):
        number = pipe.hotfix.allocate_number(ticket_id)
        agent["wms_number"] = number
        store.patch_data(ticket_id, agent=agent)
    number = int(agent["wms_number"])
    branch = f"support-task/WMS-{number}-{ticket_id}"
    target = repo / ".worktrees" / f"support-task-{ticket_id}"
    if not target.exists():
        _git(repo, "fetch", "origin", "etalon")
        # A branch from a previous interrupted attempt can still have its worktree.
        refs = _git(repo, "branch", "--list", branch)
        if refs:
            _git(repo, "worktree", "add", str(target), branch)
        else:
            _git(repo, "worktree", "add", "-b", branch, str(target), "origin/etalon")
    if _git(repo, "status", "--porcelain", cwd=target):
        # Only our two documents are permitted in this dedicated worktree.
        changed = set(_git(repo, "status", "--porcelain", cwd=target).splitlines())
        if any(not (line[3:].startswith("docs/requirements/WMS-") or
                    line[3:] == "docs/KANONICHESKIY_BACKLOG.md") for line in changed):
            raise CanonicalTaskError("dedicated worktree contains unrelated changes")
    filename = f"WMS-{number}.md"
    path = target / "docs" / "requirements" / filename
    backlog = target / "docs" / "KANONICHESKIY_BACKLOG.md"
    sources = ", ".join(f"#{s}" for s in agent.get("source_message_ids", []))
    body = (f"# WMS-{number} · {agent['title']}\n\n"
                f"Источник: чат {store.ticket(ticket_id)['chat_id']}, сообщения {sources}.\n"
                f"Версия описания: `{version}`. Подтверждение автора: "
                f"#{agent['author_confirmation']['message_id']}.\n\n"
                f"## Ожидаемое поведение\n\n{agent['description']}\n\n"
                "## Проверки\n\n| Проверка | Действие и результат | Вердикт |\n"
                "|---|---|---|\n| C1 | Сверить реализацию с описанием автора | Не проверено |\n\n"
                "## Заключение\n\nРеализация и приёмка ещё не проводились.\n")
    if not path.exists() or path.read_text(encoding="utf-8") != body:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    text = backlog.read_text(encoding="utf-8")
    heading = f"## WMS-{number} · {agent['title']}"
    if not re.search(rf"(?m)^## WMS-{number}\b", text):
        backlog.write_text(text.rstrip() + "\n\n" + heading + "\n\n"
                           f"**Статус:** описание подтверждено автором; "
                           f"[требования](requirements/{filename}).\n", encoding="utf-8")
    _git(repo, "add", "--", str(path.relative_to(target)), str(backlog.relative_to(target)), cwd=target)
    if _git(repo, "diff", "--cached", "--name-only", cwd=target):
        _git(repo, "commit", "-m", f"docs(WMS-{number}): record confirmed agent task", cwd=target)
    sha = _git(repo, "rev-parse", "HEAD", cwd=target)
    # Fetch and inspect first. A previously successful push may have lost its answer.
    remote_sha = _remote_sha(repo, branch)
    if remote_sha and remote_sha != sha:
        check = subprocess.run(["git", "merge-base", "--is-ancestor", remote_sha, sha],
                               cwd=target, capture_output=True, timeout=30, check=False)
        if check.returncode:
            raise CanonicalTaskError("remote task branch differs; manual reconciliation needed")
    if remote_sha != sha:
        _git(repo, "push", "-u", "origin", branch, cwd=target)
        if _remote_sha(repo, branch) != sha:
            raise CanonicalTaskError("task branch push not verified")
    with store.transaction():
        current = dict(store.data(ticket_id).get("agent") or {})
        if current.get("version") != version:
            raise CanonicalTaskError("description changed during Git publication")
        current.update(document_sha=sha, document_version=version, document_branch=branch,
                       wms_number=number)
        store.patch_data(ticket_id, agent=current)
    return {"number": number, "sha": sha, "branch": branch}


def _remote_sha(repo: Path, branch: str) -> str | None:
    run = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
                         cwd=repo, capture_output=True, text=True, timeout=60, check=False)
    return run.stdout.split()[0] if run.returncode == 0 and run.stdout.split() else None
