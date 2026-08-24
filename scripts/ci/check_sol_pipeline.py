#!/usr/bin/env python3
"""Самодостаточная проверка Sol-led dispatcher в чистом временном Git-репозитории."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "sol_pipeline.py"


def load_pipeline():
    spec = importlib.util.spec_from_file_location("sol_pipeline_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SolPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Sol Pipeline Test")
        (self.repo / "input.txt").write_text("input", encoding="utf-8")
        self.git("add", "input.txt")
        self.git("commit", "-m", "baseline")
        self.run_dir = self.repo / "docs" / "runs" / "test-run"
        self.request = self.repo / "request.txt"
        self.request.write_text("Дословная просьба владельца для теста.", encoding="utf-8")
        self.git("add", "request.txt")
        self.git("commit", "-m", "request")
        self.pipeline = load_pipeline()
        self.fake_bin = Path(self.temp.name) / "bin"
        self.fake_bin.mkdir()
        fake = self.fake_bin / "codex"
        fake.write_text("""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
out = args[args.index('-o') + 1]
cwd = args[args.index('-C') + 1]
if os.environ.get('FAKE_CODEX_MODE') != 'missing':
    with open(os.path.join(cwd, 'artifact.txt'), 'w', encoding='utf-8') as f: f.write('artifact')
result = {
 'status':'completed', 'summary':'Выполнена тестовая работа внешнего исполнителя.',
 'rationale':'Проверка доказывает сохранение и валидацию результата.', 'actions':['создан артефакт'],
 'artifacts': ([] if os.environ.get('FAKE_CODEX_MODE') == 'missing' else [{'path':'artifact.txt','description':'тестовый артефакт'}]),
 'changed_files':['artifact.txt'], 'evidence':['artifact.txt'], 'unknowns':[],
 'recommended_next':{'agent':'none','why':'Работа тестового агента закончена.'}}
