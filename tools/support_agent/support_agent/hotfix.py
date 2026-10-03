"""Облегчённый хотфикс (WMS-641, раздел 5): только после «кати» владельца по этому обращению.

Диспетчер сам код продукта не меняет: код пишет отдельная CLI-сессия-разработчик в отдельном
worktree. Каждый вызов step() делает один ограниченный шаг и записывает его итог в тикет, поэтому
перезапуск продолжает с той же стадии (R33), а потеря ответа внешней системы сначала выясняется
чтением (PR, деплой), а не повторяется.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

from . import prompts, sandbox
from .llm import ExecFn, ExecResult, LlmError, LlmUnavailable, default_exec
from .pipeline import Pipeline

log = logging.getLogger(__name__)
MAX_FIX_ROUNDS = 2
DEPLOY_LOOKUP_SEC = 120
MERGE_LOOKUP_SEC = 120
GIT_HARDEN = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.editor=true",
              "-c", "diff.external=", "-c", "core.untrackedCache=false", "-c", "core.pager=cat"]
FORBIDDEN_PATHS = (".github/", "scripts/deploy/", "scripts/ci/", ".claude/", ".cursor/",
                   "docker-compose", "deploy/", "tools/support_agent/")
HONEST_STATUS = "Статус: выложено в облегчённом режиме, приёмка аналитика не проводилась."


class RunsUnreadable(Exception):
    pass


class StepFailed(Exception):
    """Шаг не удался: останавливаемся и пишем владельцу (R25)."""


class HotfixRunner:
    def __init__(
        self, pipe: Pipeline, exec_fn: ExecFn = default_exec, http: httpx.Client | None = None
    ) -> None:
        self.p = pipe
        self.cfg = pipe.cfg
        self.store = pipe.store
        self.sh = exec_fn
        self.http = http or httpx.Client()

    # ===== git / gh ==================================================================
    def run(self, argv: list[str], cwd: str | Path | None = None, timeout: int = 300) -> ExecResult:
        return self.sh(argv, str(cwd) if cwd else self.cfg.repo, timeout, None)

    def must(self, argv: list[str], cwd: str | Path | None = None, timeout: int = 300) -> str:
        res = self.run(argv, cwd, timeout)
        if res.rc != 0:
            raise StepFailed(f"команда не удалась: {' '.join(argv[:3])}: {res.err.strip()[:200]}")
        return res.out

    def run_gh(self, argv: list[str], cwd: str | Path | None = None, timeout: int = 300) -> ExecResult:
        """gh запускается только из основного репозитория: из рабочей копии с недоверенными
        метаданными он мог бы исполнить чужие настройки git (N1). Аргумент cwd игнорируется."""
        return self.run(argv, None, timeout)

    def must_gh(self, argv: list[str], cwd: str | Path | None = None, timeout: int = 300) -> str:
        res = self.run_gh(argv, None, timeout)
        if res.rc != 0:
            raise StepFailed(f"команда не удалась: {' '.join(argv[:3])}: {res.err.strip()[:200]}")
        return res.out

    def run_untrusted(
        self, argv: list[str], worktree: str | Path, cwd: str | Path, timeout: int = 900
    ) -> ExecResult:
        """Код из worktree (ruff, mypy, pytest) исполняется под Seatbelt: без сети, запись только
        в worktree и временный каталог, конфиг агента и учётные данные владельца недоступны."""
        if not self.cfg.sandbox.enabled:
            return self.run(argv, cwd, timeout)
        with sandbox.temp_dir() as tmp:
            wrapped = sandbox.check_argv(
                argv, str(worktree), tmp, os.path.expanduser("~"), self.cfg.sandbox.extra_deny_read
            )
            return self.run(wrapped, cwd, timeout)

    def _in_worktree(self, cwd: str | Path | None) -> bool:
        if not cwd:
            return False
        root = (Path(self.cfg.repo) / ".worktrees").resolve()
        return root in Path(cwd).resolve().parents

    def git(self, *args: str, cwd: str | Path | None = None) -> str:
        """Git в рабочей копии, которую правил недоверенный код, запускается с жёсткими настройками:
        без fsmonitor и хуков, без внешних драйверов diff, без системного конфига (N1)."""
        if self._in_worktree(cwd):
            return self.must(["/usr/bin/env", "GIT_CONFIG_NOSYSTEM=1", "git", *GIT_HARDEN, *args], cwd)
        return self.must(["git", *args], cwd)

    def trusted_admin_dir(self, path: str | Path) -> Path:
        """Каталог метаданных worktree берём из ДОВЕРЕННОГО основного .git (недоступен песочнице)."""
        want = (Path(path) / ".git").resolve()
        admin_root = Path(self.cfg.repo) / ".git" / "worktrees"
        if admin_root.is_dir():
            for admin in admin_root.iterdir():
                pointer = admin / "gitdir"
                if pointer.is_file() and Path(pointer.read_text(encoding="utf-8").strip()).resolve() == want:
                    return admin.resolve()
        raise StepFailed("рабочая копия не зарегистрирована в основном git: метаданные подменены")

    def guard_gitdir(self, path: str | Path) -> None:
        """Перед привилегированным Git: .git рабочей копии — обычный файл-ссылка на ожидаемый каталог
        метаданных, и git rev-parse подтверждает пути. Иначе подмена (хуки, fsmonitor) — остановка."""
        admin = self.trusted_admin_dir(path)
        gitfile = Path(path) / ".git"
        if gitfile.is_symlink() or not gitfile.is_file():
            raise StepFailed("метаданные .git рабочей копии подменены (не файл-ссылка)")
        if gitfile.read_text(encoding="utf-8").strip() != f"gitdir: {admin}":
            raise StepFailed("метаданные .git рабочей копии подменены (другая ссылка)")
        out = self.git("rev-parse", "--git-dir", "--git-common-dir", cwd=path).split()
        if len(out) != 2:
            raise StepFailed("не удалось подтвердить каталог метаданных git")
        git_dir, common = ((Path(path) / out[0]).resolve(), (Path(path) / out[1]).resolve())
        if git_dir != admin or common != (Path(self.cfg.repo) / ".git").resolve():
            raise StepFailed("git указывает не на ожидаемые каталоги метаданных: рабочая копия подменена")

    def fetch(self) -> None:
        self.git("fetch", "origin")

    def ensure_worktree(self, branch: str, path: str | Path,
                        base: str = "origin/etalon") -> Path:
        """Idempotently create a named worktree from a verified caller-selected base."""
        target = Path(path)
        self.fetch()
        if not target.exists():
            self.git("worktree", "add", "-b", branch, str(target), base)
        return target

    def push_branch(self, branch: str) -> None:
        """Use the trusted checkout for a repeat-safe branch publication."""
        self.git("push", "-u", "origin", branch)

    def find_pr(self, branch: str) -> dict[str, Any] | None:
        res = self.run_gh(["gh", "pr", "list", "--head", branch, "--state", "all", "--json",
                           "number,url,state"])
        try:
            rows = json.loads(res.out or "[]")
        except ValueError:
            rows = []
        return rows[0] if res.rc == 0 and rows else None

    def ensure_pr(self, branch: str, *, base: str, title: str, body: str) -> dict[str, Any]:
        """Read before create and read after it, so a lost create response is not repeated."""
        found = self.find_pr(branch)
        if found is None:
            self.run_gh(["gh", "pr", "create", "--base", base, "--head", branch,
                         "--title", title, "--body", body])
            found = self.find_pr(branch)
        if found is None:
            raise StepFailed("pull request не удалось найти после создания")
        return found

    def pr_checks(self, pr: int | str) -> list[dict[str, Any]]:
        """Read PR checks; polling never reruns CI."""
        res = self.run_gh(["gh", "pr", "checks", str(pr), "--json", "name,bucket"])
        try:
            checks = json.loads(res.out or "[]")
        except ValueError as exc:
            raise StepFailed("не удалось прочитать состояние CI") from exc
        if not isinstance(checks, list):
            raise StepFailed("не удалось прочитать состояние CI")
        return checks

    def analysis_dir(self) -> Path:
        """Свежий origin/etalon только для чтения аналитиком (не чужой рабочий checkout)."""
        path = Path(self.cfg.repo) / ".worktrees" / "support-agent-etalon"
        now = self.p.clock()
        if now - float(self.store.kv_get("analysis_fetch_ts", 0)) >= 600 or not path.exists():
            self.fetch()
            self.store.kv_set("analysis_fetch_ts", now)
            if path.exists():
                self.git("checkout", "--detach", "origin/etalon", cwd=path)
            else:
                self.git("worktree", "add", "--detach", str(path), "origin/etalon")
        return path

    # ===== номер задачи ================================================================
    def used_numbers(self) -> set[int]:
        text = [
            self.run(["git", "show", "origin/etalon:docs/KANONICHESKIY_BACKLOG.md"]).out,
            self.run(["git", "branch", "--all", "--format=%(refname:short)"]).out,
            self.run(["git", "log", "origin/etalon", "-400", "--format=%s"]).out,
            self.run(["git", "ls-tree", "--name-only", "origin/etalon", "docs/requirements/"]).out,
            self.run(["git", "worktree", "list"]).out,
        ]
        gh = self.run_gh(["gh", "pr", "list", "--state", "all", "--limit", "200", "--json",
                       "title,headRefName"])
        if gh.rc == 0:
            text.append(gh.out)
        found = {int(n) for blob in text for n in re.findall(r"WMS[-_]0*(\d{3,4})(?!\d)", blob, re.I)}
        found |= {int(n) for blob in text for n in re.findall(r"wms0*(\d{3,4})(?!\d)", blob, re.I)}
        return {n for n in found if n < 5000}

    def allocate_number(self, tid: int) -> int:
        self.fetch()
        number = max(self.used_numbers() | {self.store.max_reserved_number()}) + 1
        while not self.store.reserve_number(number, tid):
            number += 1
        return number

    # ===== шаги ========================================================================
    def step(self, tid: int) -> None:
        h = dict(self.store.data(tid).get("hotfix") or {"step": "start"})
        if self._pause_at_boundary(tid, h):
            return
        now = self.p.clock()
        if now < float(h.get("next_poll", 0)):
            return
        name = str(h.get("step"))
        handler = getattr(self, f"_s_{name}", None)
        if handler is None:
            return
        try:
            handler(tid, h)
        except StepFailed as exc:
            self.fail(tid, h, str(exc))
        except sandbox.SandboxUnavailable as exc:
            self.fail(tid, h, str(exc))
        except (LlmUnavailable, LlmError):
            raise  # очередь: стадия не меняется, повторится, когда модель вернётся

    def save(self, tid: int, h: dict[str, Any], **changes: Any) -> dict[str, Any]:
        """Сливает изменения в сохранённое состояние и обновляет h на месте (без устаревших копий)."""
        with self.store.transaction():
            current = dict(self.store.data(tid).get("hotfix") or {})
            current.update(changes)
            self.store.patch_data(tid, hotfix=current)
        h.clear()
        h.update(current)
        return h

    def _refresh(self, tid: int, h: dict[str, Any]) -> dict[str, Any]:
        current = dict(self.store.data(tid).get("hotfix") or {})
        h.clear()
        h.update(current)
        return h

    def _pause_at_boundary(self, tid: int, h: dict[str, Any]) -> bool:
        """Останавливает только между шагами; уже отправленный merge/deploy сначала выясняет."""
        self._refresh(tid, h)
        if not h.get("hold_requested"):
            return False
        step = str(h.get("step") or "start")
        if h.get("deploy_intent") and step in ("deploy", "verify"):
            return False
        if h.get("merge_intent") and not h.get("merged") and step == "merge":
            return False
        return self._pause_for_analysis(tid, h)

    def _pause_for_analysis(self, tid: int, h: dict[str, Any]) -> bool:
        """Атомарно сохраняет весь hotfix snapshot и передаёт накопленное поручение аналитику."""
        with self.store.transaction():
            if self.store.ticket(tid)["stage"] != "hotfix":
                return False
            d = self.store.data(tid)
            current = dict(d.get("hotfix") or {})
            if not current.get("hold_requested") or not d.get("resume_note"):
                return False
            step = str(current.get("step") or "start")
            current.update(hotfix_paused=True, resume_step=step, hold_requested=False)
            self.store.set_stage(
                tid, "analysis", hotfix=current, rev=int(d.get("rev", 0)) + 1,
                client_answer=None, preview_sha=None, hotfix_ok=False, verdict=None,
            )
            seq = int(current.get("hold_seq", 0))
            if step == "start":
                phase = "подготовку исправления ещё не начинаю"
            elif step == "report" and current.get("deploy_intent"):
                phase = "выкладка уже проверена; отчёт и сообщение клиенту пока не отправляю"
            elif current.get("merged") or step == "deploy":
                phase = "подготовленное исправление сохранено; выкладку пока не запускаю"
            else:
                phase = "закончил текущий этап и остановился перед выкладкой"
            self.p.say_owner(
                f"hotfix_hold:{tid}:{seq}",
                f"По обращению №{tid} достиг безопасной границы: {phase}. Подготовленное исправление "
                "сохранено; поручение передал аналитику.",
                tid,
            )
            h.clear()
            h.update(current)
            return True

    def _claim_intent(self, tid: int, h: dict[str, Any], **intent: Any) -> bool:
        """Линеаризует owner hold и внешний dispatch, не удерживая SQLite lock на внешнем вызове."""
        with self.store.transaction():
            d = self.store.data(tid)
            current = dict(d.get("hotfix") or {})
            if current.get("hold_requested"):
                h.clear()
                h.update(current)
                return False
            current.update(intent)
            self.store.patch_data(tid, hotfix=current)
            h.clear()
            h.update(current)
            return True

    def fail(self, tid: int, h: dict[str, Any], reason: str) -> None:
        """R25: не повторяем бесконечно; владельцу — что не вышло и что уже выложено."""
        with self.store.transaction():
            d = self.store.data(tid)
            current = dict(d.get("hotfix") or {})
            done = []
            if current.get("pr_url"):
                done.append(f"pull request создан ({current['pr_url']})")
            if current.get("merged"):
                done.append("изменение влито в основную ветку")
            if current.get("deploy_intent"):
                done.append("выкладка запускалась")
            state = "; ".join(done) if done else "ничего не выложено"
            failed = {**current, "step": "failed", "failure": reason}
            pending_hold = bool(current.get("hold_requested") and d.get("resume_note"))
            if pending_hold:
                failed.update(hotfix_paused=True, resume_step="failed", resume_blocked=True,
                              hold_requested=False)
                self.store.set_stage(
                    tid, "analysis", hotfix=failed, rev=int(d.get("rev", 0)) + 1,
                    client_answer=None, preview_sha=None, hotfix_ok=False, verdict=None,
                )
            else:
                self.store.set_stage(tid, "failed", hotfix=failed)
            if pending_hold:
                if current.get("deploy_intent"):
                    progress = "Выкладка запускалась, но её успешный результат не подтверждён."
                elif current.get("pr_url") or current.get("merged"):
                    progress = "Подготовленное исправление сохранено; выкладка не запускалась."
                else:
                    progress = "Исправление не выкладывалось."
                message = (
                    f"По обращению №{tid} не удалось надёжно завершить текущий этап. {progress} "
                    "Клиенту «пробуйте» не отправлялось. Сохранённое поручение передаю аналитику; "
                    "это действие автоматически не повторяю."
                )
            else:
                message = (
                    f"Хотфикс по обращению №{tid} ({self.p.seller_of(tid)}) остановлен: {reason}\n"
                    f"Что уже сделано: {state}. Клиенту «пробуйте» не отправлялось. Решение за вами, "
                    "предлагаю разобрать вручную."
                )
            self.p.say_owner(
                f"hotfix_fail:{tid}", message, tid,
            )

    # -- start -------------------------------------------------------------------------
    def _s_start(self, tid: int, h: dict[str, Any]) -> None:
        d = self.store.data(tid)
        # В1: форма — карточка «В работе» после «кати» (только карточка этого обращения).
        if d.get("form"):
            self.p.want_card(tid, "in_progress")
        number = h.get("number") or self.allocate_number(tid)
        self.save(tid, h, step="worktree", number=number)

    # -- worktree ----------------------------------------------------------------------
    def _s_worktree(self, tid: int, h: dict[str, Any]) -> None:
        number = h["number"]
        branch = f"hotfix/wms-{number}-support"
        path = Path(self.cfg.repo) / ".worktrees" / f"wms{number}-hotfix"
        self.ensure_worktree(branch, path)
        self.save(tid, h, step="dev", branch=branch, path=str(path))

    # -- разработчик -------------------------------------------------------------------
    def _request_text(self, tid: int) -> str:
        return self.p.ticket_context(tid)

    def _s_dev(self, tid: int, h: dict[str, Any]) -> None:
        d = self.store.data(tid)
        analysis = d.get("analysis") or {}
        frontend = bool((analysis.get("hotfix") or {}).get("touches_frontend"))
        number = f"WMS-{h['number']}"
        prompt = prompts.dev_prompt(number, self.cfg.hotfix.backend_bin, self._request_text(tid),
                                    json.dumps(analysis, ensure_ascii=False)[:6000])
        if frontend:
            self.link_node_modules(h["path"])
        res, result = self.p.llm.ask_json(
            "frontend" if frontend else "routine", prompt, ticket_id=tid, session_key="dev",
            mode="write", cwd=h["path"], timeout=3600,
        )
        self.save(tid, h, dev=res, dev_cli=result.cli, frontend=frontend)
        self.commit_dev(tid, h)
        self.save(tid, h, step="checks")

    def link_node_modules(self, path: str) -> None:
        """Зависимости фронта подключает диспетчер (у разработчика нет сети и установки пакетов)."""
        main = Path(self.cfg.repo) / "frontend" / "node_modules"
        target = Path(path) / "frontend" / "node_modules"
        if main.is_dir() and not target.exists():
            target.symlink_to(main)

    def commit_dev(self, tid: int, h: dict[str, Any]) -> None:
        """Коммит делает диспетчер: у сессии разработчика нет прав на git add/commit/push."""
        path = h["path"]
        number = f"WMS-{h['number']}"
        self.guard_gitdir(path)
        self.git("add", "-A", "--", ".", ":(exclude)frontend/node_modules", cwd=path)
        if not self.git("status", "--porcelain", cwd=path).strip():
            return
        summary = " ".join(str((h.get("dev") or {}).get("summary", "")).split())[:100]
        who = "Codex Sol <noreply@openai.com>" if h.get("dev_cli") == "codex" else (
            "Claude Sonnet <noreply@anthropic.com>")
        self.git("-c", "user.name=WMS support agent", "-c", "user.email=noreply@anthropic.com",
                 "commit", "--no-verify", "-m", f"{number}: {summary or 'облегчённый хотфикс'}",
                 "-m", f"Co-Authored-By: {who}", cwd=path)

    # -- проверки (делает сам диспетчер, не доверяя отчёту разработчика) ------------------
    def _s_checks(self, tid: int, h: dict[str, Any]) -> None:
        problems = self.verify_worktree(h)
        if not problems:
            again = not h.get("reviewed") or bool(h.get("review_defects"))
            self.save(tid, h, step="review" if again else "pr")
            return
        self.send_back(tid, h, "Проверка диспетчера нашла проблемы:\n- " + "\n- ".join(problems))

    def _dev_context(self, tid: int, h: dict[str, Any]) -> str:
        analysis = self.store.data(tid).get("analysis") or {}
        return prompts.dev_prompt(f"WMS-{h['number']}", self.cfg.hotfix.backend_bin,
                                  self._request_text(tid), json.dumps(analysis, ensure_ascii=False)[:6000])

    def send_back(
        self, tid: int, h: dict[str, Any], feedback: str, counter: str = "fix_rounds",
        limit: int = MAX_FIX_ROUNDS,
    ) -> None:
        """Замечание возвращается в ТУ ЖЕ сессию разработчика; затем снова проверки (без 2-го ревью)."""
        rounds = int(h.get(counter, 0))
        if rounds >= limit:
            raise StepFailed("не удалось быстро устранить замечания проверки: " + feedback[:300])
        self.save(tid, h, **{counter: rounds + 1})
        dev, _ = self.p.llm.ask_json(
            "frontend" if h.get("frontend") else "routine",
            feedback + "\nИсправь, повтори проверки, закоммить (с номером WMS в сообщении). "
            'Верни ТОЛЬКО JSON {"summary": "...", "test_files": ["путь"], "migration": false, '
            '"frontend": true|false, "client_scenario": "..."}',
            ticket_id=tid, session_key="dev", mode="write", cwd=h["path"], timeout=3600,
            context=self._dev_context(tid, h),
        )
        self.save(tid, h, dev={**(h.get("dev") or {}), **dev})
        self.commit_dev(tid, h)
        self.save(tid, h, step="checks")

    def verify_worktree(self, h: dict[str, Any]) -> list[str]:
        path, number = Path(h["path"]), f"WMS-{h['number']}"
        problems: list[str] = []
        self.guard_gitdir(path)
        names = self.git("diff", "--name-only", "origin/etalon...HEAD", cwd=path).split()
        if not names:
            return ["нет ни одного коммита с изменениями относительно origin/etalon"]
        if any("alembic/versions" in n or "migrations/" in n for n in names):
            raise StepFailed("правка требует миграцию базы: это не облегчённый хотфикс")
        forbidden = [n for n in names if n.startswith(FORBIDDEN_PATHS)]
        if forbidden:
            raise StepFailed(
                "правка затрагивает выкладку, CI или настройки агентов, это не хотфикс: "
                + ", ".join(forbidden[:3])
            )
        subjects = self.git("log", "origin/etalon..HEAD", "--format=%s", cwd=path).splitlines()
        if not all(number in s for s in subjects):
            problems.append(f"в каждом сообщении коммита должен быть номер {number}")
        backlog = path / "docs" / "KANONICHESKIY_BACKLOG.md"
        if not backlog.exists() or not re.search(
            rf"^## {number} ", backlog.read_text(encoding="utf-8"), re.MULTILINE
        ):
            problems.append(f"в docs/KANONICHESKIY_BACKLOG.md нет заголовка «## {number} · название»")
        doc = path / "docs" / "requirements" / f"{number}.md"
        if f"docs/requirements/{number}.md" not in names or not doc.exists():
            problems.append(f"нет документа docs/requirements/{number}.md")
        else:
            text = doc.read_text(encoding="utf-8")
            if "Вердикт" not in text or "Заключение" not in text:
                problems.append(
                    f"в {number}.md нужны таблица проверок со столбцом «Вердикт» и раздел «Заключение»"
                )
        tests = [n for n in names if re.search(r"(^|/)(tests?/|test_|.*\.test\.|.*\.spec\.)", n)]
        if not tests:
            problems.append("нет теста, воспроизводящего дефект")
        backend_tests = [n.removeprefix("backend/") for n in tests if n.startswith("backend/tests/")]
        if any(n.startswith("backend/") for n in names):
            problems += self._backend_checks(path, backend_tests)
        return problems

    def _backend_checks(self, path: Path, backend_tests: list[str]) -> list[str]:
        bin_dir = self.cfg.hotfix.backend_bin
        backend = path / "backend"

        def tool(name: str) -> str:
            return str(Path(bin_dir) / name) if bin_dir else name

        problems = []
        for argv in ([tool("ruff"), "check", "."], [tool("mypy"), "."]):
            res = self.run_untrusted(argv, path, backend, 900)
            if res.rc != 0:
                problems.append(f"{Path(argv[0]).name} не проходит: {(res.out + res.err)[-400:]}")
        if backend_tests:
            res = self.run_untrusted(
                [tool("pytest"), "-n", "auto", "-q", "-p", "no:cacheprovider", *backend_tests],
                path, backend, 1800,
            )
            if res.rc != 0:
                problems.append(f"целевые тесты не проходят: {(res.out + res.err)[-500:]}")
            elif not self.test_fails_on_base(path, backend_tests):
                problems.append("тест проходит и без правки: он не воспроизводит дефект")
        return problems

    def test_fails_on_base(self, path: Path, tests: list[str]) -> bool:
        """«Падает до правки»: те же тесты на чистом origin/etalon обязаны упасть."""
        base = path.parent / f"{path.name}-base"
        try:
            self.git("worktree", "add", "--detach", str(base), "origin/etalon")
            self.guard_gitdir(base)
            for rel in tests:
                dest = base / "backend" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text((path / "backend" / rel).read_text(encoding="utf-8"), encoding="utf-8")
            bin_dir = self.cfg.hotfix.backend_bin
            pytest = str(Path(bin_dir) / "pytest") if bin_dir else "pytest"
            res = self.run_untrusted([pytest, "-q", "-p", "no:cacheprovider", *tests], base,
                                     base / "backend", 1800)
            return res.rc != 0
        finally:
            self.run(["git", "worktree", "remove", "--force", str(base)])

    # -- одна перекрёстная проверка -------------------------------------------------------
    def _s_review(self, tid: int, h: dict[str, Any]) -> None:
        """Обязательная проверка другой моделью. Недоступна — стоим в очереди (LlmUnavailable
        уходит наверх, владелец получает уведомление), а не идём в PR без ревью (F6). Подтверждённые
        дефекты после исправления перепроверяются именно по ним, до PR."""
        number = f"WMS-{h['number']}"
        pending = list(h.get("review_defects") or [])
        prompt = (
            prompts.recheck_prompt(number, pending) if pending
            else prompts.review_prompt(number, str((h.get("dev") or {}).get("summary", "")))
        )
        try:
            res, result = self.p.llm.ask_json(
                "review", prompt, ticket_id=tid, mode="readonly", cwd=h["path"],
                exclude_cli=h.get("dev_cli"),
            )
        except LlmError:
            raise StepFailed(
                "перекрёстная проверка вернула непонятный ответ: хотфикс без ревью не иду"
            ) from None
        blockers = [str(x.get("text", "")) for x in res.get("defects") or []
                    if x.get("severity") == "blocker"]
        h = self.save(tid, h, reviewed=True, review_by=result.model, review_defects=blockers)
        if blockers:
            self.send_back(tid, h, "Перекрёстная проверка нашла подтверждённые дефекты:\n- "
                           + "\n- ".join(blockers))  # после правки — проверки и перепроверка этих дефектов
        else:
            self.save(tid, h, step="pr")

    # -- pull request ---------------------------------------------------------------------
    def _s_pr(self, tid: int, h: dict[str, Any]) -> None:
        number, branch = f"WMS-{h['number']}", h["branch"]
        self.fetch()
        if self._number_collides(h):
            raise StepFailed(f"номер {number} уже занят в origin/etalon параллельной работой")
        self.push_branch(branch)
        title = f"fix({number}): {self.p.title_of(tid)}"[:100]
        body = (f"Облегчённый хотфикс по «кати» владельца (WMS-641).\n\n"
                f"{(h.get('dev') or {}).get('summary', '')}\n\n"
                "Приёмка аналитика не проводилась.\n\n"
                "🤖 Generated with [Claude Code](https://claude.com/claude-code)")
        found = self.ensure_pr(branch, base="etalon", title=title, body=body)
        self.save(tid, h, step="ci", pr=found["number"], pr_url=found["url"],
                  ci_started=self.p.clock())

    def _number_collides(self, h: dict[str, Any]) -> bool:
        backlog = self.run(["git", "show", "origin/etalon:docs/KANONICHESKIY_BACKLOG.md"]).out
        return f"WMS-{h['number']}" in backlog

    # -- CI -------------------------------------------------------------------------------
    def _s_ci(self, tid: int, h: dict[str, Any]) -> None:
        # gh pr checks возвращает код 8 (ждём) и 1 (упало) и при --json: разбираем вывод, не код.
        checks = self.pr_checks(h["pr"])
        buckets = {c["bucket"] for c in checks}
        now = self.p.clock()
        if checks and "fail" in buckets:
            failed = ", ".join(c["name"] for c in checks if c["bucket"] == "fail")
            self.send_back(tid, h, f"CI красный: {failed}. Выясни, связано ли это с твоей правкой, "
                                   "исправь (с тестом) и закоммить.", counter="ci_fix_rounds", limit=1)
            return
        if checks and buckets <= {"pass", "skipping"}:
            self.save(tid, h, step="merge")
            return
        if now - float(h.get("ci_started", now)) > self.cfg.limits.ci_timeout_sec:
            raise StepFailed("CI не завершился за отведённое время")
        self.save(tid, h, next_poll=now + 30)

    # -- merge (разрешение — «кати» по этому обращению) -----------------------------------
    def deployed_sha(self) -> str:
        cmd = self.cfg.hotfix.deployed_sha_cmd
        if not cmd:
            raise StepFailed("не настроена проверка версии на сервере (hotfix.deployed_sha_cmd)")
        out = self.must(["bash", "-lc", cmd], timeout=60).strip().splitlines()
        if not out or not re.fullmatch(r"[0-9a-f]{40}", out[-1]):
            raise StepFailed("не удалось определить версию на сервере")
        return out[-1]

    def _s_merge(self, tid: int, h: dict[str, Any]) -> None:
        pr = str(h["pr"])
        view = json.loads(self.must_gh(["gh", "pr", "view", pr, "--json", "state,mergeCommit"], h["path"]))
        if view.get("state") != "MERGED":
            if h.get("merge_intent"):
                if view.get("state") != "OPEN":
                    raise StepFailed(f"слияние завершилось в состоянии {view.get('state')}, не MERGED")
                if self.p.clock() - float(h.get("merge_ts", self.p.clock())) > MERGE_LOOKUP_SEC:
                    raise StepFailed(
                        "намерение слить pull request сохранено, но слияние не подтверждено; "
                        "повторно команду не запускаю"
                    )
                self.save(tid, h, next_poll=self.p.clock() + 10)
                return
            self.fetch()
            deployed = self.deployed_sha()
            extra = int(self.git("rev-list", "--count", f"{deployed}..origin/etalon").strip() or 0)
            if extra and not self.cfg.hotfix.allow_foreign_commits:
                raise StepFailed(
                    f"в etalon есть {extra} ещё не выложенных изменений, не относящихся к хотфиксу: "
                    "штатная выкладка выкатит всё вместе, без вашего решения не делаю"
                )
            if self.cfg.hotfix.preflight_cmd:
                self.must(["bash", "-lc", self.cfg.hotfix.preflight_cmd], timeout=120)
            if not self._claim_intent(tid, h, merge_intent=True, merge_ts=self.p.clock()):
                self._pause_for_analysis(tid, h)
                return
            # После durable intent код выхода не доказывает исход: сначала перечитываем PR и не
            # повторяем merge вслепую при потерянном ответе GitHub.
            self.run_gh(["gh", "pr", "merge", pr, f"--{self.cfg.hotfix.merge_method}"], h["path"])
            view = json.loads(self.must_gh(["gh", "pr", "view", pr, "--json", "state,mergeCommit"],
                                        h["path"]))
            if view.get("state") != "MERGED":
                self.save(tid, h, next_poll=self.p.clock() + 10)
                return
        oid = str((view.get("mergeCommit") or {}).get("oid") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise StepFailed("не удалось определить коммит слияния хотфикса")
        self.save(tid, h, step="deploy", merged=True, merge_sha=oid)

    # -- deploy ---------------------------------------------------------------------------
    def _runs(self) -> list[dict[str, Any]]:
        """Список запусков выкладки. Ошибка чтения НЕ превращается в пустой список (F5)."""
        res = self.run_gh(["gh", "run", "list", "--workflow", "deploy.yml", "--branch", "etalon",
                           "--limit", "30", "--json",
                           "databaseId,displayTitle,status,conclusion,createdAt,event"])
        try:
            runs = json.loads(res.out)
        except ValueError:
            runs = None
        if res.rc != 0 or not isinstance(runs, list):
            raise RunsUnreadable("список запусков выкладки не прочитан")
        return runs

    def foreign_commits(self, deployed: str, merge_sha: str) -> list[str]:
        """Коммиты, которые выложатся вместе с хотфиксом, кроме самого слияния и его ветки."""
        commits = set(self.git("rev-list", f"{deployed}..{merge_sha}").split())
        parents = self.git("rev-list", "--parents", "-n", "1", merge_sha).split()
        allowed = {merge_sha}
        if len(parents) == 3:  # обычное слияние: первый родитель — etalon, второй — ветка хотфикса
            allowed |= set(self.git("rev-list", f"{parents[1]}..{parents[2]}").split())
        return sorted(commits - allowed)

    def _s_deploy(self, tid: int, h: dict[str, Any]) -> None:
        """Штатный workflow получает merge_sha и attempt_id (необязательные inputs deploy.yml): сервер
        выкатывает ровно этот коммит, а запуск опознаётся только по attempt_id в его имени.
        Намерение записывается ДО запуска; неизвестный исход не повторяется, а останавливает (F4, F5)."""
        now = self.p.clock()
        if not h.get("deploy_intent"):
            self.fetch()
            sha = h["merge_sha"]
            if self.run(["git", "merge-base", "--is-ancestor", sha, "origin/etalon"]).rc != 0:
                raise StepFailed("коммит слияния хотфикса не найден в origin/etalon")
            workflow = self.run(["git", "show", "origin/etalon:.github/workflows/deploy.yml"]).out
            if "attempt_id" not in workflow:
                raise StepFailed("deploy.yml в etalon не принимает sha и attempt_id: закрепить версию "
                                 "выкладки нельзя, без вашего решения не запускаю")
            script = self.run(["git", "show", f"{sha}:scripts/deploy/prod-update.sh"]).out
            if "WMS_DEPLOY_SHA" not in script:
                raise StepFailed("скрипт выкладки в коммите хотфикса не поддерживает закреплённую версию: "
                                 "без вашего решения не запускаю")
            extra = self.foreign_commits(self.deployed_sha(), sha)
            if extra and not self.cfg.hotfix.allow_foreign_commits:
                raise StepFailed(f"вместе с хотфиксом выложились бы ещё {len(extra)} чужих изменений: "
                                 "без вашего решения не запускаю")
            attempt = "wms641-" + uuid.uuid4().hex[:12]
            if not self._claim_intent(
                tid, h, deploy_intent=True, attempt_id=attempt, deploy_ts=now
            ):
                self._pause_for_analysis(tid, h)
                return
            # Код выхода не важен: исход выясняется чтением списка запусков, повторно не запускаем.
            self.run_gh(["gh", "workflow", "run", "deploy.yml", "--ref", "etalon", "-f", f"sha={sha}",
                         "-f", f"attempt_id={attempt}"])
        try:
            runs = self._runs()
        except RunsUnreadable:
            self._wait_or_fail(tid, h, now, "список запусков выкладки не читается")
            return
        own = [r for r in runs if h["attempt_id"] in str(r.get("displayTitle", ""))]
        if len(own) > 1:
            raise StepFailed("запусков с моим attempt_id несколько, исход неоднозначен: не продолжаю")
        if not own:
            self._wait_or_fail(tid, h, now, "запуск выкладки с моим attempt_id не найден (мог не уйти или "
                               "уйти без ответа): повторно не запускаю, проверьте Actions вручную")
            return
        run = own[0]
        if run.get("status") != "completed":
            if now - float(h.get("deploy_ts", now)) > self.cfg.limits.deploy_timeout_sec:
                raise StepFailed("выкладка не завершилась за отведённое время")
            self.save(tid, h, deploy_run_id=run["databaseId"], next_poll=now + 20)
            return
        if run.get("conclusion") != "success":
            raise StepFailed(f"выкладка завершилась неуспешно ({run.get('conclusion')})")
        self.save(tid, h, step="verify", deploy_run_id=run["databaseId"])

    def _wait_or_fail(self, tid: int, h: dict[str, Any], now: float, reason: str) -> None:
        if now - float(h.get("deploy_ts", now)) > DEPLOY_LOOKUP_SEC:
            raise StepFailed(f"{reason}; запуск не подтверждён")
        self.save(tid, h, next_poll=now + 10)

    # -- проверка версии ------------------------------------------------------------------
    def _s_verify(self, tid: int, h: dict[str, Any]) -> None:
        """На сервере должен быть именно разрешённый коммит слияния, а не «текущий etalon»."""
        deployed = self.deployed_sha()
        if deployed != h["merge_sha"]:
            raise StepFailed(
                f"на сервере версия {deployed[:8]}, а разрешён хотфикс {h['merge_sha'][:8]}: выложено не "
                "то, что вы разрешили (возможно, вместе с чужими изменениями). Успехом не считаю"
            )
        base = self.cfg.hotfix.public_base_url.rstrip("/")
        for path in ("/", "/seller/", "/api/health"):
            try:
                code = self.http.get(base + path, timeout=20).status_code
            except httpx.HTTPError:
                code = 0
            if code != 200:
                raise StepFailed(f"адрес {path} отвечает {code}, а не 200")
        self.save(tid, h, step="report", verified_sha=deployed)

    # -- отчёт, «пробуйте» ----------------------------------------------------------------
    def _s_report(self, tid: int, h: dict[str, Any]) -> None:
        d = self.store.data(tid)
        dev = h.get("dev") or {}
        facts = (
            f"Что сделано: {dev.get('summary', '')}\n"
            "Как проверено: тест на дефект падал до правки и проходит после, проверки качества "
            "кода, проверка другой моделью, CI зелёный, версия на сервере совпадает с разрешённым "
            "коммитом слияния, главные адреса отвечают.\n"
            "Чего не проверено: сценарий клиента автоматически не повторялся "
            f"({dev.get('client_scenario', '')})."
        )
        try:
            body = self.p.llm.ask(
                "routine",
                "Составь для владельца склада короткий отчёт о выложенном исправлении: что "
                "исправлено по шагам клиента, как проверено, чего не проверено. Бизнес-язык, без "
                f"артикулов, кода и технических деталей.\n\n{prompts.wrap(facts)}", ticket_id=tid,
            ).text.strip()
        except (LlmUnavailable, LlmError):
            body = facts
        t = self.store.ticket(tid)
        client_text: str | None = None
        reply_to: str | None = None
        if not d.get("form") and t["chat_id"]:
            first = self.store.ticket_messages(tid)
            reply_to = first[0]["msg_id"] if first else None
            try:
                client_text = self.p.llm.ask("routine", prompts.client_done_prompt(
                    json.dumps(d.get("analysis", {}), ensure_ascii=False)), ticket_id=tid).text.strip()
            except (LlmUnavailable, LlmError):
                client_text = "Мы исправили проблему. Попробуйте, пожалуйста, ещё раз."
        card_note = ""
        if d.get("form"):  # В1: форма — карточка «Готово»; перенос доводится позже, если связи ещё нет
            self.p.want_card(tid, "completed")
            if self.store.data(tid).get("card_applied") != "completed":
                card_note = ("\nКарточка формы в Trello пока не обновлена (связь ещё не появилась или "
                             "Trello не ответил): «Готово» проставлю, как только получится.")
        pause = False
        with self.store.transaction():
            live_d = self.store.data(tid)
            live_h = dict(live_d.get("hotfix") or {})
            if live_h.get("hold_requested"):
                pause = True
                h.clear()
                h.update(live_h)
            else:
                self.p.say_owner(
                    f"hotfix_report:{tid}",
                    f"Исправление по обращению №{tid} ({self.p.seller_of(tid)}) выложено.\n\n"
                    f"{body}{card_note}\n\n{HONEST_STATUS}", tid, "report",
                )
                if client_text is not None:
                    then = {"stage": "done", "patch": {"hotfix": {**live_h, "step": "done"}}}
                    # Локальные outbox + stage фиксируются одной transaction с последней hold-проверкой.
                    if self.p.send_client_gated(
                        tid, f"t{tid}:tryit", client_text, reply_to, then
                    ):
                        self.p.apply_then(tid, then)
                else:
                    self.store.set_stage(tid, "done", hotfix={**live_h, "step": "done"})
        if pause:
            self._pause_for_analysis(tid, h)
