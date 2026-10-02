"""Облегчённый хотфикс (WMS-639, раздел 5): только после «кати» владельца по этому обращению.

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
from pathlib import Path
from typing import Any

import httpx

from . import prompts, sandbox
from .llm import ExecFn, ExecResult, LlmError, LlmUnavailable, default_exec
from .pipeline import Pipeline

log = logging.getLogger(__name__)
MAX_FIX_ROUNDS = 2
DEPLOY_LOOKUP_SEC = 120
FORBIDDEN_PATHS = (".github/", "scripts/deploy/", "scripts/ci/", ".claude/", ".cursor/",
                   "docker-compose", "deploy/", "tools/support_agent/")
HONEST_STATUS = "Статус: выложено в облегчённом режиме, приёмка аналитика не проводилась."


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

    def git(self, *args: str, cwd: str | Path | None = None) -> str:
        return self.must(["git", *args], cwd)

    def fetch(self) -> None:
        self.git("fetch", "origin")

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
        gh = self.run(["gh", "pr", "list", "--state", "all", "--limit", "200", "--json",
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
        current = dict(self.store.data(tid).get("hotfix") or {})
        current.update(changes)
        self.store.patch_data(tid, hotfix=current)
        h.clear()
        h.update(current)
        return h

    def fail(self, tid: int, h: dict[str, Any], reason: str) -> None:
        """R25: не повторяем бесконечно; владельцу — что не вышло и что уже выложено."""
        done = []
        if h.get("pr_url"):
            done.append(f"pull request создан ({h['pr_url']})")
        if h.get("merged"):
            done.append("изменение влито в основную ветку")
        if h.get("deploy_intent"):
            done.append("выкладка запускалась")
        state = "; ".join(done) if done else "ничего не выложено"
        self.store.set_stage(tid, "failed", hotfix={**h, "step": "failed", "failure": reason})
        self.p.say_owner(
            f"hotfix_fail:{tid}",
            f"Хотфикс по обращению №{tid} ({self.p.seller_of(tid)}) остановлен: {reason}\n"
            f"Что уже сделано: {state}. Клиенту «пробуйте» не отправлялось. "
            "Решение за вами, предлагаю разобрать вручную.",
            tid,
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
        self.fetch()
        if not path.exists():
            self.git("worktree", "add", "-b", branch, str(path), "origin/etalon")
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
        self.git("add", "-A", "--", ".", ":(exclude)frontend/node_modules", cwd=path)
        if not self.must(["git", "status", "--porcelain"], path).strip():
            return
        summary = " ".join(str((h.get("dev") or {}).get("summary", "")).split())[:100]
        who = "Codex Sol <noreply@openai.com>" if h.get("dev_cli") == "codex" else (
            "Claude Sonnet <noreply@anthropic.com>")
        self.git("commit", "-m", f"{number}: {summary or 'облегчённый хотфикс'}",
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
        number, branch, path = f"WMS-{h['number']}", h["branch"], h["path"]
        self.fetch()
        if self._number_collides(h):
            raise StepFailed(f"номер {number} уже занят в origin/etalon параллельной работой")
        self.git("push", "-u", "origin", branch, cwd=path)  # повторный push безопасен
        existing = self.run(["gh", "pr", "list", "--head", branch, "--state", "all", "--json",
                             "number,url"], path)
        found = json.loads(existing.out) if existing.rc == 0 and existing.out.strip() else []
        if not found:
            title = f"fix({number}): {self.p.title_of(tid)}"[:100]
            body = (f"Облегчённый хотфикс по «кати» владельца (WMS-639).\n\n"
                    f"{(h.get('dev') or {}).get('summary', '')}\n\n"
                    "Приёмка аналитика не проводилась.\n\n"
                    "🤖 Generated with [Claude Code](https://claude.com/claude-code)")
            self.must(["gh", "pr", "create", "--base", "etalon", "--head", branch, "--title", title,
                       "--body", body], path)
            existing = self.run(["gh", "pr", "list", "--head", branch, "--state", "all", "--json",
                                 "number,url"], path)
            found = json.loads(existing.out or "[]")
        if not found:
            raise StepFailed("pull request не удалось найти после создания")
        self.save(tid, h, step="ci", pr=found[0]["number"], pr_url=found[0]["url"],
                  ci_started=self.p.clock())

    def _number_collides(self, h: dict[str, Any]) -> bool:
        backlog = self.run(["git", "show", "origin/etalon:docs/KANONICHESKIY_BACKLOG.md"]).out
        return f"WMS-{h['number']}" in backlog

    # -- CI -------------------------------------------------------------------------------
    def _s_ci(self, tid: int, h: dict[str, Any]) -> None:
        # gh pr checks возвращает код 8 (ждём) и 1 (упало) и при --json: разбираем вывод, не код.
        res = self.run(["gh", "pr", "checks", str(h["pr"]), "--json", "name,bucket"], h["path"])
        try:
            checks = json.loads(res.out or "[]")
        except ValueError:
            raise StepFailed("не удалось прочитать состояние CI") from None
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
        view = json.loads(self.must(["gh", "pr", "view", pr, "--json", "state,mergeCommit"], h["path"]))
        if view.get("state") != "MERGED":
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
            self.must(["gh", "pr", "merge", pr, f"--{self.cfg.hotfix.merge_method}"], h["path"])
            view = json.loads(self.must(["gh", "pr", "view", pr, "--json", "state,mergeCommit"],
                                        h["path"]))
        oid = str((view.get("mergeCommit") or {}).get("oid") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise StepFailed("не удалось определить коммит слияния хотфикса")
        self.save(tid, h, step="deploy", merged=True, merge_sha=oid)

    # -- deploy ---------------------------------------------------------------------------
    def _runs(self, path: str) -> list[dict[str, Any]]:
        res = self.run(["gh", "run", "list", "--workflow", "deploy.yml", "--branch", "etalon",
                        "--limit", "20", "--json", "databaseId,status,conclusion,createdAt,event"],
                       path)
        return json.loads(res.out) if res.rc == 0 and res.out.strip() else []

    def _s_deploy(self, tid: int, h: dict[str, Any]) -> None:
        """Штатный workflow выкатывает ТЕКУЩУЮ вершину etalon (deploy.yml без входных параметров),
        поэтому: версия фиксируется как merge_sha; перед запуском вершина обязана совпасть с ним; намерение
        записывается ДО запуска; свой запуск опознаётся по новому id, а не по времени; после
        перезапуска запуск повторно не отправляется (F4, F5)."""
        now = self.p.clock()
        if not h.get("deploy_intent"):
            self.fetch()
            etalon = self.git("rev-parse", "origin/etalon").strip()
            if etalon != h["merge_sha"]:
                raise StepFailed(
                    f"после слияния хотфикса в etalon появились другие изменения ({etalon[:8]} вместо "
                    f"{h['merge_sha'][:8]}): штатная выкладка выкатит и их, без вашего решения не запускаю"
                )
            before = [r["databaseId"] for r in self._runs(h["path"])]
            self.save(tid, h, deploy_intent=True, runs_before=before, deploy_ts=now)  # до запуска
            # Код выхода не важен: исход выясняется чтением списка запусков, повторно не запускаем.
            self.run(["gh", "workflow", "run", "deploy.yml", "--ref", "etalon"], h["path"])
        if not h.get("deploy_run_id"):
            new = [r for r in self._runs(h["path"])
                   if r["databaseId"] not in h.get("runs_before", [])
                   and r.get("event") == "workflow_dispatch"]
            if len(new) > 1:
                raise StepFailed("появилось несколько новых запусков выкладки, свой опознать нельзя")
            if not new:
                if now - float(h.get("deploy_ts", now)) > DEPLOY_LOOKUP_SEC:
                    raise StepFailed("запуск выкладки не подтверждён (мог не уйти или уйти без ответа): "
                                     "повторно не запускаю, проверьте Actions вручную")
                self.save(tid, h, next_poll=now + 10)
                return
            self.save(tid, h, deploy_run_id=new[0]["databaseId"], deploy_wait_from=now)
        run = next((r for r in self._runs(h["path"]) if r["databaseId"] == h["deploy_run_id"]), None)
        if run is None or run.get("status") != "completed":
            if now - float(h.get("deploy_wait_from", now)) > self.cfg.limits.deploy_timeout_sec:
                raise StepFailed("выкладка не завершилась за отведённое время")
            self.save(tid, h, next_poll=now + 20)
            return
        if run.get("conclusion") != "success":
            raise StepFailed(f"выкладка завершилась неуспешно ({run.get('conclusion')})")
        self.save(tid, h, step="verify")

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
        card_note = ""
        if d.get("form"):  # В1: форма — карточка «Готово»; перенос доводится позже, если связи ещё нет
            self.p.want_card(tid, "completed")
            if self.store.data(tid).get("card_applied") != "completed":
                card_note = ("\nКарточка формы в Trello пока не обновлена (связь ещё не появилась или "
                             "Trello не ответил): «Готово» проставлю, как только получится.")
        self.p.say_owner(
            f"hotfix_report:{tid}",
            f"Исправление по обращению №{tid} ({self.p.seller_of(tid)}) выложено.\n\n{body}{card_note}"
            f"\n\n{HONEST_STATUS}", tid, "report",
        )
        if not d.get("form") and t["chat_id"]:
            first = self.store.ticket_messages(tid)
            try:
                text = self.p.llm.ask("routine", prompts.client_done_prompt(
                    json.dumps(d.get("analysis", {}), ensure_ascii=False)), ticket_id=tid).text.strip()
            except (LlmUnavailable, LlmError):
                text = "Мы исправили проблему. Попробуйте, пожалуйста, ещё раз."
            self.p.say_client(f"t{tid}:tryit", t["chat_id"], text,
                              first[0]["msg_id"] if first else None, tid)  # один раз на обращение
        self.store.set_stage(tid, "done", hotfix={**h, "step": "done"})

