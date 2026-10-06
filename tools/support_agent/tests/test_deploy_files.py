"""F4/F5: необязательные sha и attempt_id в deploy.yml; выкладка всегда закреплена за точным SHA.

Workflow и боевой скрипт не запускаются: проверяются разбор YAML и серверная часть на временных git-репозиториях
(для боевого скрипта включён WMS_DEPLOY_GUARD_ONLY=1: остановка до сборки и базы)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
UPDATE = ROOT / "scripts" / "deploy" / "prod-update.sh"
pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="needs git/bash")


def load() -> dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    data["on"] = data.pop(True)  # PyYAML читает ключ on как True
    return data  # type: ignore[no-any-return]


def named_step(steps: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    """Найти именованный шаг, не предполагая наличие name у uses-шагов."""
    return next(step for step in steps if step.get("name", "").startswith(prefix))


def test_workflow_yaml_has_optional_inputs_run_name_and_unchanged_triggers() -> None:
    wf = load()
    assert list(wf["on"]) == ["workflow_dispatch"]  # по-прежнему только ручной запуск
    inputs = wf["on"]["workflow_dispatch"]["inputs"]
    for name in ("sha", "attempt_id"):
        assert inputs[name]["required"] is False and inputs[name]["default"] == ""
    assert "inputs.attempt_id" in wf["run-name"] and "'Deploy Production'" in wf["run-name"]
    steps = wf["jobs"]["deploy"]["steps"]
    trusted = named_step(steps, "Require trusted dispatch branch")
    validate = named_step(steps, "Validate optional inputs")
    target = named_step(steps, "Resolve immutable target and verify its CI before SSH")
    deploy = named_step(steps, "Deploy on server")
    assert "refs/heads/etalon" in trusted["run"]
    assert "^[0123456789abcdef]{40}$" in validate["run"]
    assert "scripts/ci/verify_ci.py" in target["run"] and "sha=$target_sha" in target["run"]
    assert steps.index(validate) < steps.index(target) < steps.index(deploy)
    assert deploy["env"]["DEPLOY_SHA"] == "${{ steps.target.outputs.sha }}"
    assert deploy["with"]["envs"] == "DEPLOY_SHA"
    assert "prod-update.sh" in deploy["with"]["script"] and "docker" not in deploy["with"]["script"]
    assert any(s.get("name", "").startswith("Smoke check") for s in steps)  # проверка адресов осталась
    assert wf["concurrency"] == {"group": "deploy-production", "cancel-in-progress": False}


def git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    base = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, env={**base, **(env or {})}, capture_output=True,
                          text=True, check=True).stdout.strip()


def make_remote(tmp_path: Path, script_for: Any) -> tuple[Path, Path, dict[str, str]]:
    """origin с тремя коммитами etalon (c1, c2, c3) и коммитом side, не входящим в etalon."""
    work = tmp_path / "work"
    work.mkdir()
    git("init", "-q", "-b", "etalon", ".", cwd=work)
    shas: dict[str, str] = {}
    for tag in ("c1", "c2", "c3"):
        target = work / "scripts" / "deploy"
        target.mkdir(parents=True, exist_ok=True)
        (target / "prod-update.sh").write_text(script_for(tag), encoding="utf-8")
        (work / "marker.txt").write_text(tag, encoding="utf-8")
        git("add", "-A", cwd=work)
        git("commit", "-qm", tag, cwd=work)
        shas[tag] = git("rev-parse", "HEAD", cwd=work)
    git("checkout", "-q", "-b", "side", shas["c1"], cwd=work)
    (work / "side.txt").write_text("x", encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-qm", "side", cwd=work)
    shas["side"] = git("rev-parse", "HEAD", cwd=work)
    git("checkout", "-q", "etalon", cwd=work)
    origin = tmp_path / "origin.git"
    git("clone", "-q", "--bare", str(work), str(origin), cwd=tmp_path)
    clone = tmp_path / "server"
    git("clone", "-q", str(origin), str(clone), cwd=tmp_path)
    return origin, clone, shas


def stub_script(tag: str) -> str:
    return f'#!/usr/bin/env bash\necho "STUB script={tag} pin=${{WMS_DEPLOY_SHA:-}} head=$(git rev-parse HEAD)"\n'


def run_remote_part(
    clone: Path, tmp_path: Path, deploy_sha: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    wf = load()
    deploy = named_step(wf["jobs"]["deploy"]["steps"], "Deploy on server")
    env = {k: v for k, v in os.environ.items() if k != "GIT_CONFIG_GLOBAL"}
    (tmp_path / "home").mkdir(exist_ok=True)
    env.update({
        "WMS_REPO_DIR": str(clone),
        "HOME": str(tmp_path / "home"),
        "DEPLOY_SHA": deploy_sha,
    })
    env.update(extra_env or {})
    return subprocess.run(["bash", "-c", deploy["with"]["script"]], env=env, capture_output=True, text=True,
                          cwd=tmp_path)


def test_workflow_server_part_uses_resolved_head_of_etalon_as_immutable_target(tmp_path: Path) -> None:
    origin, clone, shas = make_remote(tmp_path, stub_script)
    res = run_remote_part(clone, tmp_path, shas["c3"])  # target-шаг разрешил пустой input в голову etalon
    assert res.returncode == 0, res.stderr
    assert f"STUB script=c3 pin={shas['c3']} head={shas['c3']}" in res.stdout


def test_workflow_server_part_pinned_uses_that_commit_script_and_pin(tmp_path: Path) -> None:
    origin, clone, shas = make_remote(tmp_path, stub_script)
    res = run_remote_part(clone, tmp_path, shas["c2"])
    assert res.returncode == 0, res.stderr
    assert f"STUB script=c2 pin={shas['c2']}" in res.stdout  # скрипт из закреплённого коммита, не из вершины


def test_workflow_server_part_refuses_foreign_or_malformed_sha_before_running_anything(tmp_path: Path) -> None:
    origin, clone, shas = make_remote(tmp_path, stub_script)
    for bad in (shas["side"], "", "abc123", "G" * 40, "0" * 40):
        res = run_remote_part(clone, tmp_path, bad)
        assert res.returncode != 0 and "STUB" not in res.stdout, bad


def prod_script(tmp_path: Path) -> Any:
    return lambda tag: UPDATE.read_text(encoding="utf-8")


def run_update(clone: Path, tmp_path: Path, pin: str | None) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "HOME": str(home), "WMS_REPO_DIR": str(clone), "WMS_DEPLOY_GUARD_ONLY": "1",
           "GIT_CONFIG_NOSYSTEM": "1"}
    if pin is not None:
        env["WMS_DEPLOY_SHA"] = pin
    return subprocess.run(["bash", str(UPDATE)], env=env, capture_output=True, text=True, cwd=clone)


def test_real_update_script_default_is_head_of_etalon_and_pin_selects_exact_commit(tmp_path: Path) -> None:
    origin, clone, shas = make_remote(tmp_path, prod_script(tmp_path))
    res = run_update(clone, tmp_path, None)
    assert res.returncode == 0 and git("rev-parse", "HEAD", cwd=clone) == shas["c3"], res.stderr
    res = run_update(clone, tmp_path, "")
    assert res.returncode == 0 and git("rev-parse", "HEAD", cwd=clone) == shas["c3"]
    res = run_update(clone, tmp_path, shas["c2"])
    assert res.returncode == 0 and git("rev-parse", "HEAD", cwd=clone) == shas["c2"], res.stderr
    assert "guard passed" in res.stdout


def test_real_update_script_refuses_pin_outside_trunk_or_malformed(tmp_path: Path) -> None:
    origin, clone, shas = make_remote(tmp_path, prod_script(tmp_path))
    git("fetch", "-q", "origin", "side", cwd=clone)
    res = run_update(clone, tmp_path, shas["side"])
    assert res.returncode != 0 and "not contained in trunk" in res.stderr
    for bad in ("abc", "Z" * 40, "x" * 41):
        res = run_update(clone, tmp_path, bad)
        assert res.returncode != 0 and "40-character" in res.stderr


def test_update_script_still_contains_backup_migration_and_health_steps() -> None:
    text = UPDATE.read_text(encoding="utf-8")
    for needle in ("pg_dump", "pg_restore --list", "run --rm migrations", "verify public access settings",
                   "WMS_DEPLOY_GUARD_ONLY", "is-ancestor"):
        assert needle in text


OLD_COMMIT = "549f7ba9"  # до закрепления версии: prod-update.sh не знает WMS_DEPLOY_SHA


def old_script() -> str:
    res = subprocess.run(["git", "show", f"{OLD_COMMIT}:scripts/deploy/prod-update.sh"], cwd=ROOT,
                         capture_output=True, text=True)
    if res.returncode != 0:
        pytest.skip("исторический prod-update.sh недоступен")
    assert "WMS_DEPLOY_SHA" not in res.stdout
    return res.stdout


def test_old_script_in_pinned_sha_is_refused_before_it_runs(tmp_path: Path) -> None:
    """N3: старый скрипт игнорирует закрепление и выкатил бы вершину etalon: отказ ДО его исполнения."""
    new = UPDATE.read_text(encoding="utf-8")
    old = old_script()
    origin, clone, shas = make_remote(tmp_path, lambda tag: old if tag == "c1" else new)
    git("checkout", "-q", shas["c1"], cwd=clone)  # сервер сейчас на старом коммите
    before = git("rev-parse", "HEAD", cwd=clone)
    res = run_remote_part(clone, tmp_path, shas["c1"], {"WMS_DEPLOY_GUARD_ONLY": "1"})
    assert res.returncode != 0
    assert "no pinned-version support" in res.stderr
    assert "Deploy guard passed" not in res.stdout and "checkout deploy branch" not in res.stdout
    assert git("rev-parse", "HEAD", cwd=clone) == before  # ничего не переключалось
    # коммит с новым скриптом проходит и выкатывается ровно закреплённый
    ok = run_remote_part(clone, tmp_path, shas["c2"], {"WMS_DEPLOY_GUARD_ONLY": "1"})
    assert ok.returncode == 0 and git("rev-parse", "HEAD", cwd=clone) == shas["c2"], ok.stderr


def test_resolved_etalon_head_still_works_when_older_commit_has_old_script(tmp_path: Path) -> None:
    new = UPDATE.read_text(encoding="utf-8")
    origin, clone, shas = make_remote(tmp_path, lambda tag: old_script() if tag == "c1" else new)
    res = run_remote_part(clone, tmp_path, shas["c3"], {"WMS_DEPLOY_GUARD_ONLY": "1"})
    assert res.returncode == 0 and git("rev-parse", "HEAD", cwd=clone) == shas["c3"], res.stderr


def test_pinned_script_stops_before_build_if_head_is_not_the_pin(tmp_path: Path) -> None:
    """Страховка внутри скрипта: если checkout оказался не на закреплённом коммите, сборки нет."""
    origin, clone, shas = make_remote(tmp_path, prod_script(tmp_path))
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    real_git = shutil.which("git")
    (shim_dir / "git").write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$*" == *"checkout -B"* ]]; then exec ' + str(real_git) + ' checkout -q -B etalon origin/etalon; fi\n'
        'exec ' + str(real_git) + ' "$@"\n', encoding="utf-8")
    (shim_dir / "git").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "PATH": f"{shim_dir}:{os.environ['PATH']}", "HOME": str(home),
           "WMS_REPO_DIR": str(clone), "WMS_DEPLOY_GUARD_ONLY": "1", "WMS_DEPLOY_SHA": shas["c2"]}
    res = subprocess.run(["bash", str(UPDATE)], env=env, capture_output=True, text=True, cwd=clone)
    assert res.returncode != 0 and "pinned deploy requested" in res.stderr
    assert "deploy guard" not in res.stdout and "docker" not in res.stdout