with open(out, 'w', encoding='utf-8') as f: json.dump(result, f)
print(json.dumps({'event':'done'}))
""", encoding="utf-8")
        fake.chmod(0o755)
        self.env = {"PATH": str(self.fake_bin) + os.pathsep + os.environ["PATH"]}
        self.invoke(["init", "--run-dir", str(self.run_dir), "--request-file", str(self.request)])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, text=True, capture_output=True, check=True).stdout.strip()

    def invoke(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), mock.patch.dict(os.environ, self.env, clear=False), mock.patch.object(os, "getcwd", return_value=str(self.repo)):
            previous = Path.cwd()
            os.chdir(self.repo)
            try:
                code = self.pipeline.main(argv)
            finally:
                os.chdir(previous)
        return code, stdout.getvalue(), stderr.getvalue()

    def write_json(self, name: str, value: object) -> Path:
        path = self.repo / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def call_spec(self, call_id: str = "call-one") -> dict:
        return {"call_id": call_id, "agent": "researcher", "why_now": "Нужно проверить протокол сохранения полного результата агента.", "task": "Создай обещанный тестовый артефакт и верни валидный результат для проверки.", "working_directory": ".", "inputs": [{"ref": "input.txt", "purpose": "Исходные данные для тестового вызова"}], "expected_artifacts": [{"path": "artifact.txt", "purpose": "Сохранённый результат тестового агента"}], "acceptance": ["Артефакт существует и перечислен в ответе агента."]}

    def result(self) -> dict:
        return {"status": "completed", "summary": "Выполнена тестовая работа внешнего исполнителя.", "rationale": "Проверка доказывает сохранение и валидацию результата.", "actions": ["создан артефакт"], "artifacts": [{"path": "artifact.txt", "description": "тестовый артефакт"}], "changed_files": ["artifact.txt"], "evidence": ["artifact.txt"], "unknowns": [], "recommended_next": {"agent": "none", "why": "Работа тестового агента закончена."}}

    def run_file(self, relative: str, content: str = "доказательство") -> Path:
        path = self.run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def imported_attempt(self, call_id: str, role: str, result_status: str = "completed") -> Path:
        artifact = self.run_file(f"evidence/{call_id}.md", f"артефакт роли {role}")
        result = self.result()
        result["status"] = result_status
        result["artifacts"] = [{"path": str(artifact.relative_to(self.repo)), "description": "доказательство роли"}]
        source = self.run_file(f"external/{call_id}.json", json.dumps(result))
        spec = self.call_spec(call_id)
        spec["agent"] = role
        spec["expected_artifacts"] = [{"path": str(artifact.relative_to(self.repo)), "purpose": "Сохранённый артефакт роли"}]
        spec_path = self.run_file(f"specs/{call_id}.json", json.dumps(spec))
        code, _, error = self.invoke(["import-result", "--run-dir", str(self.run_dir), "--spec", str(spec_path), "--result", str(source)])
        self.assertEqual(code, 0, error)
        return self.run_dir / "attempts" / call_id / "final-result.json"

    def executed_check(self, check_id: str = "finish-check") -> Path:
        spec = {"check_id": check_id, "why_now": "Нужно зафиксировать успешную проверку на текущем сохранённом commit.", "working_directory": ".", "argv": [sys.executable, "-c", "print('check passed')"], "timeout_seconds": 10}
        spec_path = self.run_file(f"specs/{check_id}.json", json.dumps(spec))
        code, _, error = self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(spec_path)])
        self.assertEqual(code, 0, error)
        return self.run_dir / "checks" / check_id / "metadata.json"

    def completion(self, evidence: dict[str, list[Path]]) -> dict:
        return {
            "lead_verdict": "Ведущий проверил все обязательные доказательства этого запуска.",
            **{
                name: {
                    "status": "passed",
                    "why": "Это доказательство прошло обязательную содержательную проверку.",
                    "evidence": [str(path.relative_to(self.repo)) for path in evidence[name]],
                }
                for name in ["prototype", "test_plan", "review", "test_execution", "browser_acceptance", "git_saved"]
            },
        }

    def saved_completion_evidence(self, sha: str | None = None) -> Path:
        return self.run_file("gates/git-saved.txt", sha or self.git("rev-parse", "HEAD"))

    def test_invalid_call_rejected_without_spawn(self) -> None:
        spec = self.call_spec()
        spec["why_now"] = "мало"
        code, _, _ = self.invoke(["call", "--run-dir", str(self.run_dir), "--spec", str(self.write_json("bad.json", spec))])
        self.assertEqual(code, 2)
        self.assertFalse((self.repo / "artifact.txt").exists())

    def test_dry_run_persists_full_prompt(self) -> None:
        spec = self.write_json("call.json", self.call_spec())
        code, _, _ = self.invoke(["call", "--run-dir", str(self.run_dir), "--spec", str(spec), "--dry-run"])
        self.assertEqual(code, 0)
        prompt = (self.run_dir / "attempts" / "call-one" / "full-prompt.txt").read_text(encoding="utf-8")
        self.assertIn("Sol-исследователь WMS", prompt)
        self.assertIn("Создай обещанный тестовый артефакт", prompt)

    def test_valid_fake_agent_and_missing_artifact(self) -> None:
        valid = self.write_json("valid.json", self.call_spec("valid-call"))
        code, _, _ = self.invoke(["call", "--run-dir", str(self.run_dir), "--spec", str(valid)])
        self.assertEqual(code, 0)
        self.assertTrue((self.run_dir / "attempts" / "valid-call" / "final-result.json").exists())
        missing = self.write_json("missing.json", self.call_spec("missing-call"))
        self.env["FAKE_CODEX_MODE"] = "missing"
        code, _, _ = self.invoke(["call", "--run-dir", str(self.run_dir), "--spec", str(missing)])
        self.assertEqual(code, 2)
        saved = json.loads((self.run_dir / "attempts" / "missing-call" / "metadata.json").read_text())
        self.assertEqual(saved["status"], "protocol_error")

    def test_import_result(self) -> None:
        (self.repo / "artifact.txt").write_text("artifact", encoding="utf-8")
        result = self.write_json("external-result.json", self.result())
        spec = self.write_json("import.json", self.call_spec("import-call"))
        code, _, _ = self.invoke(["import-result", "--run-dir", str(self.run_dir), "--spec", str(spec), "--result", str(result)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.run_dir / "attempts" / "import-call" / "metadata.json").read_text())["status"], "completed")

    def test_check_captures_sha_streams_and_failure(self) -> None:
        good = self.write_json("good-check.json", {"check_id": "check-good", "why_now": "Нужно сохранить stdout, stderr и неизменность SHA проверки.", "working_directory": ".", "argv": [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"], "timeout_seconds": 10})
        code, _, _ = self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(good)])
        self.assertEqual(code, 0)
        check = self.run_dir / "checks" / "check-good"
        self.assertIn("out", (check / "stdout.txt").read_text())
        self.assertIn("err", (check / "stderr.txt").read_text())
        data = json.loads((check / "metadata.json").read_text())
        self.assertEqual(data["head_before"], data["head_after"])
        bad = self.write_json("bad-check.json", {"check_id": "check-bad", "why_now": "Нужно сохранить неуспешный exit code без автоматического повтора.", "working_directory": ".", "argv": [sys.executable, "-c", "raise SystemExit(7)"], "timeout_seconds": 10})
        code, _, _ = self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(bad)])
        self.assertEqual(code, 1)

    def test_completion_missing_evidence_rejected_and_status_restart(self) -> None:
        spec = self.write_json("dry.json", self.call_spec("restart-call"))
        self.assertEqual(self.invoke(["call", "--run-dir", str(self.run_dir), "--spec", str(spec), "--dry-run"])[0], 0)
        restarted = load_pipeline()
        with mock.patch.object(self, "pipeline", restarted):
            code, output, _ = self.invoke(["status", "--run-dir", str(self.run_dir)])
        self.assertEqual(code, 0)
        self.assertIn("restart-call: dry_run", output)
        completion = {"lead_verdict": "Ведущий проверил все обязательные доказательства этого запуска.", **{name: {"status": "passed", "why": "Это доказательство прошло обязательную содержательную проверку.", "evidence": []} for name in ["prototype", "test_plan", "review", "test_execution", "browser_acceptance", "git_saved"]}}
        path = self.write_json("completion.json", completion)
        code, _, _ = self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])
        self.assertEqual(code, 2)

    def test_zero_calls_and_checks_cannot_finish(self) -> None:
        completion = self.completion({name: [self.run_file(f"gates/{name}.txt")] for name in ["prototype", "test_plan", "review", "test_execution", "browser_acceptance"]} | {"git_saved": [self.saved_completion_evidence()]})
        path = self.run_file("completion-zero.json", json.dumps(completion))
        self.assertEqual(self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])[0], 2)

    def test_blocked_role_result_cannot_satisfy_finish(self) -> None:
        evidence = {
            "prototype": [self.imported_attempt("developer-call", "developer")],
            "test_plan": [self.imported_attempt("tester-call", "tester", "blocked")],
            "review": [self.imported_attempt("reviewer-call", "reviewer")],
            "browser_acceptance": [self.imported_attempt("clicker-call", "clicker")],
            "test_execution": [self.executed_check()],
            "git_saved": [self.saved_completion_evidence()],
        }
        path = self.run_file("completion-blocked-role.json", json.dumps(self.completion(evidence)))
        self.assertEqual(self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])[0], 2)

    def test_finish_requires_all_roles_and_current_sha_check(self) -> None:
        evidence = {
            "prototype": [self.imported_attempt("developer-call", "developer")],
            "test_plan": [self.imported_attempt("tester-call", "tester")],
            "review": [self.imported_attempt("reviewer-call", "reviewer")],
            "browser_acceptance": [self.imported_attempt("clicker-call", "clicker")],
            "test_execution": [self.executed_check()],
            "git_saved": [self.saved_completion_evidence()],
        }
        path = self.run_file("completion-happy.json", json.dumps(self.completion(evidence)))
        code, _, error = self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])
        self.assertEqual(code, 0, error)

    def test_finish_rejects_old_check_after_new_commit(self) -> None:
        old_sha = self.git("rev-parse", "HEAD")
        old_check = self.executed_check("old-check")
        (self.repo / "saved.txt").write_text("saved", encoding="utf-8")
        self.git("add", "saved.txt", "request.txt")
        self.git("commit", "-m", "new saved state")
        evidence = {
            "prototype": [self.imported_attempt("developer-call", "developer")],
            "test_plan": [self.imported_attempt("tester-call", "tester")],
            "review": [self.imported_attempt("reviewer-call", "reviewer")],
            "browser_acceptance": [self.imported_attempt("clicker-call", "clicker")],
            "test_execution": [old_check],
            "git_saved": [self.saved_completion_evidence()],
        }
        path = self.run_file("completion-old-check.json", json.dumps(self.completion(evidence)))
        self.assertEqual(self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])[0], 2)

    def test_finish_rejects_old_git_sha(self) -> None:
        old_sha = self.git("rev-parse", "HEAD")
        (self.repo / "saved.txt").write_text("saved", encoding="utf-8")
        self.git("add", "saved.txt", "request.txt")
        self.git("commit", "-m", "new saved state")
        evidence = {
            "prototype": [self.imported_attempt("developer-call", "developer")],
            "test_plan": [self.imported_attempt("tester-call", "tester")],
            "review": [self.imported_attempt("reviewer-call", "reviewer")],
            "browser_acceptance": [self.imported_attempt("clicker-call", "clicker")],
            "test_execution": [self.executed_check()],
            "git_saved": [self.saved_completion_evidence(old_sha)],
        }
        path = self.run_file("completion-old-sha.json", json.dumps(self.completion(evidence)))
        self.assertEqual(self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])[0], 2)

    def test_timeouts_are_terminal_and_decode_bytes(self) -> None:
        call_spec = self.call_spec("timeout-call")
        call_spec["timeout_seconds"] = 60
        original_run = subprocess.run

        def timeout_codex(command, *args, **kwargs):
            if command[:2] == ["codex", "exec"]:
                raise subprocess.TimeoutExpired(command, 60, output=b"stdout-bytes", stderr=b"stderr-bytes")
            return original_run(command, *args, **kwargs)

        with mock.patch.object(self.pipeline.subprocess, "run", side_effect=timeout_codex):
            code, _, _ = self.invoke(["call", "--run-dir", str(self.run_dir), "--spec", str(self.write_json("timeout-call.json", call_spec))])
        self.assertEqual(code, 2)
        attempt = self.run_dir / "attempts" / "timeout-call"
        self.assertIn("stdout-bytes", (attempt / "raw-stdout.jsonl").read_text())
        self.assertIn("stderr-bytes", (attempt / "stderr.txt").read_text())
        self.assertTrue(json.loads((attempt / "metadata.json").read_text())["timed_out"])
        check_spec = {"check_id": "timeout-check", "why_now": "Нужно доказать терминальное сохранение timeout проверки с байтовыми потоками.", "working_directory": ".", "argv": ["timeout-command"], "timeout_seconds": 10}

        def timeout_check(command, *args, **kwargs):
            if command == ["timeout-command"]:
                raise subprocess.TimeoutExpired(command, 10, output=b"check-out", stderr=b"check-err")
            return original_run(command, *args, **kwargs)

        with mock.patch.object(self.pipeline.subprocess, "run", side_effect=timeout_check):
            code, _, _ = self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(self.write_json("timeout-check.json", check_spec))])
        self.assertEqual(code, 1)
        check = self.run_dir / "checks" / "timeout-check"
        self.assertIn("check-out", (check / "stdout.txt").read_text())
        self.assertEqual(json.loads((check / "metadata.json").read_text())["status"], "failed")

    def test_rejects_token_argv_and_external_run_dir(self) -> None:
        token_check = {"check_id": "secret-check", "why_now": "Нужно проверить запрет явного credential-параметра в тестовой команде.", "working_directory": ".", "argv": ["tool", "--token", "supersecret"], "timeout_seconds": 10}
        self.assertEqual(self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(self.write_json("secret-check.json", token_check))])[0], 2)
        outside = Path(self.temp.name) / "outside-run"
        self.assertEqual(self.invoke(["init", "--run-dir", str(outside), "--request-file", str(self.request)])[0], 2)
        self.assertEqual(self.invoke(["init", "--run-dir", str(self.run_dir), "--request-file", str(self.request)])[0], 2)

    def test_fabricated_attempt_and_check_are_rejected(self) -> None:
        fake_attempt = self.run_file("attempts/fake-role/final-result.json", json.dumps(self.result()))
        fake_dir = fake_attempt.parent
        (fake_dir / "metadata.json").write_text(json.dumps({"call_id": "fake-role", "role": "tester", "status": "completed"}), encoding="utf-8")
        (fake_dir / "call.json").write_text("{}", encoding="utf-8")
        (fake_dir / "raw-stdout.jsonl").write_text("", encoding="utf-8")
        (fake_dir / "stderr.txt").write_text("", encoding="utf-8")
        fake_check = self.run_file("checks/fake-check/metadata.json", json.dumps({"check_id": "fake-check", "status": "passed", "head_before": self.git("rev-parse", "HEAD"), "head_after": self.git("rev-parse", "HEAD")}))
        (fake_check.parent / "check.json").write_text("{}", encoding="utf-8")
        (fake_check.parent / "stdout.txt").write_text("", encoding="utf-8")
        (fake_check.parent / "stderr.txt").write_text("", encoding="utf-8")
        evidence = {name: [fake_attempt] for name in ["prototype", "test_plan", "review", "browser_acceptance"]}
        evidence.update({"test_execution": [fake_check], "git_saved": [self.saved_completion_evidence()]})
        path = self.run_file("completion-fabricated.json", json.dumps(self.completion(evidence)))
        self.assertEqual(self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])[0], 2)

    def test_ledger_is_bound_to_run_context(self) -> None:
        run_path = self.run_dir / "RUN.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["ledger_id"] = "0" * 64
        run["ledger_path"] = str(Path(run["repo_common_git_dir"]) / "sol-pipeline-ledger" / run["ledger_id"])
        run_path.write_text(json.dumps(run), encoding="utf-8")
        self.assertEqual(self.invoke(["status", "--run-dir", str(self.run_dir)])[0], 2)

    def test_reviewer_and_clicker_on_old_sha_are_rejected(self) -> None:
        evidence = {
            "prototype": [self.imported_attempt("developer-call", "developer")],
            "test_plan": [self.imported_attempt("tester-call", "tester")],
            "review": [self.imported_attempt("reviewer-call", "reviewer")],
            "browser_acceptance": [self.imported_attempt("clicker-call", "clicker")],
        }
        (self.repo / "saved.txt").write_text("saved", encoding="utf-8")
        self.git("add", "saved.txt")
        self.git("commit", "-m", "new current head")
        evidence["test_execution"] = [self.executed_check()]
        evidence["git_saved"] = [self.saved_completion_evidence()]
        path = self.run_file("completion-old-review.json", json.dumps(self.completion(evidence)))
        self.assertEqual(self.invoke(["finish", "--run-dir", str(self.run_dir), "--spec", str(path)])[0], 2)

    def test_all_sensitive_argv_forms_and_env_refs(self) -> None:
        for index, value in enumerate(["--access-token", "--client-secret", "dsn=postgres://x", "X-API-Key"]):
            spec = {"check_id": f"forbid-{index}", "why_now": "Нужно запретить явный секретный параметр в argv проверки процесса.", "working_directory": ".", "argv": ["tool", value], "timeout_seconds": 10}
            self.assertEqual(self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(self.write_json(f"forbid-{index}.json", spec))])[0], 2)
        self.env["SAFE_TEST_TOKEN"] = "super-secret-value"
        script = self.repo / "show_env.py"
        script.write_text("import os; print(os.environ['SAFE_TEST_TOKEN'])", encoding="utf-8")
        spec = {"check_id": "env-ref-check", "why_now": "Нужно передать названную переменную только в изолированное окружение проверки.", "working_directory": ".", "argv": [sys.executable, "show_env.py"], "timeout_seconds": 10, "env_refs": ["SAFE_TEST_TOKEN"]}
        path = self.write_json("env-ref-check.json", spec)
        code, _, error = self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(path)])
        self.assertEqual(code, 0, error)
        check_dir = self.run_dir / "checks" / "env-ref-check"
        self.assertIn("[REDACTED]", (check_dir / "stdout.txt").read_text())
        metadata = (check_dir / "metadata.json").read_text()
        self.assertIn("SAFE_TEST_TOKEN", metadata)
        self.assertNotIn("super-secret-value", metadata)
        self.env["DATABASE_URL"] = "postgresql://user:password@example.invalid/private"
        database_script = self.repo / "show_database_url.py"
        database_script.write_text("import os; print(os.environ['DATABASE_URL'])", encoding="utf-8")
        database_spec = {"check_id": "database-env-ref", "why_now": "Нужно удалить из сохранённого вывода значение явно переданной переменной независимо от её имени.", "working_directory": ".", "argv": [sys.executable, "show_database_url.py"], "timeout_seconds": 10, "env_refs": ["DATABASE_URL"]}
        database_path = self.write_json("database-env-ref.json", database_spec)
        self.assertEqual(self.invoke(["check", "--run-dir", str(self.run_dir), "--spec", str(database_path)])[0], 0)
        database_output = (self.run_dir / "checks" / "database-env-ref" / "stdout.txt").read_text()
        self.assertIn("[REDACTED]", database_output)
        self.assertNotIn("postgresql://", database_output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
