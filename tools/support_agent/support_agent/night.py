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
from .pipeline import InlinePool, ThreadPool

TASK_RE = re.compile(r"^WMS-(\d+)$")
CONTRADICTION_RE = re.compile(r"\bC\d+\b.*\bR\d+\b|\bR\d+\b.*\bC\d+\b", re.IGNORECASE)
REQUIRED_CHECKS = {"baseline", "backlog", "backend", "frontend-build", "охрана"}
SKILLS_ROOT = "docs/reviews/2026-09-11-analyst-draft/skills"
TEST_PATH_RE = re.compile(r"(^|/)(tests?|guards|__snapshots__|fixtures)/|(^|/)conftest\.py$|\.test\.[jt]sx?$")
CONTROL_PATHS = (".github", "scripts/ci", "scripts/deploy", "guards", "backend/tests/guards",
                 "frontend/src/guards", "tools/support_agent", "AGENTS.md", "CLAUDE.md")


class NightRunner:
    """Advance one persisted transition per call."""

    def __init__(self, pipe: Any, hotfix: HotfixRunner) -> None:
        self.p, self.store, self.cfg = pipe, pipe.store, pipe.cfg
        self.hotfix = hotfix
        self.task_pool = InlinePool() if isinstance(pipe.pool, InlinePool) else ThreadPool(5)

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
            "prepare_release": bool(job.get("prepare_release")),
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
        task_id = state.get("_active_task_id")
        if task_id:
            # Each lane owns one task. Never write a stale snapshot of its siblings.
            task = state["tasks"][task_id]
            if "next_poll" in changes:
                task["next_poll"] = changes["next_poll"]
            with self.store.transaction():
                fresh = self._state(tid)
                current = fresh["tasks"].get(task_id, {})
                job = self.store.kv_get(f"agent_job:{fresh['job_id']}", {})
                if (self.store.ticket(tid)["stage"] != "development"
                        or current.get("status") != "working" or job.get("cancel_requested")):
                    return
                fresh["tasks"][task_id] = task
                self.store.patch_data(tid, night=fresh)
            return
        state.update(changes)
        with self.store.transaction():
            fresh = self._state(tid)
            # A long CI/model call must not restore a revoked owner permission.
            state["release_authorized"] = bool(fresh.get("release_authorized"))
            if "release_hold_reason" in fresh:
                state["release_hold_reason"] = fresh["release_hold_reason"]
            self.store.patch_data(tid, night=state)

    def _task(self, state: dict[str, Any]) -> dict[str, Any] | None:
        if state.get("_active_task_id"):
            return state["tasks"][state["_active_task_id"]]
        return next((task for task in state["tasks"].values()
                     if task["status"] == "working"), None)

    # -- development ----------------------------------------------------------------
    def development(self, tid: int) -> None:
        state = self._state(tid)
        if state.get("step") == "etalon_ci":
            with self.store.lock:
                if self._cancelled(tid, self._state(tid)):
                    return
            if self.p.clock() < float(state.get("next_poll", 0)):
                return
            try:
                self._etalon_ci(tid, state)
            except StepFailed as exc:
                with self.store.lock:
                    fresh = self._state(tid)
                    if fresh.get("step") == "etalon_ci" and not self._cancelled(tid, fresh):
                        self._stop_task(tid, fresh, self._task(fresh), str(exc))
            return
        # The controller's snapshot and global transitions are indivisible with
        # respect to lane saves, cancellation and owner messages in this process.
        # Worker/model calls use their own threads and do not hold this lock.
        with self.store.lock:
            self._schedule_development(tid)

    def _schedule_development(self, tid: int) -> None:
        state = self._state(tid)
        if self._cancelled(tid, state):
            return
        if self.p.clock() < float(state.get("next_poll", 0)):
            return
        # Older runtimes incorrectly made provider outages terminal. Resume only
        # that exact failure; do not reopen owner holds or failed safety checks.
        for interrupted in state["tasks"].values():
            if (interrupted.get("status") == "stopped"
                    and str(interrupted.get("reason", "")).startswith(
                        "frontend-разработчики Sonnet и Sol 5.6 недоступны:")):
                interrupted.update(status="working", step="developer")
                interrupted["feedback"] = (
                    str(interrupted.get("feedback") or "")
                    + "\nПредыдущий вызов прервался. Проверь и сохрани уже написанный код; "
                    "продолжи с существующего состояния, не повторяй внешние действия."
                ).strip()
                interrupted.pop("reason", None)
                self._save(tid, state)
        try:
            if state.get("step") == "etalon_ci":
                return
            deadline = state.get("deadline_at")
            if deadline and self.p.clock() >= float(deadline):
                for current in state["tasks"].values():
                    if current["status"] == "working":
                        current.update(status="stopped", step="stopped",
                                       reason="не готово к сроку выпуска")
                target = "release" if ((state.get("release_authorized") or state.get("prepare_release"))
                                       and any(current["status"] == "ready"
                                               for current in state["tasks"].values())) else "report"
                step = "candidate" if target == "release" else "morning_report"
                self.store.set_stage(tid, target, night={**state, "step": step, "next_poll": 0})
                return
            task = self._task(state)
            if task is None:
                if any(task["status"] == "ready" for task in state["tasks"].values()) \
                        and (state.get("release_authorized") or state.get("prepare_release")):
                    deadline = state.get("deadline_at")
                    if deadline and self.p.clock() < float(deadline):
                        self._save(tid, state, next_poll=min(float(deadline), self.p.clock() + 60))
                        return
                    self.store.set_stage(tid, "release", night={**state, "step": "candidate",
                                                                 "next_poll": 0})
                else:
                    self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})
                return
            for current in state["tasks"].values():
                if (current["status"] == "working"
                        and self.p.clock() >= float(current.get("next_poll", 0))):
                    task_id = current["id"]
                    def develop_selected(selected_id: str = task_id) -> None:
                        self._develop_task(tid, selected_id)
                    self.task_pool.submit(
                        f"night:{tid}:{task_id}",
                        develop_selected,
                    )
        except (LlmUnavailable, LlmError):
            self._save(tid, state, next_poll=self.p.clock() + 60)
        except StepFailed as exc:
            self._stop_task(tid, state, self._task(state), str(exc))

    def _develop_task(self, tid: int, task_id: str) -> None:
        state = self._state(tid)
        task = state["tasks"][task_id]
        job = self.store.kv_get(f"agent_job:{state['job_id']}", {})
        if (self.store.ticket(tid)["stage"] != "development"
                or task["status"] != "working" or job.get("cancel_requested")
                or self.p.clock() < float(task.get("next_poll", 0))):
            return
        state["_active_task_id"] = task_id
        task.pop("next_poll", None)
        try:
            getattr(self, f"_task_{task['step']}")(tid, state, task)
        except (LlmUnavailable, LlmError) as exc:
            task = self._task(state)
            if task is not None:
                route = "Sol 6.1"
                task["reason"] = f"ожидает доступности {route}: {exc}"
                task["model_retries"] = int(task.get("model_retries", 0)) + 1
            self._save(tid, state, next_poll=self.p.clock() + 60)
            return
        except StepFailed as exc:
            self._stop_task(tid, state, self._task(state), str(exc))

    def _etalon_ci(self, tid: int, state: dict[str, Any]) -> None:
        self.hotfix.fetch()
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
        completed = bool(runs and runs[0].get("status") == "completed")
        check = self._failed_run_check(runs[0]) if completed else ""
        with self.store.lock:
            state = self._state(tid)
            if (self.store.ticket(tid)["stage"] != "development"
                    or state.get("step") != "etalon_ci" or self._cancelled(tid, state)):
                return
            if not completed:
                self._save(tid, state, next_poll=self.p.clock() + 30)
                return
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
        self.hotfix.ensure_worktree(branch, path, base=state["etalon_sha"])
        # The approved document may still live on its task branch, not in etalon.
        source = self.store.data(task["ticket_id"]).get("agent", {}) if task.get("ticket_id") else {}
        doc_rel = f"docs/requirements/{task['id']}.md"
        backlog_rel = "docs/KANONICHESKIY_BACKLOG.md"
        if source.get("document_sha"):
            content = self.hotfix.git("show", f"{source['document_sha']}:{doc_rel}")
            doc = path / doc_rel
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text(content + "\n", encoding="utf-8")
            source_backlog = self.hotfix.git(
                "show", f"{source['document_sha']}:{backlog_rel}"
            )
            backlog = path / backlog_rel
            if not backlog.is_file():
                raise StepFailed("нет канонического бэклога в рабочей копии")
            backlog.write_text(
                self._replace_backlog_section(
                    backlog.read_text(encoding="utf-8"), source_backlog, task["id"]
                ),
                encoding="utf-8",
            )
        elif not (path / doc_rel).is_file():
            raise StepFailed("нет согласованного документа задачи; аналитик не должен придумывать постановку")
        if task.get("frontend"):
            self.hotfix.link_node_modules(str(path))
        task.update(step="analyst", branch=branch, path=str(path))
        task["control_hashes"] = self._control_hashes(task)
        self._commit(task, f"{task['id']}: согласованная постановка", paths=[doc_rel, backlog_rel])
        self._save(tid, state)

    @staticmethod
    def _replace_backlog_section(current: str, approved: str, task_id: str) -> str:
        header = re.compile(rf"(?m)^## {re.escape(task_id)}(?:\s|$)")

        def bounds(text: str) -> tuple[int, int] | None:
            match = header.search(text)
            if match is None:
                return None
            following = re.search(r"(?m)^## WMS-\d+(?:\s|$)", text[match.end():])
            end = match.end() + following.start() if following else len(text)
            return match.start(), end

        approved_bounds = bounds(approved)
        if approved_bounds is None:
            raise StepFailed(f"{task_id}: в согласованном коммите нет записи канонического бэклога")
        section = approved[slice(*approved_bounds)].strip()
        current_bounds = bounds(current)
        if current_bounds is None:
            return current.rstrip() + "\n\n" + section + "\n"
        start, end = current_bounds
        return current[:start].rstrip() + "\n\n" + section + "\n\n" + current[end:].lstrip()

    def _task_analyst(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        prompt = (
            f"Ты аналитик {task['id']}. Прочитай AGENTS.md и "
            f"{SKILLS_ROOT}/wms-product-analyst/SKILL.md. "
            f"Дополни docs/requirements/{task['id']}.md конкретными проверками. "
            "Таблица проверок обязана содержать столбцы «Класс» и «Тест». "
            'Сохрани согласованные требования. Измени только документ, Git-коммиты делает контроллер. '
            'Верни JSON {"summary":"...","checks":["C1"]}.'
        )
        self.p.llm.ask_json("analyst", prompt, ticket_id=task.get("ticket_id"),
                            session_key=f"night:{state['job_id']}:{task['id']}:analyst",
                            mode="write", cwd=task["path"], timeout=1800)
        doc = Path(task["path"]) / "docs" / "requirements" / f"{task['id']}.md"
        text = doc.read_text(encoding="utf-8") if doc.exists() else ""
        if "Класс" not in text or "Тест" not in text:
            raise StepFailed("аналитик не добавил столбцы «Класс» и «Тест»")
        doc_rel = f"docs/requirements/{task['id']}.md"
        if self._changed_outside(task, [doc_rel]):
            raise StepFailed("аналитик изменил файлы вне документа требований")
        self._commit(task, f"{task['id']}: проверки аналитика", paths=[doc_rel])
        task["step"] = "tester"
        self._save(tid, state)

    def _task_tester(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        prompt = (
            f"Ты тестировщик {task['id']}. Прочитай AGENTS.md, docs/requirements/{task['id']}.md "
            f"и {SKILLS_ROOT}/wms-test-writer/SKILL.md. Напиши контрактные тесты до кода реализации; "
            "ожидания не подгоняй. Заполни столбец «Тест»; Git-коммит делает контроллер. "
            'Верни JSON {"summary":"...","tests":["relative/path"]}.'
        )
        result, _ = self.p.llm.ask_json(
            "routine", prompt, ticket_id=task.get("ticket_id"),
            session_key=f"night:{state['job_id']}:{task['id']}:tester", mode="write",
            cwd=task["path"], timeout=3600,
        )
        tests = [str(item) for item in result.get("tests") or [] if self._safe_rel(str(item))]
        if not tests or any(not TEST_PATH_RE.search(path)
                            or not (Path(task["path"]) / path).is_file() for path in tests):
            raise StepFailed("тестировщик не создал контрактные тесты")
        if not any(self._executable_test(path) for path in tests):
            raise StepFailed("контракт содержит только вспомогательные файлы, исполняемых тестов нет")
        doc_rel = f"docs/requirements/{task['id']}.md"
        # Helper files the tests need (fixtures, conftest, seeds) belong to the contract too;
        # only changes outside test code stop the task.
        support = [item for item in self._changed_outside(task, tests + [doc_rel])
                   if TEST_PATH_RE.search(item)]
        tests = tests + [item for item in support if self._safe_rel(item)]
        unrelated = self._changed_outside(task, tests + [doc_rel])
        if unrelated:
            raise StepFailed("тестировщик изменил файлы вне контракта тестов: "
                             + ", ".join(unrelated))
        if not self._commit(task, f"{task['id']}: контракт тестов", paths=tests + [doc_rel]):
            raise StepFailed("контракт тестов не изменил Git")
        task.update(step="developer", tests=tests, contract_commit=self._head(task),
                    contract_hashes=self._hashes(task, tests))
        self._save(tid, state)

    def _task_developer(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        feedback = str(task.get("feedback", ""))
        prompt = (
            f"Ты разработчик {task['id']}. Прочитай AGENTS.md, docs/requirements/{task['id']}.md "
            f"и {SKILLS_ROOT}/wms-developer/SKILL.md. Сохраняй обязательное поведение. "
            "Если подтверждённая диагностика требует правки теста, фикстуры или имени, "
            "обнови затронутые проверки и передай изменение на обычное независимое ревью; "
            "не ослабляй assertions ради зелёного результата. "
            "Актуальное прямое решение владельца: все новые этапы, включая frontend/дизайн, "
            "выполняет только gpt-6.1-sol через Codex, без подмены другой моделью. "
            "Ревью выполняет отдельная сессия Sol 6.1. Это правило имеет приоритет "
            "над прежними назначениями моделей в файлах этой рабочей ветки. "
            "Ты уже отдельный разработчик внутри цепочки: аналитик и тестировщик завершили свои этапы. "
            "Выполни реализацию сам, не запускай вложенных агентов и не создавай чаты. "
            "Ревью, приёмку, commit, push и выпуск выполнит контроллер после твоего ответа. "
            "Перед правкой проверь существующий diff: после прерванного вызова продолжай его, "
            "не удаляя сохранённые изменения. "
            "Локально запусти контракт и tests/guards. Если проверка Cn противоречит Rm, "
            "не пиши код и укажи точное противоречие. "
            f"Замечание предыдущей попытки: {feedback or 'нет'}. "
            f"Полные журналы последних проверок (прочитай до исправления): {task.get('check_logs', {})}. "
            'Верни JSON {"summary":"...","contradiction":"" или "C1 противоречит R2"}.'
        )
        result, execution = self.p.llm.ask_json(
            "frontend" if task.get("frontend") else "routine", prompt,
            ticket_id=task.get("ticket_id"),
            session_key=f"night:{state['job_id']}:{task['id']}:developer", mode="write",
            cwd=task["path"], timeout=3600,
        )
        task.update(dev_cli=execution.cli, dev_model=execution.model)
        task.pop("feedback", None)
        task.pop("reason", None)
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
        self._sync_task_base(tid, state, task)
        self._refresh_contract_tests(task)
        self._assert_contract(task)
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
        task["step"] = "review"
        self._save(tid, state)

    def _task_review(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        head = self._head(task)
        if task.get("reviewed_sha") != head:
            prompt = (
                f"Проверь реализацию {task['id']}. Прочитай AGENTS.md, "
                f"docs/requirements/{task['id']}.md, diff, результаты тестов, "
                f"полные журналы {task.get('check_logs', {})}, "
                f"исходный коммит тестового контракта {task.get('contract_commit') or 'не указан'}, "
                f"изменение тестов/фикстур/имён: {'да' if task.get('contract_changed') else 'нет'}, "
                f"{SKILLS_ROOT}/../owner-cases.md и {SKILLS_ROOT}/../failure-cases.md целиком. "
                "Проверь требования, повторы, сбои и соседние процессы. Если менялись тесты, "
                "фикстуры или имена, отдельно изучи diff contract_commit → текущий SHA и "
                "подтверди, что исходное обязательное поведение сохранилось; обычные правки "
                "не требуют сохранения прежних байтов. Ничего не меняй. "
                "Прямое решение владельца: новый этап ревью выполняет отдельная сессия "
                "gpt-6.1-sol через Codex, без подмены; прежние назначения моделей отменены. "
                'Верни JSON {"accepted":true|false,"summary":"конкретные дефекты или результат"}.'
            )
            result, execution = self.p.llm.ask_json(
                "review", prompt, ticket_id=task.get("ticket_id"), mode="readonly",
                cli_only="codex",
                cwd=task["path"], timeout=1800,
                session_key=f"night:{state['job_id']}:{task['id']}:review",
            )
            if self._head(task) != head or self._changed_outside(task, []):
                raise StepFailed("ревью изменило проверяемую версию")
            if result.get("accepted") is not True:
                reason = str(result.get("summary") or "ревью не пройдено")
                if self._failure(tid, state, task, hashlib.sha256(reason.encode()).hexdigest(), reason):
                    return
                task.update(step="developer", feedback=reason)
                self._save(tid, state)
                return
            task.update(
                reviewed_sha=head,
                review_by=execution.model,
                review_summary=str(result.get("summary") or "ревью принято"),
            )
        task["step"] = "acceptance"
        self._save(tid, state)

    def _task_pr(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        self.hotfix.guard_gitdir(task["path"])
        self.hotfix.fetch()
        etalon = self.hotfix.git("rev-parse", "origin/etalon", cwd=task["path"]).strip()
        if self.hotfix.git_result(
            "merge-base", "--is-ancestor", etalon, "HEAD", cwd=task["path"]
        ).rc != 0:
            self._clear_stale_validation(task)
            task["step"] = "checks"
            self._save(tid, state)
            return
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
            self._assert_contract(task)
            if self._head(task) != task.get("ci_head") or task.get("accepted_sha") != task.get("ci_head"):
                raise StepFailed("CI и приёмка относятся к другой версии задачи")
            task.update(status="ready", step="ready", head_sha=task["ci_head"])
            self._save(tid, state)
            return
        if self.p.clock() - float(task.get("ci_started", self.p.clock())) > self.cfg.limits.ci_timeout_sec:
            raise StepFailed("CI задачи не завершился в срок")
        self._save(tid, state, next_poll=self.p.clock() + 30)

    def _task_acceptance(self, tid: int, state: dict[str, Any], task: dict[str, Any]) -> None:
        prompt = (
            f"Проведи приёмку {task['id']} как аналит по "
            f"{SKILLS_ROOT}/wms-product-analyst/SKILL.md. "
            "Прочитай requirements, diff, ревью и результаты тестов. Проверь сценарии. "
            f"Перекрёстное ревью: модель {task.get('review_by') or 'не указана'}, "
            f"SHA {task.get('reviewed_sha') or 'не указан'}, заключение: "
            f"{task.get('review_summary') or 'нет сохранённого текста'}. "
            f"Дополнительные материалы приёмки от ведущего: {task.get('feedback') or 'нет'}. "
            "Владелец назначил только gpt-6.1-sol через Codex для всех новых этапов. "
            "Аналитик, разработчик и ревьюер остаются отдельными сессиями; "
            "это актуальное правило вместо прежних назначений моделей в рабочей ветке. "
            "Заполни только вердикты и заключение в документе; требования и тесты не меняй. "
            "Git-коммит делает контроллер. Полный CI выполнится после фиксации приёмки. "
            'Верни JSON {"accepted":true|false,"summary":"..."}.'
        )
        result, _ = self.p.llm.ask_json(
            "analyst", prompt, ticket_id=task.get("ticket_id"),
            session_key=f"night:{state['job_id']}:{task['id']}:analyst", mode="write",
            cwd=task["path"], timeout=1800,
        )
        doc_rel = f"docs/requirements/{task['id']}.md"
        if self._changed_outside(task, [doc_rel]):
            raise StepFailed("приёмка изменила файлы вне документа требований")
        self._assert_contract(task)
        self._commit(task, f"{task['id']}: приёмка", paths=[doc_rel])
        if result.get("accepted") is not True:
            reason = str(result.get("summary") or "приёмка не пройдена")
            if self._failure(tid, state, task, hashlib.sha256(reason.encode()).hexdigest(), reason):
                return
            task.update(step="developer", feedback=reason)
            self._save(tid, state)
            return
        task.update(step="pr", accepted=str(result.get("summary") or ""), accepted_sha=self._head(task))
        self._save(tid, state)

    # -- release --------------------------------------------------------------------
    def release(self, tid: int) -> None:
        state = self._state(tid)
        if self._cancelled(tid, state):
            return
        if self.p.clock() < float(state.get("next_poll", 0)):
            return
        try:
            step = str(state.get("step"))
            # Preparing a candidate and its CI does not authorize publication.
            # Re-read the owner's decision at every mutating release boundary.
            dispatched = (self.store.data(tid).get("hotfix") or {}).get(f"{step}_intent")
            if (step in ("merge", "deploy", "promote") and not dispatched
                    and not self._state(tid).get("release_authorized")):
                if step in ("merge", "deploy"):
                    state["release_recheck"] = "candidate_ci" if step == "merge" else "merged_ci"
                self._save(tid, state, next_poll=self.p.clock() + 30)
                return
            if state.get("release_recheck") and not dispatched:
                recheck = state.pop("release_recheck")
                self._save(tid, state, step=recheck, next_poll=0)
                return
            if step == "candidate":
                self._candidate(tid, state)
            elif step == "candidate_ci":
                self._candidate_ci(tid, state)
            elif step == "awaiting_release":
                if self._state(tid).get("release_authorized"):
                    # Revalidate both PR SHAs and required checks after the hold.
                    self._candidate_ci(tid, state)
                else:
                    self._save(tid, state, next_poll=self.p.clock() + 30)
            elif step == "candidate_attribute":
                self._candidate_attribute(tid, state)
            elif step == "merged_ci":
                self._merged_ci(tid, state)
            elif step in ("merge", "deploy", "verify"):
                self._release_hotfix_step(tid, state, step)
            elif step == "promote":
                self._promote(tid, state)
            elif step == "promote_ci":
                self._promote_ci(tid, state)
        except (LlmUnavailable, LlmError) as exc:
            self._save(tid, state, model_retry_reason=str(exc), next_poll=self.p.clock() + 60)
            return
        except StepFailed as exc:
            state["release_error"] = str(exc)
            if state.get("release_sha"):
                for task_id in state["candidate"]["included"]:
                    state["tasks"][task_id]["promote"] = f"не завершено: {exc}"
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
        self.hotfix.fetch()
        base = self.hotfix.git("rev-parse", "origin/etalon").strip()
        deployed = self.hotfix.deployed_sha()
        if self.hotfix.run(["git", "merge-base", "--is-ancestor", deployed, base]).rc:
            raise StepFailed("рабочая версия содержит исправления вне etalon; выпуск потерял бы хотфикс")
        branch = f"codex/night-release-{state['job_id'][:8]}-{attempt}"
        path = Path(self.cfg.repo) / ".worktrees" / f"night-release-{state['job_id'][:8]}-{attempt}"
        self.hotfix.ensure_worktree(branch, path, base=base)
        for task in included:
            self._assert_contract(task)
            actual = self.hotfix.git("rev-parse", f"origin/{task['branch']}").strip()
            if actual != task.get("head_sha"):
                raise StepFailed(f"версия {task['id']} изменилась после приёмки и CI")
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
                              "head": self._head({"path": str(path)}), "base": base,
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
            view = self._pr_view(candidate["pr"])
            if view.get("headRefOid") != candidate["head"] or view.get("baseRefOid") != candidate["base"]:
                raise StepFailed("состав кандидата или etalon изменился после сборки; нужен новый прогон")
            if not self._state(tid).get("release_authorized"):
                self._save(tid, state, step="awaiting_release", next_poll=self.p.clock() + 30)
                return
            self.store.patch_data(tid, hotfix={"step": "merge", "pr": candidate["pr"],
                                                "path": candidate["path"],
                                                "expected_head": candidate["head"]})
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
        if next_step == "report":
            for task_id in state["candidate"]["included"]:
                state["tasks"][task_id].update(status="released", release_sha=current.get("merge_sha"))
        if step == "merge" and next_step == "deploy":
            next_step = "merged_ci"
            state["merged_ci_started"] = self.p.clock()
        self._save(tid, state, step="promote" if next_step == "report" else next_step,
                   release_sha=current.get("merge_sha"), next_poll=current.get("next_poll", 0))

    def _merged_ci(self, tid: int, state: dict[str, Any]) -> None:
        sha = state["release_sha"]
        response = self.hotfix.run_gh([
            "gh", "run", "list", "--workflow", "ci.yml", "--branch", "etalon",
            "--commit", sha, "--event", "push", "--limit", "1", "--json",
            "databaseId,headSha,status,conclusion",
        ])
        if response.rc:
            raise StepFailed("не удалось прочитать CI коммита слияния")
        runs = json.loads(response.out or "[]")
        if runs and runs[0].get("status") == "completed":
            run = runs[0]
            if run.get("headSha") != sha or run.get("conclusion") != "success" or self._failed_run_check(run):
                raise StepFailed("CI точного коммита слияния не зелёный; deploy не запускается")
            self._save(tid, state, step="deploy", next_poll=0)
            return
        if self.p.clock() - state["merged_ci_started"] > self.cfg.limits.ci_timeout_sec:
            raise StepFailed("CI коммита слияния не завершился в срок; deploy не запускается")
        self._save(tid, state, next_poll=self.p.clock() + 30)

    def _pr_view(self, pr: int) -> dict[str, Any]:
        response = self.hotfix.run_gh(["gh", "pr", "view", str(pr), "--json", "headRefOid,baseRefOid,state"])
        if response.rc:
            raise StepFailed("не удалось проверить точную версию PR")
        return json.loads(response.out)

    def _cancelled(self, tid: int, state: dict[str, Any]) -> bool:
        job = self.store.kv_get(f"agent_job:{state['job_id']}", {})
        if not job.get("cancel_requested"):
            return False
        hotfix = self.store.data(tid).get("hotfix") or {}
        # An already dispatched external action must be reconciled, not abandoned.
        if hotfix.get("deploy_intent") and state.get("step") in ("deploy", "verify"):
            return False
        if hotfix.get("merge_intent") and state.get("step") == "merge":
            return False
        for task in state["tasks"].values():
            if task["status"] != "released":
                task.update(status="stopped", reason="остановлено владельцем")
        job.update(status="cancelled", cancel_requested=True, finished_at=self.p.clock())
        with self.store.transaction():
            self.store.kv_set(f"agent_job:{state['job_id']}", job)
            self.store.set_stage(tid, "done", night={**state, "step": "done"})
        return True

    def _promote(self, tid: int, state: dict[str, Any]) -> None:
        promotion = state.get("promotion")
        if not promotion:
            branch = f"codex/night-guards-{state['job_id'][:8]}"
            path = Path(self.cfg.repo) / ".worktrees" / f"night-guards-{state['job_id'][:8]}"
            self.hotfix.ensure_worktree(branch, path, base=state["release_sha"])
            promotion = {"branch": branch, "path": str(path)}
            self._save(tid, state, promotion=promotion)
        path = promotion["path"]
        for task_id in state["candidate"]["included"]:
            task = state["tasks"][task_id]
            if task.get("promote"):
                continue
            if task.get("promote_intent"):
                raise StepFailed("перенос в охрану прерван; рабочая копия сохранена, повтор не запускался")
            task["promote_intent"] = True
            self._save(tid, state)
            res = self.hotfix.run(["python3", "scripts/ci/promote_guards.py", task_id], path, 1800)
            if res.rc != 0:
                raise StepFailed(f"{task_id}: перенос в охрану: {(res.out + res.err)[-300:]}")
            changed = self._commit(promotion, f"{task_id}: постоянные проверки в охране")
            if changed:
                promotion["changed"] = True
            task["promote"] = "сохранено, ожидает CI" if changed else "перенос не требуется"
            self._save(tid, state)
            return
        if promotion.get("changed"):
            self.hotfix.push_branch(promotion["branch"])
            found = self.hotfix.ensure_pr(
                promotion["branch"], base="etalon", title="Постоянная охрана после ночного выпуска",
                body="Перенос принятых проверок класса «навсегда» после выпуска.\n\n"
                     + "\n".join(state["candidate"]["included"]),
            )
            promotion.update(pr=found["number"], url=found.get("url"), head=self._head(promotion),
                             started=self.p.clock())
            self._save(tid, state, step="promote_ci", promotion=promotion, next_poll=0)
            return
        self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})

    def _promote_ci(self, tid: int, state: dict[str, Any]) -> None:
        promotion = state["promotion"]
        checks = self.hotfix.pr_checks(promotion["pr"])
        if any(check.get("bucket") == "fail" for check in checks):
            raise StepFailed(f"CI постоянной охраны красный: {promotion.get('url')}")
        if self.p.clock() - promotion["started"] > self.cfg.limits.ci_timeout_sec:
            raise StepFailed(f"постоянная охрана ожидает CI/слияния: {promotion.get('url')}")
        if not self._required_ci_passed(checks):
            self._save(tid, state, next_poll=self.p.clock() + 30)
            return
        pr = str(promotion["pr"])
        response = self.hotfix.run_gh(["gh", "pr", "view", pr, "--json", "state,headRefOid,mergeCommit"])
        if response.rc:
            raise StepFailed("не удалось проверить публикацию постоянной охраны")
        view = json.loads(response.out)
        if view.get("headRefOid") != promotion["head"]:
            raise StepFailed("версия PR постоянной охраны изменилась")
        if view.get("state") == "MERGED":
            for task_id in state["candidate"]["included"]:
                state["tasks"][task_id]["promote"] = f"в etalon: {promotion.get('url')}"
            self.store.set_stage(tid, "report", night={**state, "step": "morning_report"})
            return
        if view.get("state") != "OPEN":
            raise StepFailed("PR постоянной охраны закрыт без слияния")
        if not promotion.get("merge_intent"):
            with self.store.transaction():
                fresh = self._state(tid)
                if not fresh.get("release_authorized"):
                    fresh["next_poll"] = self.p.clock() + 30
                    self.store.patch_data(tid, night=fresh)
                    return
                promotion["merge_intent"] = True
                fresh["promotion"] = promotion
                self.store.patch_data(tid, night=fresh)
            self.hotfix.run_gh(["gh", "pr", "merge", pr, "--merge",
                               "--match-head-commit", promotion["head"]])
        self._save(tid, state, next_poll=self.p.clock() + 30)

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
        generation = state.get("resume_generation", 0)
        suffix = f":resume-{generation}" if generation else ""
        self.p.say_owner(f"night_report:{state['job_id']}{suffix}", body[:4000], tid, "night_report")
        job = self.store.kv_get(f"agent_job:{state['job_id']}", {})
        job.update(status="done", result=body, finished_at=self.p.clock())
        self.store.kv_set(f"agent_job:{state['job_id']}", job)
        self.store.set_stage(tid, "done", night={**state, "step": "done"})

    # -- helpers --------------------------------------------------------------------
    def _commit(self, task: dict[str, Any], message: str,
                *, paths: list[str] | None = None) -> bool:
        path = task["path"]
        self.hotfix.guard_gitdir(path)
        # `git add .` respects .gitignore; naming the ignored node_modules
        # symlink even as an exclusion can make Git return an error.
        pathspecs = [f":(literal){item}" for item in paths] if paths else ["."]
        self.hotfix.git("add", "-A", "--", *pathspecs, cwd=path)
        staged = self.hotfix.git("diff", "--cached", "--name-only", "--", *pathspecs,
                                 cwd=path)
        if not staged.strip():
            return False
        self.hotfix.git("-c", "user.name=WMS support agent", "-c", "user.email=noreply@openai.com",
                        "commit", "--no-verify", "-m", message, cwd=path)
        return True

    def _changed_outside(self, task: dict[str, Any], allowed: list[str]) -> list[str]:
        exclusions = [f":(exclude,literal){item}" for item in allowed]
        status = self.hotfix.git(
            "status", "--porcelain", "--untracked-files=all", "--", ".",
            ":(exclude)frontend/node_modules", *exclusions, cwd=task["path"],
        )
        paths: list[str] = []
        for line in status.splitlines():
            changed = line[3:] if len(line) > 3 else line
            if " -> " in changed:
                changed = changed.split(" -> ", 1)[1]
            if changed:
                paths.append(changed)
        return paths

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
            if path.is_symlink() or Path(task["path"]).resolve() not in path.resolve().parents:
                raise StepFailed("контракт тестов содержит ссылку за пределы рабочей копии")
            if path.is_file():
                result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def _assert_contract(self, task: dict[str, Any]) -> None:
        if "control_hashes" in task and self._control_hashes(task) != task["control_hashes"]:
            raise StepFailed("изменены CI, правила выпуска или защищённые проверки; автопубликация запрещена")
        changed = (self._hashes(task, task.get("tests") or []) != task.get("contract_hashes", {})
                   or bool(task.get("contract_paths_changed")))
        # Keep the original digest only as review context. Test/fixture bytes and
        # names are checked by the current test run and ordinary independent review.
        task["contract_changed"] = changed

    def _refresh_contract_tests(self, task: dict[str, Any]) -> None:
        """Run the current test paths after an ordinary reviewed test/fixture edit.

        Keep original paths still present in HEAD and include current executable
        paths added or changed since the test contract. Disabling rename detection
        makes the destination of a rename an ordinary added path. A deleted
        contract with no executable tests left still stops before local checks.
        """
        contract_commit = str(task.get("contract_commit") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", contract_commit):
            return
        result = self.hotfix.git(
            "diff", "--no-renames", "--name-status", contract_commit, "HEAD", "--",
            cwd=task["path"],
        )
        baseline_paths = task.get("contract_hashes") or {}
        original = list(dict.fromkeys(
            str(path) for path in (baseline_paths if baseline_paths else task.get("tests") or [])
        ))
        deleted: set[str] = set()
        added_or_changed: set[str] = set()
        changed_test_paths = False
        for line in result.splitlines():
            fields = line.split("\t")
            if len(fields) != 2:
                continue
            status, path = fields
            changed_test_paths = changed_test_paths or bool(TEST_PATH_RE.search(path))
            if status in ("A", "M", "C") and self._executable_test(path):
                added_or_changed.add(path)
            elif status == "D":
                deleted.add(path)

        root = Path(task["path"])
        refreshed: list[str] = []
        paths = [path for path in original if path not in deleted] + sorted(added_or_changed)
        for path in paths:
            if self._safe_rel(path) and (root / path).is_file():
                refreshed.append(path)
        refreshed = list(dict.fromkeys(refreshed))
        if any(self._executable_test(path) for path in original) and not any(
            self._executable_test(path) for path in refreshed
        ):
            raise StepFailed("контракт не содержит исполняемых тестов после изменений")
        task["tests"] = refreshed
        task["contract_paths_changed"] = changed_test_paths

    @staticmethod
    def _clear_stale_validation(task: dict[str, Any]) -> None:
        for key in (
            "reviewed_sha", "review_by", "review_summary", "accepted", "accepted_sha",
            "ci_head", "ci_started", "head_sha",
        ):
            task.pop(key, None)

    def _sync_task_base(
        self, tid: int, state: dict[str, Any], task: dict[str, Any],
    ) -> None:
        """Merge the latest trusted etalon before tests, review, acceptance and task CI."""
        self.hotfix.guard_gitdir(task["path"])
        self.hotfix.fetch()
        etalon = self.hotfix.git("rev-parse", "origin/etalon", cwd=task["path"]).strip()
        intent = task.get("base_sync_intent")
        if intent:
            if self.hotfix.git_result(
                "merge-base", "--is-ancestor", str(intent), "HEAD", cwd=task["path"]
            ).rc == 0:
                task["control_hashes"] = self._control_hashes(task)
                self._clear_stale_validation(task)
                task["base_sha"] = intent
            task.pop("base_sync_intent", None)
            self._save(tid, state)
        if self.hotfix.git_result(
            "merge-base", "--is-ancestor", etalon, "HEAD", cwd=task["path"]
        ).rc == 0:
            self._assert_contract(task)
            task["base_sha"] = etalon
            self._save(tid, state)
            return
        self._assert_contract(task)
        if self._changed_outside(task, []):
            raise StepFailed("нельзя обновить базу задачи с несохранёнными изменениями")
        backlog_rel = "docs/KANONICHESKIY_BACKLOG.md"
        task_backlog = (Path(task["path"]) / backlog_rel).read_text(encoding="utf-8")
        task["base_sync_intent"] = etalon
        self._save(tid, state)
        result = self.hotfix.git_result(
            "-c", "user.name=WMS support agent", "-c", "user.email=noreply@openai.com",
            "merge", "--no-ff", "--no-edit", etalon, cwd=task["path"], timeout=1800,
        )
        if result.rc != 0:
            conflicts = self.hotfix.git(
                "diff", "--name-only", "--diff-filter=U", cwd=task["path"]
            ).splitlines()
            if conflicts == [backlog_rel]:
                fresh_backlog = self.hotfix.git(
                    "show", f"{etalon}:{backlog_rel}", cwd=task["path"]
                )
                (Path(task["path"]) / backlog_rel).write_text(
                    self._replace_backlog_section(fresh_backlog, task_backlog, task["id"]),
                    encoding="utf-8",
                )
                self.hotfix.git("add", "--", backlog_rel, cwd=task["path"])
                finish = self.hotfix.git_result(
                    "-c", "user.name=WMS support agent", "-c",
                    "user.email=noreply@openai.com", "commit", "--no-edit",
                    cwd=task["path"],
                )
                if finish.rc == 0:
                    result = finish
            if result.rc != 0:
                self.hotfix.git_result("merge", "--abort", cwd=task["path"])
                task.pop("base_sync_intent", None)
                self._save(tid, state)
                raise StepFailed(
                    "актуальный etalon конфликтует с веткой задачи; нужна ручная интеграция"
                )
        task["control_hashes"] = self._control_hashes(task)
        task["base_sha"] = etalon
        task.pop("base_sync_intent", None)
        self._clear_stale_validation(task)
        self._save(tid, state)

    def _control_hashes(self, task: dict[str, Any]) -> dict[str, str]:
        root = Path(task["path"])
        paths = []
        for name in CONTROL_PATHS:
            path = root / name
            for item in ([path] if path.is_file() or path.is_symlink() else path.rglob("*")):
                if item.is_file() or item.is_symlink():
                    if "__pycache__" not in item.parts and item.suffix != ".pyc":
                        paths.append(item.relative_to(root).as_posix())
        return self._hashes(task, paths)

    @staticmethod
    def _executable_test(path: str) -> bool:
        return (path.startswith("backend/tests/") and Path(path).name.startswith("test_")
                and path.endswith(".py")) or bool(
                    path.startswith("frontend/src/") and re.search(r"\.test\.tsx?$", path))

    def _run_contract(self, task: dict[str, Any]) -> list[str]:
        root = Path(task["path"])
        backend = [path.removeprefix("backend/") for path in task.get("tests") or []
                   if path.startswith("backend/") and Path(path).name.startswith("test_")
                   and path.endswith(".py")]
        frontend = [path.removeprefix("frontend/") for path in task.get("tests") or []
                    if path.startswith("frontend/") and re.search(r"\.(test|spec)\.[jt]sx?$", path)]
        problems: list[str] = []
        backend_guards = (["tests/guards"]
                          if (root / "backend" / "tests" / "guards").exists() else [])
        if backend or backend_guards:
            python = str(Path(self.cfg.hotfix.backend_bin) / "python") \
                if self.cfg.hotfix.backend_bin else "python3"
            res = self.hotfix.run_untrusted([python, "-m", "pytest", "-n", "auto", "-q",
                                             *backend, *backend_guards], root, root / "backend", 1800)
            self._save_check_log(task, "backend", res.rc, res.out + res.err)
            if res.rc != 0:
                problems.append((res.out + res.err)[-1400:])
        frontend_guards = [path for path in ("tests/guards", "src/guards", "tests-guards")
                           if (root / "frontend" / path).exists()]
        if frontend or frontend_guards:
            command = ["npx", "vitest", "run", "--configLoader", "runner", *frontend, *frontend_guards]
            chromium = self.cfg.hotfix.frontend_chromium
            if chromium:
                if not Path(chromium).is_file():
                    raise StepFailed("настроенный тестовый Chromium не найден")
                command = ["/usr/bin/env", f"WMS_PRINT_CHROMIUM={chromium}", *command]
            res = self.hotfix.run_untrusted(command, root, root / "frontend", 1800)
            self._save_check_log(task, "frontend", res.rc, res.out + res.err)
            if res.rc != 0:
                problems.append((res.out + res.err)[-1400:])
        return problems

    def _save_check_log(self, task: dict[str, Any], suite: str, rc: int, output: str) -> None:
        root = Path(task["path"]).resolve()
        folder = root / ".agent-runs" / "night-checks"
        if root not in folder.resolve().parents:
            raise StepFailed("каталог журнала проверок находится вне рабочей копии")
        folder.mkdir(parents=True, exist_ok=True)
        head = self._head(task)
        path = folder / f"{suite}-{head}.log"
        if path.is_symlink():
            raise StepFailed("журнал проверок не должен быть символической ссылкой")
        path.write_text(f"SHA: {head}\nSuite: {suite}\nExit: {rc}\n\n{output}", encoding="utf-8")
        task.setdefault("check_logs", {})[suite] = str(path.relative_to(root))

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
