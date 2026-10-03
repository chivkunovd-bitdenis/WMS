"""Fixed overnight development and release controller.

Models perform bounded role steps. Code owns ordering, retries and external
transitions. Git, GitHub and deploy operations deliberately reuse HotfixRunner.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .hotfix import HotfixRunner, StepFailed
from .llm import LlmError, LlmUnavailable

TASK_RE = re.compile(r"^WMS-(\d+)$")
CONTRADICTION_RE = re.compile(r"\bC\d+\b.*\bR\d+\b|\bR\d+\b.*\bC\d+\b", re.IGNORECASE)
REQUIRED_CHECKS = {"baseline", "backlog", "backend", "frontend-build", "охрана"}
SKILLS_ROOT = "docs/reviews/2026-09-11-analyst-draft/skills"


class NightRunner:
    """Advance one persisted transition per call."""

    def __init__(self, pipe: Any, hotfix: HotfixRunner) -> None:
        self.p, self.store, self.cfg = pipe, pipe.store, pipe.cfg
        self.hotfix = hotfix

    def ensure_job(self, job_id: str) -> int:
        job = self.store.kv_get(f"agent_job:{job_id}", {})
        existing = int(job.get("night_ticket_id") or 0)
        if existing and self.store.row("SELECT id FROM tickets WHERE id=?", (existing,)):
            return existing
        tasks: dict[str, dict[str, Any]] = {}
        for task_id in job.get("task_ids") or []:
            match = TASK_RE.fullmatch(str(task_id))
            if not match:
                raise ValueError(f"invalid night task id: {task_id}")
            snapshot = (job.get("task_snapshot") or {}).get(task_id) or {}
            tasks[str(task_id)] = {
                "id": str(task_id), "number": int(match.group(1)), "step": "worktree",
                "status": "working", "ticket_id": snapshot.get("ticket_id"),
                "frontend": bool(snapshot.get("is_frontend")), "contract_changed": False,
            }
        night = {
            "job_id": job_id, "step": "etalon_ci", "tasks": tasks,
            "release_authorized": bool(job.get("release_authorized")),
            "deadline_at": job.get("deadline_at"), "candidate_attempt": 0,
        }
        with self.store.transaction():
            fresh = self.store.kv_get(f"agent_job:{job_id}", {})
            existing = int(fresh.get("night_ticket_id") or 0)
            if existing:
                return existing
            tid = self.store.add_ticket(kind="night_job", source="agent_job", chat_id=None,
                                        seller="", stage="development", data={"night": night})
            fresh.update(status="running", phase="night", night_ticket_id=tid)
            self.store.kv_set(f"agent_job:{job_id}", fresh)
            return tid

    def _state(self, tid: int) -> dict[str, Any]:
        return dict(self.store.data(tid).get("night") or {})

    def _save(self, tid: int, state: dict[str, Any], **changes: Any) -> None:
        state.update(changes)
        self.store.patch_data(tid, night=state)

    def _task(self, state: dict[str, Any]) -> dict[str, Any] | None:
        return next((task for task in state["tasks"].values()
                     if task["status"] == "working"), None)

    # -- development ----------------------------------------------------------------
    def development(self, tid: int) -> None:
        state = self._state(tid)
        if self.p.clock() < float(state.get("next_poll", 0)):
            return
        try:
            if state.get("step") == "etalon_ci":
                self._etalon_ci(tid, state)
                return
            deadline = state.get("deadline_at")
            if deadline and self.p.clock() >= float(deadline):
                for current in state["tasks"].values():
                    if current["status"] == "working":
                        current.update(status="stopped", step="stopped",
                                       reason="не готово к сроку выпуска")
                target = "release" if (state.get("release_authorized")
                                       and any(current["status"] == "ready"
                                               for current in state["tasks"].values())) else "report"
                step = "candidate" if target == "release" else "morning_report"
                self.store.set_stage(tid, target, night={**state, "step": step, "next_poll": 0})
                return
            task = self._task(state)
            if task is None:
                if any(task["status"] == "ready" for task in state["tasks"].values()) \
                        and state.get("release_authorized"):
                    deadline = state.get("deadline_at")
                    if deadline and self.p.clock() < float(deadline):
                        self._save(tid, state, next_poll=min(float(deadline), self.p.clock() + 60))
                        return
                    self.store.set_stage(tid, "release", night={**state, "step": "candidate",
                                                                 "next_poll": 0})
                else:
                    self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})
                return
            getattr(self, f"_task_{task['step']}")(tid, state, task)
        except (LlmUnavailable, LlmError):
            raise
        except StepFailed as exc:
            self._stop_task(tid, state, self._task(state), str(exc))

    def _etalon_ci(self, tid: int, state: dict[str, Any]) -> None:
        sha = self.hotfix.git("rev-parse", "origin/etalon").strip()
        res = self.hotfix.run_gh([
            "gh", "run", "list", "--workflow", "ci.yml", "--branch", "etalon",
            "--commit", sha, "--limit", "1", "--json",
            "databaseId,headSha,status,conclusion,displayTitle",
        ])
        try:
            runs = json.loads(res.out or "[]")
        except ValueError as exc:
            raise StepFailed("не удалось прочитать CI etalon") from exc
        if res.rc != 0 or not isinstance(runs, list):
            raise StepFailed("не удалось прочитать CI etalon")
        if not runs or runs[0].get("status") != "completed":
            self._save(tid, state, next_poll=self.p.clock() + 30)
            return
        check = self._failed_run_check(runs[0])
        if runs[0].get("conclusion") != "success" or check:
            check = check or str(runs[0].get("displayTitle") or "CI")
            self.p.say_owner(f"night_etalon_red:{state['job_id']}:{sha}",
                             f"etalon красный: {check}, ночь не запускаю",
                             tid, "night")
            for task in state["tasks"].values():
                task.update(status="stopped", reason=f"etalon красный: {check}")
            self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})
            return
        self._save(tid, state, step="tasks", etalon_sha=sha, next_poll=0)

    def _failed_run_check(self, run: dict[str, Any]) -> str:
        run_id = run.get("databaseId")
        if run_id:
            res = self.hotfix.run_gh(["gh", "run", "view", str(run_id), "--json", "jobs"])
            try:
                jobs = json.loads(res.out or "{}").get("jobs") or []
            except (ValueError, AttributeError):
                jobs = []
            by_name = {str(job.get("name")): str(job.get("conclusion")) for job in jobs}
            failed = [name for name in sorted(REQUIRED_CHECKS)
                      if by_name.get(name) != "success"]
            if failed:
                return ", ".join(failed)
            return ""
        return str(run.get("displayTitle") or "CI")

    def _task_worktree(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        branch = f"night/{task['id'].lower()}-{state['job_id'][:8]}"
        path = Path(self.cfg.repo) / ".worktrees" / f"night-{task['id'].lower()}-{state['job_id'][:8]}"
        self.hotfix.ensure_worktree(branch, path)
        if task.get("frontend"):
            self.hotfix.link_node_modules(str(path))
        task.update(step="analyst", branch=branch, path=str(path))
        self._save(tid, state)

    def _task_analyst(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        prompt = (
            f"Ты аналитик {task['id']}. Прочитай AGENTS.md и "
            f"{SKILLS_ROOT}/wms-product-analyst/SKILL.md. "
            f"Дополни docs/requirements/{task['id']}.md конкретными проверками. "
            "Таблица проверок обязана содержать столбцы «Класс» и «Тест». "
            'Измени только документ. Верни JSON {"summary":"...","checks":["C1"]}.'
        )
        self.p.llm.ask_json("analyst", prompt, ticket_id=task.get("ticket_id"),
                            session_key=f"night:{state['job_id']}:{task['id']}:analyst",
                            mode="write", cwd=task["path"], timeout=1800)
        doc = Path(task["path"]) / "docs" / "requirements" / f"{task['id']}.md"
        text = doc.read_text(encoding="utf-8") if doc.exists() else ""
        if "Класс" not in text or "Тест" not in text:
            raise StepFailed("аналитик не добавил столбцы «Класс» и «Тест»")
        task["step"] = "tester"
        self._save(tid, state)

    def _task_tester(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        prompt = (
            f"Ты тестировщик {task['id']}. Прочитай AGENTS.md, docs/requirements/{task['id']}.md "
            f"и {SKILLS_ROOT}/wms-test-writer/SKILL.md. Напиши контрактные тесты до кода реализации; "
            "ожидания не подгоняй. "
            'Верни JSON {"summary":"...","tests":["relative/path"]}.'
        )
        result, _ = self.p.llm.ask_json(
            "routine", prompt, ticket_id=task.get("ticket_id"),
            session_key=f"night:{state['job_id']}:{task['id']}:tester", mode="write",
            cwd=task["path"], timeout=3600,
        )
        tests = [str(item) for item in result.get("tests") or [] if self._safe_rel(str(item))]
        if not tests or any(not (Path(task["path"]) / path).is_file() for path in tests):
            raise StepFailed("тестировщик не создал контрактные тесты")
        if not self._commit(task, f"{task['id']}: контракт тестов"):
            raise StepFailed("контракт тестов не изменил Git")
        task.update(step="developer", tests=tests, contract_commit=self._head(task),
                    contract_hashes=self._hashes(task, tests))
        self._save(tid, state)

    def _task_developer(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        feedback = str(task.pop("feedback", ""))
        prompt = (
            f"Ты разработчик {task['id']}. Прочитай AGENTS.md, docs/requirements/{task['id']}.md "
            f"и {SKILLS_ROOT}/wms-developer/SKILL.md. Реализуй требования, не меняя контракт тестов. "
            "Локально запусти контракт и tests/guards. Если проверка Cn противоречит Rm, "
            "не пиши код и укажи точное противоречие. "
            f"Замечание предыдущей попытки: {feedback or 'нет'}. "
            'Верни JSON {"summary":"...","contradiction":"" или "C1 противоречит R2"}.'
        )
        result, _ = self.p.llm.ask_json(
            "frontend" if task.get("frontend") else "routine", prompt,
            ticket_id=task.get("ticket_id"),
            session_key=f"night:{state['job_id']}:{task['id']}:developer", mode="write",
            cwd=task["path"], timeout=3600,
        )
        contradiction = str(result.get("contradiction") or "").strip()
        if contradiction and CONTRADICTION_RE.search(contradiction):
            task.update(status="waiting_owner", reason=contradiction, step="owner_decision")
            self._save(tid, state)
            self.p.say_owner(f"night_decision:{state['job_id']}:{task['id']}",
                             f"{task['id']} ждёт твоего решения: {contradiction}", tid, "night")
            return
        changed = self._commit(task, f"{task['id']}: реализация")
        if not changed and feedback:
            self._stop_task(tid, state, task,
                            f"одинаковое падение повторилось без изменения кода: {feedback}")
            return
        task.update(step="checks", summary=str(result.get("summary") or ""))
        self._save(tid, state)

    def _task_checks(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        failures = self._run_contract(task)
        if failures:
            reason = "\n".join(failures)[-1800:]
            if self._failure(tid, state, task, hashlib.sha256(reason.encode()).hexdigest(), reason):
                return
            task.update(step="developer", feedback=("упала контрактная проверка, "
                                                    "ожидалось: pass, получено:\n"
                                                    f"{reason}"))
            self._save(tid, state)
            return
        task["contract_changed"] = self._hashes(task, task.get("tests") or []) != task.get("contract_hashes")
        task["step"] = "pr"
        self._save(tid, state)

    def _task_pr(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        self.hotfix.push_branch(task["branch"])
        task["pr_intent"] = True
        self._save(tid, state)
        found = self.hotfix.ensure_pr(
            task["branch"], base="etalon", title=f"{task['id']}: ночная разработка",
            body=f"Фиксированный ночной конвейер {task['id']}.",
        )
        task.update(step="ci", pr=found["number"], pr_url=found.get("url"),
                    ci_head=self._head(task), ci_started=self.p.clock())
        self._save(tid, state)

    def _task_ci(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        checks = self.hotfix.pr_checks(task["pr"])
        buckets = {str(check.get("bucket")) for check in checks}
        if checks and "fail" in buckets:
            names = ", ".join(str(check.get("name")) for check in checks if check.get("bucket") == "fail")
            fingerprint = hashlib.sha256(names.encode()).hexdigest()
            reason = f"упала {names}, ожидалось: pass, получено: fail"
            if self._failure(tid, state, task, fingerprint, reason):
                return
            task.update(step="developer", feedback=f"CI красный: {names}")
            self._save(tid, state)
            return
        if self._required_ci_passed(checks):
            task["step"] = "acceptance"
            self._save(tid, state)
            return
        if self.p.clock() - float(task.get("ci_started", self.p.clock())) > self.cfg.limits.ci_timeout_sec:
            raise StepFailed("CI задачи не завершился в срок")
        self._save(tid, state, next_poll=self.p.clock() + 30)

    def _task_acceptance(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        prompt = (
            f"Проведи приёмку {task['id']} как аналит по "
            f"{SKILLS_ROOT}/wms-product-analyst/SKILL.md. "
            "Прочитай requirements, diff и результаты тестов. Ничего не меняй: CI уже прошёл на точном SHA. "
            'Верни JSON {"accepted":true|false,"summary":"..."}.'
        )
        result, _ = self.p.llm.ask_json(
            "analyst", prompt, ticket_id=task.get("ticket_id"),
            session_key=f"night:{state['job_id']}:{task['id']}:analyst", mode="readonly",
            cwd=task["path"], timeout=1800,
        )
        if result.get("accepted") is not True:
            self._stop_task(tid, state, task,
                            str(result.get("summary") or "приёмка не пройдена"))
            return
        task.update(status="ready", step="ready", accepted=str(result.get("summary") or ""),
                    head_sha=self._head(task),
                    contract_changed=(self._hashes(task, task.get("tests") or [])
                                      != task.get("contract_hashes")))
        self._save(tid, state)

    # -- release --------------------------------------------------------------------
    def release(self, tid: int) -> None:
        state = self._state(tid)
        if self.p.clock() < float(state.get("next_poll", 0)):
            return
        try:
            step = str(state.get("step"))
            if step == "candidate":
                self._candidate(tid, state)
            elif step == "candidate_ci":
                self._candidate_ci(tid, state)
            elif step == "candidate_attribute":
                self._candidate_attribute(tid, state)
            elif step in ("merge", "deploy", "verify"):
                self._release_hotfix_step(tid, state, step)
            elif step == "promote":
                self._promote(tid, state)
        except (LlmUnavailable, LlmError):
            raise
        except StepFailed as exc:
            state["release_error"] = str(exc)
            self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})

    def _candidate(self, tid: int, state: dict[str, Any]) -> None:
        excluded = set(state.get("excluded") or [])
        included = [task for task in state["tasks"].values()
                    if task["status"] == "ready" and task["id"] not in excluded]
        if not included:
            self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})
            return
        attempt = int(state.get("candidate_attempt", 0)) + 1
        if attempt > 2:
            raise StepFailed("два прогона CI кандидата исчерпаны")
        branch = f"night/release-{state['job_id'][:8]}-{attempt}"
        path = Path(self.cfg.repo) / ".worktrees" / f"night-release-{state['job_id'][:8]}-{attempt}"
        self.hotfix.ensure_worktree(branch, path)
        for task in included:
            present = self.hotfix.run(["git", "merge-base", "--is-ancestor",
                                       f"origin/{task['branch']}", "HEAD"], path)
            if present.rc != 0:
                self.hotfix.git("merge", "--no-ff", "--no-edit", f"origin/{task['branch']}", cwd=path)
        self.hotfix.push_branch(branch)
        found = self.hotfix.ensure_pr(
            branch, base="etalon",
            title=f"Ночной выпуск {state['job_id'][:8]} ({attempt})",
            body="\n".join(task["id"] for task in included),
        )
        self._save(tid, state, step="candidate_ci", candidate_attempt=attempt,
                   candidate={"branch": branch, "path": str(path), "pr": found["number"],
                              "included": [task["id"] for task in included],
                              "started": self.p.clock()}, next_poll=0)

    def _candidate_ci(self, tid: int, state: dict[str, Any]) -> None:
        candidate = state["candidate"]
        checks = self.hotfix.pr_checks(candidate["pr"])
        buckets = {str(check.get("bucket")) for check in checks}
        if checks and "fail" in buckets:
            names = [str(check.get("name")) for check in checks if check.get("bucket") == "fail"]
            if int(state.get("candidate_attempt", 0)) >= 2:
                state["release_error"] = (f"упала {', '.join(names)}, "
                                          "ожидалось: pass, получено: fail")
                self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})
                return
            self._save(tid, state, step="candidate_attribute", candidate_failures=names)
            return
        if self._required_ci_passed(checks):
            self.store.patch_data(tid, hotfix={"step": "merge", "pr": candidate["pr"],
                                                "path": candidate["path"]})
            self._save(tid, state, step="merge")
            return
        if self.p.clock() - float(candidate["started"]) > self.cfg.limits.ci_timeout_sec:
            raise StepFailed("CI кандидата не завершился в срок")
        self._save(tid, state, next_poll=self.p.clock() + 30)

    def _candidate_attribute(self, tid: int, state: dict[str, Any]) -> None:
        candidate = state["candidate"]
        prompt = json.dumps({
            "failed_checks": state.get("candidate_failures"),
            "candidate_tasks": candidate["included"],
            "instruction": "Read the candidate diff and CI check names. Attribute the failure to "
                           "exactly one task only when evidence supports it. Return JSON task_id and reason.",
        }, ensure_ascii=False)
        result, _ = self.p.llm.ask_json("review", prompt, mode="readonly", cwd=candidate["path"],
                                        session_key=f"night:{state['job_id']}:candidate-review")
        task_id = str(result.get("task_id") or "")
        if task_id not in candidate["included"]:
            raise StepFailed("красный CI кандидата не удалось связать с одной задачей")
        task = state["tasks"][task_id]
        task.update(status="stopped", reason=f"упала {', '.join(state['candidate_failures'])}, "
                                             "ожидалось: pass, получено: fail; "
                                             f"{result.get('reason', '')}")
        self._save(tid, state, step="candidate",
                   excluded=list(state.get("excluded") or []) + [task_id])

    def _release_hotfix_step(self, tid: int, state: dict[str, Any], step: str) -> None:
        hotfix = dict(self.store.data(tid).get("hotfix") or {})
        if step == "merge":
            self.hotfix._s_merge(tid, hotfix)
        elif step == "deploy":
            self.hotfix._s_deploy(tid, hotfix)
        else:
            self.hotfix._s_verify(tid, hotfix)
        current = dict(self.store.data(tid).get("hotfix") or {})
        next_step = str(current.get("step"))
        self._save(tid, state, step="promote" if next_step == "report" else next_step,
                   release_sha=current.get("merge_sha"), next_poll=current.get("next_poll", 0))

    def _promote(self, tid: int, state: dict[str, Any]) -> None:
        path = state["candidate"]["path"]
        for task_id in state["candidate"]["included"]:
            task = state["tasks"][task_id]
            if task.get("promote"):
                continue
            if task.get("promote_intent"):
                task["promote"] = "исход неизвестен после перезапуска; не повторялось"
                self._save(tid, state)
                return
            task["promote_intent"] = True
            self._save(tid, state)
            res = self.hotfix.run(["python3", "scripts/ci/promote_guards.py", task_id], path, 1800)
            missing = res.rc != 0 and ("No such file" in res.err or "can't open file" in res.err)
            task["promote"] = "пропущено: нет скрипта" if missing else (
                "выполнено" if res.rc == 0 else f"ошибка: {(res.out + res.err)[-300:]}")
            self._save(tid, state)
            return
        for task_id in state["candidate"]["included"]:
            state["tasks"][task_id].update(status="released", release_sha=state.get("release_sha"))
        self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})

    # -- report ---------------------------------------------------------------------
    def report(self, tid: int) -> None:
        state = self._state(tid)
        lines: list[str] = []
        for task in state.get("tasks", {}).values():
            if task["status"] == "released":
                line = f"{task['id']}: выпущено ({str(task.get('release_sha') or '')[:12]})"
                if task.get("promote"):
                    line += f"; promote_guards: {task['promote']}"
            elif task["status"] == "waiting_owner":
                line = f"{task['id']}: ждёт твоего решения: {task.get('reason', '')}"
            else:
                reason = str(task.get("reason") or state.get("release_error")
                             or "не дошла до выпуска")
                line = f"{task['id']}: не выпущено: {reason}"
            lines.append(line)
            changed = "да" if task.get("contract_changed") else "нет"
            lines.append(f"{task['id']}: контракт тестов менялся: {changed}")
        body = "\n".join(lines)
        self.p.say_owner(f"night_report:{state['job_id']}", body[:4000], tid, "night_report")
        job = self.store.kv_get(f"agent_job:{state['job_id']}", {})
        job.update(status="done", result=body, finished_at=self.p.clock())
        self.store.kv_set(f"agent_job:{state['job_id']}", job)
        self.store.set_stage(tid, "done", night={**state, "step": "done"})

    # -- helpers --------------------------------------------------------------------
    def _commit(self, task: dict[str, Any], message: str) -> bool:
        path = task["path"]
        self.hotfix.guard_gitdir(path)
        self.hotfix.git("add", "-A", "--", ".", ":(exclude)frontend/node_modules", cwd=path)
        if not self.hotfix.git("status", "--porcelain", cwd=path).strip():
            return False
        self.hotfix.git("-c", "user.name=WMS support agent", "-c", "user.email=noreply@openai.com",
                        "commit", "--no-verify", "-m", message, cwd=path)
        return True

    def _head(self, task: dict[str, Any]) -> str:
        return self.hotfix.git("rev-parse", "HEAD", cwd=task["path"]).strip()

    @staticmethod
    def _safe_rel(path: str) -> bool:
        value = Path(path)
        return bool(path) and not value.is_absolute() and ".." not in value.parts

    def _hashes(self, task: dict[str, Any], paths: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for rel in paths:
            path = Path(task["path"]) / rel
            if path.is_file():
                result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def _run_contract(self, task: dict[str, Any]) -> list[str]:
        root = Path(task["path"])
        backend = [path.removeprefix("backend/") for path in task.get("tests") or []
                   if path.startswith("backend/")]
        frontend = [path.removeprefix("frontend/") for path in task.get("tests") or []
                    if path.startswith("frontend/")]
        problems: list[str] = []
        backend_guards = (["tests/guards"]
                          if (root / "backend" / "tests" / "guards").exists() else [])
        if backend or backend_guards:
            python = str(Path(self.cfg.hotfix.backend_bin) / "python") \
                if self.cfg.hotfix.backend_bin else "python3"
            res = self.hotfix.run_untrusted([python, "-m", "pytest", "-n", "auto", "-q",
                                             *backend, *backend_guards], root, root / "backend", 1800)
            if res.rc != 0:
                problems.append((res.out + res.err)[-1400:])
        frontend_guards = [path for path in ("tests/guards", "src/guards", "tests-guards")
                           if (root / "frontend" / path).exists()]
        if frontend or frontend_guards:
            res = self.hotfix.run_untrusted(["npx", "vitest", "run", *frontend,
                                             *frontend_guards],
                                             root, root / "frontend", 1800)
            if res.rc != 0:
                problems.append((res.out + res.err)[-1400:])
        return problems

    def _failure(self, tid: int, state: dict[str, Any], task: dict[str, Any],
                 fingerprint: str, reason: str) -> bool:
        current = {"sha": self._head(task), "fingerprint": fingerprint}
        if task.get("last_failure") == current:
            self._stop_task(tid, state, task, reason)
            return True
        task["last_failure"] = current
        self._save(tid, state)
        return False

    @staticmethod
    def _required_ci_passed(checks: list[dict[str, Any]]) -> bool:
        by_name = {str(check.get("name")): str(check.get("bucket")) for check in checks}
        return all(by_name.get(name) == "pass" for name in REQUIRED_CHECKS)

    def _stop_task(self, tid: int, state: dict[str, Any], task: dict[str, Any] | None,
                   reason: str) -> None:
        if task is None:
            state["release_error"] = reason
        else:
            task.update(status="stopped", reason=reason, step="stopped")
        self._save(tid, state)
