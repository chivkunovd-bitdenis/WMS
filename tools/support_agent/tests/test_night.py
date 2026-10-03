"""WMS-652: fixed overnight stage; every model/git/gh call is a fake."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from support_agent.llm import ExecResult
from support_agent.night import NightRunner

from .conftest import ok


class FakeHotfix:
    def __init__(self, *, etalon: str = "green") -> None:
        self.etalon = etalon
        self.calls: list[tuple[str, list[str]]] = []
        self.release_calls: list[str] = []
        self.p: Any = None

    def git(self, *args: str, cwd: str | Path | None = None) -> str:
        self.calls.append(("git", list(args)))
        if args[:2] == ("rev-parse", "origin/etalon"):
            return "a" * 40
        if args[:2] == ("rev-parse", "HEAD"):
            return "b" * 40
        if args[:2] == ("status", "--porcelain"):
            return ""
        return ""

    def run_gh(self, argv: list[str], cwd: str | Path | None = None,
               timeout: int = 300) -> ExecResult:
        self.calls.append(("gh", argv))
        if argv[:4] == ["gh", "run", "list", "--workflow"]:
            return ok(out=json.dumps([{"databaseId": 1, "headSha": "a" * 40,
                                       "status": "completed",
                                       "conclusion": "success" if self.etalon == "green" else "failure",
                                       "displayTitle": "backend"}]))
        if argv[:4] == ["gh", "run", "view", "1"]:
            return ok(out=json.dumps({"jobs": [
                {"name": name, "conclusion": "success"}
                for name in ("baseline", "backlog", "backend", "frontend-build", "охрана")
            ]}))
        if argv[:3] == ["gh", "pr", "checks"]:
            return ok(out=json.dumps([{"name": "backend", "bucket": "fail"}]))
        return ok(out="[]")

    def run(self, argv: list[str], cwd: str | Path | None = None,
            timeout: int = 300) -> ExecResult:
        self.calls.append(("run", argv))
        return ok()

    def fetch(self) -> None:
        self.calls.append(("git", ["fetch"]))

    def ensure_worktree(self, branch: str, path: str | Path,
                        base: str = "origin/etalon") -> Path:
        self.calls.append(("git", ["worktree", branch, str(path), base]))
        return Path(path)

    def push_branch(self, branch: str) -> None:
        self.calls.append(("git", ["push", branch]))

    def link_node_modules(self, path: str) -> None:
        self.calls.append(("node_modules", [path]))

    def ensure_pr(self, branch: str, *, base: str, title: str, body: str) -> dict[str, Any]:
        self.calls.append(("gh", ["pr", branch, base, title, body]))
        return {"number": 9, "url": "https://example.test/pr/9"}

    def pr_checks(self, pr: int | str) -> list[dict[str, Any]]:
        self.calls.append(("gh", ["checks", str(pr)]))
        return [{"name": "backend", "bucket": "fail"}]

    def guard_gitdir(self, path: str | Path) -> None:
        return None

    def run_untrusted(self, argv: list[str], worktree: str | Path,
                      cwd: str | Path, timeout: int = 900) -> ExecResult:
        self.calls.append(("test", argv))
        return ok()

    def _s_merge(self, tid: int, state: dict[str, Any]) -> None:
        self.release_calls.append("merge")
        self.p.store.patch_data(tid, hotfix={**state, "step": "deploy", "merge_sha": "c" * 40})

    def _s_deploy(self, tid: int, state: dict[str, Any]) -> None:
        self.release_calls.append("deploy")
        self.p.store.patch_data(tid, hotfix={**state, "step": "verify", "merge_sha": "c" * 40})

    def _s_verify(self, tid: int, state: dict[str, Any]) -> None:
        self.release_calls.append("verify")
        self.p.store.patch_data(tid, hotfix={**state, "step": "report", "merge_sha": "c" * 40})


class RealGitHotfix(FakeHotfix):
    def git(self, *args: str, cwd: str | Path | None = None) -> str:
        self.calls.append(("git", list(args)))
        result = subprocess.run(
            ["git", *args], cwd=cwd, env={**os.environ, "LC_ALL": "C"},
            check=True, capture_output=True, text=True,
        )
        return result.stdout


def make_night(env: Any, *, etalon: str = "green", release: bool = True) -> tuple[NightRunner, int]:
    task = env.store.add_ticket(kind="agent_task", source="telegram", chat_id=-100,
                                seller="seller", stage="agent_discussion",
                                data={"agent": {"wms_number": 700}})
    env.store.kv_set("agent_job:job1", {
        "id": "job1", "task_ids": ["WMS-700"], "release_authorized": release,
        "deadline_at": None, "status": "queued",
        "task_snapshot": {"WMS-700": {"ticket_id": task, "is_frontend": False}},
    })
    fake = FakeHotfix(etalon=etalon)
    fake.p = env.pipe
    runner = NightRunner(env.pipe, fake)  # type: ignore[arg-type]
    env.pipe.night = runner
    return runner, runner.ensure_job("job1")


def test_night_stages_are_registered_and_job_is_durable(env: Any) -> None:
    runner, tid = make_night(env)
    assert {"development", "release", "report"} <= set(env.pipe.stages)
    assert runner.ensure_job("job1") == tid
    assert env.store.kv_get("agent_job:job1")["night_ticket_id"] == tid
    assert env.store.ticket(tid)["stage"] == "development"


def test_red_etalon_stops_before_any_task_or_model_call(env: Any) -> None:
    runner, tid = make_night(env, etalon="red")
    runner.development(tid)
    state = env.store.data(tid)["night"]
    assert state["tasks"]["WMS-700"]["status"] == "stopped"
    assert env.store.ticket(tid)["stage"] == "report"
    assert env.store.outbox_by_key("night_etalon_red:job1:" + "a" * 40) is not None
    assert env.llm.calls == []


def test_developer_contradiction_waits_for_owner_without_commit(env: Any, tmp_path: Path) -> None:
    runner, tid = make_night(env)
    root = tmp_path / "task"
    root.mkdir()
    state = env.store.data(tid)["night"]
    state["step"] = "tasks"
    state["tasks"]["WMS-700"].update(step="developer", path=str(root))
    env.store.patch_data(tid, night=state)
    env.llm.on("routine", "Ты разработчик WMS-700",
               {"summary": "", "contradiction": "C3 противоречит R2"})
    runner.development(tid)
    task = env.store.data(tid)["night"]["tasks"]["WMS-700"]
    assert task["status"] == "waiting_owner"
    assert "C3" in task["reason"]
    assert not [call for call in runner.hotfix.calls if call[0] == "git" and "commit" in call[1]]


def test_same_failure_without_new_commit_stops_task(env: Any, tmp_path: Path) -> None:
    runner, tid = make_night(env)
    root = tmp_path / "task"
    root.mkdir()
    state = env.store.data(tid)["night"]
    state["step"] = "tasks"
    state["tasks"]["WMS-700"].update(step="developer", path=str(root),
                                              feedback="CI красный: backend")
    env.store.patch_data(tid, night=state)
    env.llm.on("routine", "Ты разработчик WMS-700",
               {"summary": "нечего менять", "contradiction": ""})
    runner.development(tid)
    task = env.store.data(tid)["night"]["tasks"]["WMS-700"]
    assert task["status"] == "stopped"
    assert "без изменения кода" in task["reason"]


def test_analyst_document_and_tester_contract_are_separate_commits(
    env: Any, tmp_path: Path,
) -> None:
    runner, tid = make_night(env)
    root = tmp_path / "task"
    doc = root / "docs" / "requirements" / "WMS-700.md"
    test_file = root / "backend" / "tests" / "test_wms_700_contract.py"
    doc.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    doc.write_text("# WMS-700\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.test",
         "commit", "-qm", "baseline"], cwd=root, check=True,
    )
    hotfix = RealGitHotfix()
    hotfix.p = env.pipe
    runner.hotfix = hotfix  # type: ignore[assignment]
    state = env.store.data(tid)["night"]
    state["step"] = "tasks"
    state["tasks"]["WMS-700"].update(step="analyst", path=str(root))
    env.store.patch_data(tid, night=state)

    def analyst(_: str, __: dict[str, Any]) -> dict[str, Any]:
        doc.write_text("# WMS-700\n\n| Класс | Тест |\n|---|---|\n", encoding="utf-8")
        return {"summary": "проверки добавлены", "checks": ["C1"]}

    def tester(_: str, __: dict[str, Any]) -> dict[str, Any]:
        test_file.write_text("def test_contract():\n    assert True\n", encoding="utf-8")
        return {"summary": "контракт добавлен", "tests": [
            "backend/tests/test_wms_700_contract.py",
        ]}

    env.llm.on("analyst", "Ты аналитик WMS-700", analyst)
    env.llm.on("routine", "Ты тестировщик WMS-700", tester)
    runner.development(tid)
    runner.development(tid)

    analyst_files = subprocess.run(
        ["git", "show", "--format=", "--name-only", "HEAD^"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    contract_files = subprocess.run(
        ["git", "show", "--format=", "--name-only", "HEAD"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    assert analyst_files == ["docs/requirements/WMS-700.md"]
    assert contract_files == ["backend/tests/test_wms_700_contract.py"]
    assert subprocess.run(
        ["git", "log", "-2", "--format=%s"], cwd=root,
        check=True, capture_output=True, text=True,
    ).stdout.splitlines() == [
        "WMS-700: контракт тестов", "WMS-700: проверки аналитика",
    ]


def test_deadline_stops_unfinished_work_and_releases_only_ready_subset(env: Any) -> None:
    runner, tid = make_night(env)
    state = env.store.data(tid)["night"]
    state.update(step="tasks", deadline_at=env.clock.now)
    state["tasks"]["WMS-700"].update(status="ready", step="ready")
    state["tasks"]["WMS-701"] = {"id": "WMS-701", "status": "working", "step": "developer"}
    env.store.patch_data(tid, night=state)
    runner.development(tid)
    saved = env.store.data(tid)["night"]
    assert env.store.ticket(tid)["stage"] == "release"
    assert saved["tasks"]["WMS-701"]["status"] == "stopped"
    assert saved["tasks"]["WMS-700"]["status"] == "ready"


def test_second_candidate_failure_goes_to_report_without_rerun(env: Any) -> None:
    runner, tid = make_night(env)
    state = env.store.data(tid)["night"]
    state.update(step="candidate_ci", candidate_attempt=2,
                 candidate={"pr": 9, "started": env.clock.now, "included": ["WMS-700"]})
    state["tasks"]["WMS-700"].update(status="ready", step="ready")
    env.store.set_stage(tid, "release", night=state)
    runner.release(tid)
    assert env.store.ticket(tid)["stage"] == "report"
    assert "ожидалось: pass" in env.store.data(tid)["night"]["release_error"]


def test_required_ci_rejects_missing_or_skipped_jobs() -> None:
    good = [{"name": name, "bucket": "pass"}
            for name in ("baseline", "backlog", "backend", "frontend-build", "охрана")]
    assert NightRunner._required_ci_passed(good)
    assert not NightRunner._required_ci_passed(good[:-1])
    assert not NightRunner._required_ci_passed([{**row, "bucket": "skipping"}
                                                 if row["name"] == "backend" else row
                                                 for row in good])


def test_release_calls_existing_hotfix_merge_deploy_verify(env: Any) -> None:
    runner, tid = make_night(env)
    env.store.set_stage(tid, "release", night={**env.store.data(tid)["night"], "step": "merge"},
                        hotfix={"step": "merge", "pr": 9, "path": "/fake"})
    runner.release(tid)
    runner.release(tid)
    runner.release(tid)
    assert runner.hotfix.release_calls == ["merge", "deploy", "verify"]
    assert env.store.data(tid)["night"]["step"] == "promote"


def test_interrupted_promote_is_not_repeated(env: Any) -> None:
    runner, tid = make_night(env)
    state = env.store.data(tid)["night"]
    state.update(step="promote", release_sha="c" * 40,
                 candidate={"path": "/fake", "included": ["WMS-700"]})
    state["tasks"]["WMS-700"].update(status="ready", promote_intent=True)
    env.store.set_stage(tid, "release", night=state)
    runner.release(tid)
    assert "исход неизвестен" in env.store.data(tid)["night"]["tasks"]["WMS-700"]["promote"]
    assert not [call for call in runner.hotfix.calls if call[0] == "run"]


def test_report_has_required_per_task_lines_and_is_idempotent(env: Any) -> None:
    runner, tid = make_night(env, release=False)
    state = env.store.data(tid)["night"]
    state["tasks"]["WMS-700"].update(status="waiting_owner",
                                              reason="C1 противоречит R2",
                                              contract_changed=True)
    env.store.set_stage(tid, "report", night={**state, "step": "morning_report"})
    runner.report(tid)
    runner.report(tid)
    rows = env.store.rows("SELECT * FROM outbox WHERE purpose='night_report'")
    assert len(rows) == 1
    assert "ждёт твоего решения" in rows[0]["text"]
    assert "контракт тестов менялся: да" in rows[0]["text"]
