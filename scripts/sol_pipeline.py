#!/usr/bin/env python3
"""Минимальный журналируемый диспетчер для Sol-led процесса WMS.

Скрипт намеренно не строит последовательность ролей и не повторяет вызовы.
Каждая команда либо сохраняет один наблюдаемый факт, либо возвращает ошибку
ведущему Sol, который принимает следующее содержательное решение.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "pipeline" / "sol-led" / "contracts"
AGENTS = ROOT / ".codex" / "agents"
SHA_RE = re.compile(r"\b[0-9a-f]{7,64}\b", re.IGNORECASE)
SECRET_NAME_RE = re.compile(r"(?:TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
CREDENTIAL_ARG_RE = re.compile(r"(?:token|secret|password|credential|api[-_]?key|authorization|bearer|dsn|access[-_]?token|client[-_]?secret|x[-_]?api[-_]?key)", re.IGNORECASE)
CHECK_ENV_ALLOWLIST = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TERM", "PYTHONPATH", "VIRTUAL_ENV")


class PipelineError(Exception):
    """Ошибка протокола, которую должен увидеть и обработать ведущий."""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def secret_values() -> list[str]:
    """Возвращает значения секретов, которые нельзя сохранять в журнале."""
    return sorted(
        (value for name, value in os.environ.items() if SECRET_NAME_RE.search(name) and len(value) >= 8),
        key=len,
        reverse=True,
    )


def redact_text(value: str | bytes, extra_values: list[str] | tuple[str, ...] = ()) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    for secret in sorted([*secret_values(), *(item for item in extra_values if len(item) >= 4)], key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    return value


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(redact_value(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(redact_text(value))
        temporary = Path(handle.name)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Не найден JSON-файл: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Некорректный JSON в {path}: {exc.msg}") from exc


def resolve(path_value: str, base: Path) -> Path:
    path = Path(path_value)
    return (path if path.is_absolute() else base / path).resolve()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def git(*argv: str, cwd: Path) -> str:
    completed = subprocess.run(["git", *argv], cwd=cwd, text=True, capture_output=True)
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise PipelineError(f"Git-команда не выполнилась: {message}")
    return completed.stdout.strip()


def load_schema(name: str) -> dict[str, Any]:
    return read_json(CONTRACTS / name)


def validate(instance: Any, schema: dict[str, Any], root: dict[str, Any] | None = None, where: str = "") -> list[str]:
    """Небольшая достаточная для локальных контрактов проверка JSON Schema."""
    root = root or schema
    if "$ref" in schema:
        reference = schema["$ref"]
        if not reference.startswith("#/"):
            return [f"{where or 'значение'}: неподдерживаемая ссылка {reference}"]
        target: Any = root
        for part in reference[2:].split("/"):
            target = target[part]
        return validate(instance, target, root, where)

    errors: list[str] = []
    label = where or "корень"
    expected = schema.get("type")
    type_ok = {
        "object": isinstance(instance, dict),
        "array": isinstance(instance, list),
        "string": isinstance(instance, str),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
    }
    if expected and not type_ok.get(expected, True):
        return [f"{label}: ожидается {expected}"]
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{label}: значение не входит в допустимый список")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{label}: строка короче {schema['minLength']} символов")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{label}: строка не соответствует формату")
    if isinstance(instance, int):
        if instance < schema.get("minimum", instance):
            errors.append(f"{label}: значение меньше {schema['minimum']}")
        if instance > schema.get("maximum", instance):
            errors.append(f"{label}: значение больше {schema['maximum']}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{label}: требуется минимум {schema['minItems']} элементов")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(validate(item, schema["items"], root, f"{label}[{index}]"))
    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{label}: отсутствует обязательное поле {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{label}: лишнее поле {key}")
        for key, child in properties.items():
            if key in instance:
                errors.extend(validate(instance[key], child, root, f"{label}.{key}"))
    return errors


def require_valid(value: Any, schema_name: str, title: str) -> None:
    errors = validate(value, load_schema(schema_name))
    if errors:
        raise PipelineError(f"{title} не соответствует контракту: " + "; ".join(errors))


def run_file(run_dir: Path) -> Path:
    return run_dir / "RUN.json"


def ledger_id_for(run_dir: Path, worktree: Path, base_sha: str, request_sha256: str) -> str:
    context = f"{run_dir.resolve()}\0{worktree.resolve()}\0{base_sha}\0{request_sha256}"
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


def ledger_dir_for(common_git: Path, ledger_id: str) -> Path:
    return common_git / "sol-pipeline-ledger" / ledger_id


def ledger_paths(run: dict[str, Any]) -> tuple[Path, Path]:
    try:
        ledger_id = run["ledger_id"]
        ledger_dir = Path(run["ledger_path"]).resolve()
    except KeyError as exc:
        raise PipelineError("RUN.json не содержит ссылку на подписанный ledger") from exc
    common_git = Path(run["repo_common_git_dir"]).resolve()
    expected = ledger_dir_for(common_git, ledger_id).resolve()
    if not isinstance(ledger_id, str) or ledger_dir != expected:
        raise PipelineError("Ссылка на ledger в RUN.json некорректна")
    key_path = ledger_dir / "hmac.key"
    if not key_path.is_file():
        raise PipelineError("Ключ подписанного ledger не найден")
    return ledger_dir, key_path


def attest(run: dict[str, Any], entry_type: str, entry_id: str, payload: dict[str, Any]) -> None:
    ledger_dir, key_path = ledger_paths(run)
    key = key_path.read_bytes()
    if len(key) != 32:
        raise PipelineError("Ключ ledger имеет неверную длину")
    signed_payload = {"ledger_id": run["ledger_id"], "type": entry_type, "id": entry_id, **payload}
    signature = hmac.new(key, canonical_json(signed_payload), hashlib.sha256).hexdigest()
    atomic_json(ledger_dir / f"{entry_type}-{entry_id}.json", {"payload": signed_payload, "signature": signature})


def attestation(run: dict[str, Any], entry_type: str, entry_id: str, directory: Path, files: dict[str, Path]) -> dict[str, Any]:
    ledger_dir, key_path = ledger_paths(run)
    path = ledger_dir / f"{entry_type}-{entry_id}.json"
    record = read_json(path)
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict) or not isinstance(record.get("signature"), str):
        raise PipelineError(f"Подпись ledger повреждена: {path.name}")
    payload = record["payload"]
    expected_signature = hmac.new(key_path.read_bytes(), canonical_json(payload), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(record["signature"], expected_signature):
        raise PipelineError(f"Подпись ledger не совпадает: {path.name}")
    if payload.get("ledger_id") != run["ledger_id"] or payload.get("type") != entry_type or payload.get("id") != entry_id:
        raise PipelineError(f"Ledger содержит чужую запись: {path.name}")
    digests = payload.get("digests")
    if not isinstance(digests, dict):
        raise PipelineError(f"Ledger не содержит хэши файлов: {path.name}")
    for name, file_path in files.items():
        if not file_path.is_file() or digests.get(name) != sha256_file(file_path):
            raise PipelineError(f"Файл {name} не совпадает с подписанной записью ledger")
    return payload


def load_run(run_dir_value: str) -> tuple[Path, dict[str, Any]]:
    run_dir = Path(run_dir_value).expanduser().resolve()
    run = read_json(run_file(run_dir))
    for key in ("worktree", "repo_common_git_dir", "base_sha"):
        if not isinstance(run.get(key), str):
            raise PipelineError(f"RUN.json не содержит поле {key}")
    worktree = Path(run["worktree"]).resolve()
    if run_dir == worktree or not is_within(run_dir, worktree):
        raise PipelineError("Папка запуска должна находиться внутри записанного Git worktree")
    if not worktree.is_dir() or Path(git("rev-parse", "--show-toplevel", cwd=worktree)).resolve() != worktree:
        raise PipelineError("Записанный worktree больше не является действующим Git worktree")
    common_git = Path(git("rev-parse", "--git-common-dir", cwd=worktree))
    if not common_git.is_absolute():
        common_git = (worktree / common_git).resolve()
    if common_git != Path(run["repo_common_git_dir"]).resolve():
        raise PipelineError("Git common dir запуска больше не совпадает с сохранённым")
    request_path = run_dir / "REQUEST.txt"
    request_digest = sha256_file(request_path)
    if run.get("request_sha256") != request_digest:
        raise PipelineError("Дословная просьба запуска изменена после init")
    expected_ledger_id = ledger_id_for(run_dir, worktree, run["base_sha"], request_digest)
    if run.get("ledger_id") != expected_ledger_id:
        raise PipelineError("Подписанный ledger не принадлежит этому run-dir, worktree, base SHA и запросу")
    ledger_paths(run)
    return run_dir, run


def append_event(run_dir: Path, **event: Any) -> None:
    event = {"timestamp": now(), **event}
    events_path = run_dir / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_value(event), ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(events_path, 0o600)


def attempt_dir(run_dir: Path, call_id: str) -> Path:
    return run_dir / "attempts" / call_id


def check_dir(run_dir: Path, check_id: str) -> Path:
    return run_dir / "checks" / check_id


def verify_working_directory(spec: dict[str, Any], run: dict[str, Any]) -> Path:
    worktree = Path(run["worktree"]).resolve()
    working_directory = resolve(spec["working_directory"], worktree)
    if not working_directory.exists() or not working_directory.is_dir():
        raise PipelineError(f"Рабочая директория не существует: {working_directory}")
    if not is_within(working_directory, worktree):
        raise PipelineError("Рабочая директория должна находиться внутри worktree этого запуска")
    actual_worktree = Path(git("rev-parse", "--show-toplevel", cwd=working_directory)).resolve()
    if actual_worktree != worktree:
        raise PipelineError("Рабочая директория относится к другому Git worktree")
    return working_directory


def local_path(value: str, working_directory: Path, run_dir: Path, worktree: Path) -> Path:
    path = resolve(value, working_directory)
    if not path.exists():
        raise PipelineError(f"Не найден локальный вход или артефакт: {path}")
    if not (is_within(path, worktree) or is_within(path, run_dir)):
        raise PipelineError(f"Путь должен находиться в репозитории или папке запуска: {path}")
    return path


def verify_call_paths(spec: dict[str, Any], run_dir: Path, run: dict[str, Any], working_directory: Path) -> list[Path]:
    worktree = Path(run["worktree"]).resolve()
    for input_item in spec["inputs"]:
        local_path(input_item["ref"], working_directory, run_dir, worktree)
    expected: list[Path] = []
    for artifact in spec["expected_artifacts"]:
        path = resolve(artifact["path"], working_directory)
        if not (is_within(path, worktree) or is_within(path, run_dir)):
            raise PipelineError(f"Ожидаемый артефакт должен находиться в репозитории или папке запуска: {path}")
        expected.append(path)
    return expected


def config_for(role: str) -> dict[str, Any]:
    config_path = AGENTS / f"wms-{role}.toml"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Не найдена конфигурация роли: {config_path}") from exc
    for key in ("model", "model_reasoning_effort", "sandbox_mode", "developer_instructions"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise PipelineError(f"В конфигурации роли отсутствует поле {key}")
    return config


def prompt_for(spec: dict[str, Any], config: dict[str, Any]) -> str:
    return (
        config["developer_instructions"].strip()
        + "\n\nНиже — единственное поручение ведущего Sol в JSON. Верни только JSON по output schema.\n"
        + json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )


def validate_result(result_path: Path, spec: dict[str, Any], expected: list[Path], working_directory: Path, run_dir: Path, run: dict[str, Any]) -> dict[str, Any]:
    result = read_json(result_path)
    require_valid(result, "result.schema.json", "Результат агента")
    result_paths: set[Path] = set()
    for artifact in result["artifacts"]:
        artifact_path = local_path(artifact["path"], working_directory, run_dir, Path(run["worktree"]).resolve())
        result_paths.add(artifact_path)
    missing = [str(path) for path in expected if not path.exists() or path not in result_paths]
    if missing:
        raise PipelineError("Агент не подтвердил обещанные артефакты: " + ", ".join(missing))
    return result


def write_attempt_common(directory: Path, spec: dict[str, Any], prompt: str, metadata: dict[str, Any]) -> None:
    if directory.exists():
        raise PipelineError(f"Попытка с этим ID уже сохранена и не может быть перезаписана: {directory.name}")
    private_dir(directory)
    atomic_json(directory / "call.json", spec)
    atomic_text(directory / "full-prompt.txt", prompt)
    atomic_json(directory / "metadata.json", metadata)


def sanitize_result_file(directory: Path) -> None:
    """Codex пишет output file сам, поэтому сразу заменяем его приватной redacted-копией."""
    result_path = directory / "final-result.json"
    if result_path.exists():
        atomic_text(result_path, result_path.read_text(encoding="utf-8", errors="replace"))


def call_attestation(run: dict[str, Any], directory: Path, metadata: dict[str, Any]) -> None:
    attest(run, "call", metadata["call_id"], {
        "role": metadata["role"],
        "status": metadata["status"],
        "result_status": metadata.get("result_status"),
        "head_before": metadata["head_before"],
        "head_after": metadata["head_after"],
        "digests": {name: sha256_file(directory / filename) for name, filename in {
            "call_spec": "call.json", "metadata": "metadata.json", "final_result": "final-result.json",
            "raw_stdout": "raw-stdout.jsonl", "stderr": "stderr.txt",
        }.items()},
    })


def check_attestation(run: dict[str, Any], directory: Path, metadata: dict[str, Any]) -> None:
    attest(run, "check", metadata["check_id"], {
        "role": None,
        "status": metadata["status"],
        "result_status": None,
        "head_before": metadata["head_before"],
        "head_after": metadata["head_after"],
        "digests": {name: sha256_file(directory / filename) for name, filename in {
            "check_spec": "check.json", "metadata": "metadata.json", "stdout": "stdout.txt", "stderr": "stderr.txt",
        }.items()},
    })


def command_init(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise PipelineError(f"Папка запуска уже не пуста и не может быть перезаписана: {run_dir}")
    request = Path(args.request_file).expanduser().resolve()
    if not request.is_file():
        raise PipelineError(f"Файл исходной просьбы не найден: {request}")
    worktree = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd())).resolve()
    if run_dir == worktree or not is_within(run_dir, worktree):
        raise PipelineError("--run-dir должен находиться внутри текущего Git worktree")
    common_git = Path(git("rev-parse", "--git-common-dir", cwd=worktree))
    if not common_git.is_absolute():
        common_git = (worktree / common_git).resolve()
    base_sha = args.base_sha or git("rev-parse", "HEAD", cwd=worktree)
    if subprocess.run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"], cwd=worktree).returncode:
        raise PipelineError(f"base_sha не указывает на существующий commit: {base_sha}")
    request_sha256 = hashlib.sha256(request.read_bytes()).hexdigest()
    ledger_id = ledger_id_for(run_dir, worktree, base_sha, request_sha256)
    ledger_dir = ledger_dir_for(common_git, ledger_id)
    if ledger_dir.exists():
        raise PipelineError(f"Подписанный ledger уже существует: {ledger_dir}")
    private_dir(ledger_dir)
    key_path = ledger_dir / "hmac.key"
    with key_path.open("xb") as handle:
        handle.write(secrets.token_bytes(32))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(key_path, 0o600)
    private_dir(run_dir)
    atomic_text(run_dir / "REQUEST.txt", request.read_text(encoding="utf-8"))
    atomic_json(run_file(run_dir), {
        "created_at": now(),
        "worktree": str(worktree),
        "repo_common_git_dir": str(common_git),
        "base_sha": base_sha,
        "request_file": str(request),
        "request_sha256": request_sha256,
        "ledger_id": ledger_id,
        "ledger_path": str(ledger_dir),
    })
    append_event(run_dir, event="init", status="accepted", path=str(run_dir), base_sha=base_sha, worktree=str(worktree))
    print(f"Запуск создан: {run_dir}")
    return 0


def command_call(args: argparse.Namespace) -> int:
    run_dir, run = load_run(args.run_dir)
    spec = read_json(Path(args.spec).expanduser().resolve())
    require_valid(spec, "call.schema.json", "Поручение")
    working_directory = verify_working_directory(spec, run)
    expected = verify_call_paths(spec, run_dir, run, working_directory)
    config = config_for(spec["agent"])
    prompt = prompt_for(spec, config)
    directory = attempt_dir(run_dir, spec["call_id"])
    metadata = {
        "call_id": spec["call_id"], "role": spec["agent"], "model": config["model"],
        "reasoning_effort": config["model_reasoning_effort"], "sandbox": config["sandbox_mode"],
        "working_directory": str(working_directory), "started_at": now(), "status": "started",
        "head_before": git("rev-parse", "HEAD", cwd=working_directory),
    }
    write_attempt_common(directory, spec, prompt, metadata)
    append_event(run_dir, event="call_started", status="started", call_id=spec["call_id"], role=spec["agent"], model=config["model"], path=str(directory))
    command = ["codex", "exec", "--json", "--output-schema", str(CONTRACTS / "result.schema.json"), "-o", str(directory / "final-result.json"), "-m", config["model"], "-c", f"model_reasoning_effort={config['model_reasoning_effort']}", "-s", config["sandbox_mode"], "-C", str(working_directory), "-"]
    metadata["command"] = command
    timeout_seconds = spec.get("timeout_seconds", 7200)
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= 14400:
        raise PipelineError("timeout_seconds вызова должен быть целым числом от 1 до 14400")
    metadata["timeout_seconds"] = timeout_seconds
    if args.dry_run:
        atomic_text(directory / "raw-stdout.jsonl", "")
        atomic_text(directory / "stderr.txt", "")
        metadata.update({"head_after": git("rev-parse", "HEAD", cwd=working_directory), "finished_at": now(), "status": "dry_run"})
        atomic_json(directory / "metadata.json", metadata)
        append_event(run_dir, event="call_finished", status="dry_run", call_id=spec["call_id"], role=spec["agent"], model=config["model"], path=str(directory))
        print(f"Dry-run сохранён: {directory}")
        return 0
    try:
        completed = subprocess.run(command, input=prompt, text=True, capture_output=True, cwd=working_directory, timeout=timeout_seconds)
        atomic_text(directory / "raw-stdout.jsonl", completed.stdout)
        atomic_text(directory / "stderr.txt", completed.stderr)
        sanitize_result_file(directory)
        metadata["exit_code"] = completed.returncode
        if completed.returncode:
            raise PipelineError(f"Codex завершился с кодом {completed.returncode}")
        result = validate_result(directory / "final-result.json", spec, expected, working_directory, run_dir, run)
        metadata["result_status"] = result["status"]
        metadata["status"] = "completed"
        exit_code = 0
    except subprocess.TimeoutExpired as exc:
        atomic_text(directory / "raw-stdout.jsonl", exc.stdout or "")
        atomic_text(directory / "stderr.txt", exc.stderr or "")
        sanitize_result_file(directory)
        metadata.update({"status": "protocol_error", "timed_out": True, "error": f"Codex превысил timeout {timeout_seconds} секунд"})
        exit_code = 1
    except (OSError, PipelineError) as exc:
        sanitize_result_file(directory)
        atomic_text(directory / "raw-stdout.jsonl", (directory / "raw-stdout.jsonl").read_text(encoding="utf-8") if (directory / "raw-stdout.jsonl").exists() else "")
        atomic_text(directory / "stderr.txt", (directory / "stderr.txt").read_text(encoding="utf-8") if (directory / "stderr.txt").exists() else "")
        metadata["status"] = "protocol_error"
        metadata["error"] = str(exc)
        exit_code = 1
    metadata["head_after"] = git("rev-parse", "HEAD", cwd=working_directory)
    metadata["finished_at"] = now()
    atomic_json(directory / "metadata.json", metadata)
    if metadata["status"] == "completed":
        call_attestation(run, directory, metadata)
    append_event(run_dir, event="call_finished", status=metadata["status"], call_id=spec["call_id"], role=spec["agent"], model=config["model"], path=str(directory))
    if exit_code:
        raise PipelineError(metadata["error"])
    print(f"Вызов сохранён: {directory}")
    return 0


def command_import_result(args: argparse.Namespace) -> int:
    run_dir, run = load_run(args.run_dir)
    spec = read_json(Path(args.spec).expanduser().resolve())
    require_valid(spec, "call.schema.json", "Поручение")
    working_directory = verify_working_directory(spec, run)
    expected = verify_call_paths(spec, run_dir, run, working_directory)
    result_source = Path(args.result).expanduser().resolve()
    if not result_source.is_file():
        raise PipelineError(f"Файл внешнего результата не найден: {result_source}")
    config = config_for(spec["agent"])
    directory = attempt_dir(run_dir, spec["call_id"])
    metadata = {"call_id": spec["call_id"], "role": spec["agent"], "model": config["model"], "working_directory": str(working_directory), "started_at": now(), "status": "importing", "imported_from": str(result_source), "head_before": git("rev-parse", "HEAD", cwd=working_directory)}
    write_attempt_common(directory, spec, prompt_for(spec, config), metadata)
    append_event(run_dir, event="call_started", status="importing", call_id=spec["call_id"], role=spec["agent"], model=config["model"], path=str(directory))
    atomic_text(directory / "raw-stdout.jsonl", "")
    atomic_text(directory / "stderr.txt", "")
    atomic_text(directory / "final-result.json", result_source.read_text(encoding="utf-8"))
    try:
        result = validate_result(directory / "final-result.json", spec, expected, working_directory, run_dir, run)
        metadata["result_status"] = result["status"]
        metadata["status"] = "completed"
        exit_code = 0
    except PipelineError as exc:
        metadata.update({"status": "protocol_error", "error": str(exc)})
        exit_code = 1
    metadata["head_after"] = git("rev-parse", "HEAD", cwd=working_directory)
    metadata["finished_at"] = now()
    atomic_json(directory / "metadata.json", metadata)
    if metadata["status"] == "completed":
        call_attestation(run, directory, metadata)
    append_event(run_dir, event="call_imported", status=metadata["status"], call_id=spec["call_id"], role=spec["agent"], model=config["model"], path=str(directory))
    if exit_code:
        raise PipelineError(metadata["error"])
    print(f"Внешний результат сохранён: {directory}")
    return 0


def check_environment(spec: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    env_refs = spec.get("env_refs", [])
    if not isinstance(env_refs, list) or any(not isinstance(name, str) or not name for name in env_refs):
        raise PipelineError("env_refs проверки должен быть списком непустых имён переменных")
    if len(set(env_refs)) != len(env_refs):
        raise PipelineError("env_refs проверки не должен содержать повторов")
    environment = {name: os.environ[name] for name in CHECK_ENV_ALLOWLIST if name in os.environ}
    for name in env_refs:
        if name not in os.environ:
            raise PipelineError(f"Переменная из env_refs отсутствует в окружении: {name}")
        environment[name] = os.environ[name]
    return environment, env_refs


def sensitive_env_values() -> list[str]:
    return [value for name, value in os.environ.items() if SECRET_NAME_RE.search(name) and value]


def command_check(args: argparse.Namespace) -> int:
    run_dir, run = load_run(args.run_dir)
    spec = read_json(Path(args.spec).expanduser().resolve())
    require_valid(spec, "check.schema.json", "Проверка")
    working_directory = verify_working_directory(spec, run)
    environment, env_refs = check_environment(spec)
    explicit_env_values = [os.environ[name] for name in env_refs]
    forbidden = [argument for argument in spec["argv"] if CREDENTIAL_ARG_RE.search(argument)]
    forbidden.extend(argument for argument in spec["argv"] if any(value and value in argument for value in [*sensitive_env_values(), *explicit_env_values]))
    if forbidden:
        raise PipelineError("В argv проверки запрещены credential-параметры и фактические значения переменных окружения")
    directory = check_dir(run_dir, spec["check_id"])
    if directory.exists():
        raise PipelineError(f"Проверка с этим ID уже сохранена: {spec['check_id']}")
    private_dir(directory)
    atomic_json(directory / "check.json", spec)
    before_sha = git("rev-parse", "HEAD", cwd=working_directory)
    metadata: dict[str, Any] = {"check_id": spec["check_id"], "command": spec["argv"], "cwd": str(working_directory), "env_refs": env_refs, "head_before": before_sha, "started_at": now(), "status": "started"}
    atomic_json(directory / "metadata.json", metadata)
    append_event(run_dir, event="check_started", status="started", check_id=spec["check_id"], path=str(directory))
    try:
        completed = subprocess.run(spec["argv"], cwd=working_directory, text=True, capture_output=True, timeout=spec["timeout_seconds"], env=environment)
        stdout, stderr, code, timed_out = completed.stdout, completed.stderr, completed.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = redact_text(exc.stdout or "")
        stderr = redact_text(exc.stderr or "")
        code, timed_out = None, True
    except OSError as exc:
        stdout, stderr, code, timed_out = "", str(exc), None, False
    atomic_text(directory / "stdout.txt", redact_text(stdout, explicit_env_values))
    atomic_text(directory / "stderr.txt", redact_text(stderr, explicit_env_values))
    after_sha = git("rev-parse", "HEAD", cwd=working_directory)
    expected_codes = spec.get("expected_exit_codes", [0])
    passed = not timed_out and code in expected_codes and before_sha == after_sha
    metadata.update({"head_after": after_sha, "exit_code": code, "timed_out": timed_out, "finished_at": now(), "status": "passed" if passed else "failed"})
    atomic_json(directory / "metadata.json", metadata)
    check_attestation(run, directory, metadata)
    append_event(run_dir, event="check_finished", status=metadata["status"], check_id=spec["check_id"], path=str(directory))
    print(f"Проверка {'пройдена' if passed else 'не пройдена'}: {directory}")
    return 0 if passed else 1


def evidence_path(value: str, run_dir: Path, worktree: Path) -> Path:
    path = resolve(value, worktree)
    if not path.exists():
        raise PipelineError(f"Файл доказательства не найден: {path}")
    if not (is_within(path, run_dir) or is_within(path, worktree)):
        raise PipelineError(f"Доказательство должно находиться в запуске или репозитории: {path}")
    return path


def attempt_from_evidence(path: Path, run_dir: Path) -> Path | None:
    try:
        relative = path.relative_to(run_dir / "attempts")
        return run_dir / "attempts" / relative.parts[0]
    except ValueError:
        return None


def check_from_evidence(path: Path, run_dir: Path) -> Path | None:
    try:
        relative = path.relative_to(run_dir / "checks")
        return run_dir / "checks" / relative.parts[0]
    except ValueError:
        return None


def completed_attempt_for_role(evidence: list[Path], run_dir: Path, run: dict[str, Any], role: str, current_head: str | None = None) -> bool:
    for path in evidence:
        attempt = attempt_from_evidence(path, run_dir)
        if attempt is None:
            continue
        metadata = read_json(attempt / "metadata.json")
        call_id = metadata.get("call_id")
        if not isinstance(call_id, str):
            continue
        payload = attestation(run, "call", call_id, attempt, {
            "call_spec": attempt / "call.json", "metadata": attempt / "metadata.json",
            "final_result": attempt / "final-result.json", "raw_stdout": attempt / "raw-stdout.jsonl", "stderr": attempt / "stderr.txt",
        })
        if payload.get("status") != "completed" or payload.get("role") != role or payload.get("result_status") != "completed":
            continue
        if current_head is None or (payload.get("head_before") == current_head and payload.get("head_after") == current_head):
            return True
    return False


def current_check_from_evidence(evidence: list[Path], run_dir: Path, run: dict[str, Any], current_head: str) -> bool:
    for path in evidence:
        check = check_from_evidence(path, run_dir)
        if check is None:
            continue
        metadata = read_json(check / "metadata.json")
        check_id = metadata.get("check_id")
        if not isinstance(check_id, str):
            continue
        payload = attestation(run, "check", check_id, check, {
            "check_spec": check / "check.json", "metadata": check / "metadata.json",
            "stdout": check / "stdout.txt", "stderr": check / "stderr.txt",
        })
        if payload.get("status") == "passed" and payload.get("head_before") == current_head and payload.get("head_after") == current_head:
            return True
    return False


def not_applicable_evidence_is_separate(evidence: list[Path], run_dir: Path) -> bool:
    """Неприменимость должна быть объяснена отдельным файлом запуска, не логом роли."""
    return bool(evidence) and any(
        is_within(path, run_dir)
        and not is_within(path, run_dir / "attempts")
        and not is_within(path, run_dir / "checks")
        for path in evidence
    )


def application_tree_is_clean(worktree: Path, run_dir: Path) -> bool:
    allowed = run_dir.relative_to(worktree)
    output = git("status", "--porcelain", "--untracked-files=all", cwd=worktree)
    for line in output.splitlines():
        filename = line[3:]
        if " -> " in filename:
            filename = filename.split(" -> ", 1)[1]
        path = Path(filename)
        if not is_within((worktree / path).resolve(), (worktree / allowed).resolve()):
            return False
    return True


def command_finish(args: argparse.Namespace) -> int:
    run_dir, run = load_run(args.run_dir)
    completion = read_json(Path(args.spec).expanduser().resolve())
    try:
        require_valid(completion, "completion.schema.json", "Итог")
        worktree = Path(run["worktree"]).resolve()
        current_head = git("rev-parse", "HEAD", cwd=worktree)
        if subprocess.run(["git", "merge-base", "--is-ancestor", run["base_sha"], current_head], cwd=worktree).returncode:
            raise PipelineError("Текущий HEAD не является потомком base_sha этого запуска")
        evidence_by_gate: dict[str, list[Path]] = {}
        git_evidence: list[Path] = []
        for gate_name in ("prototype", "test_plan", "review", "test_execution", "browser_acceptance", "git_saved"):
            gate = completion[gate_name]
            evidence_by_gate[gate_name] = []
            for item in gate["evidence"]:
                path = evidence_path(item, run_dir, worktree)
                evidence_by_gate[gate_name].append(path)
                if gate_name == "git_saved":
                    git_evidence.append(path)
        for gate_name, role in (("test_plan", "tester"), ("review", "reviewer")):
            required_head = current_head if role == "reviewer" else None
            if not completed_attempt_for_role(evidence_by_gate[gate_name], run_dir, run, role, required_head):
                raise PipelineError(f"{gate_name}.evidence должно ссылаться на completed попытку роли {role}")
        for gate_name, role in (("prototype", "developer"), ("browser_acceptance", "clicker")):
            required_head = current_head if role == "clicker" else None
            if completion[gate_name]["status"] == "passed" and not completed_attempt_for_role(evidence_by_gate[gate_name], run_dir, run, role, required_head):
                raise PipelineError(f"{gate_name}.evidence должно ссылаться на completed попытку роли {role}")
        for gate_name in ("prototype", "test_plan", "review", "test_execution", "browser_acceptance", "git_saved"):
            if completion[gate_name]["status"] == "not_applicable" and not not_applicable_evidence_is_separate(evidence_by_gate[gate_name], run_dir):
                raise PipelineError(f"Для not_applicable гейта {gate_name} нужен отдельный непустой артефакт текущего запуска")
        if not current_check_from_evidence(evidence_by_gate["test_execution"], run_dir, run, current_head):
            raise PipelineError("test_execution.evidence должно ссылаться на passed check текущего запуска на текущем HEAD")
        if not git_evidence:
            raise PipelineError("Для git_saved нужно хотя бы одно файловое доказательство с SHA commit")
        saved_shas: set[str] = set()
        for path in git_evidence:
            for candidate in SHA_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
                if subprocess.run(["git", "cat-file", "-e", f"{candidate}^{{commit}}"], cwd=worktree).returncode == 0:
                    saved_shas.add(candidate)
        if current_head not in saved_shas:
            raise PipelineError("В доказательствах git_saved должен быть указан точный текущий HEAD")
        if not application_tree_is_clean(worktree, run_dir):
            raise PipelineError("В worktree есть несохранённые изменения вне артефактов текущего запуска")
        atomic_json(run_dir / "COMPLETION.json", completion)
        append_event(run_dir, event="finish_accepted", status="accepted", path=str(run_dir), head=current_head, saved_shas=sorted(saved_shas))
        print("Завершение принято; push и deploy намеренно не выполнялись.")
        return 0
    except PipelineError as exc:
        append_event(run_dir, event="finish_rejected", status="rejected", path=str(run_dir), error=str(exc))
        raise


def command_status(args: argparse.Namespace) -> int:
    run_dir, run = load_run(args.run_dir)
    print(f"Запуск: {run_dir}\nWorktree: {run['worktree']}\nBase SHA: {run['base_sha']}")
    problems: list[str] = []
    for title, directory in (("Вызовы", run_dir / "attempts"), ("Проверки", run_dir / "checks")):
        print(f"{title}:")
        entries = sorted(directory.iterdir()) if directory.exists() else []
        if not entries:
            print("  нет")
        for entry in entries:
            try:
                metadata = read_json(entry / "metadata.json")
                state = metadata.get("status", "неизвестно")
                print(f"  {entry.name}: {state}")
                if state not in {"completed", "passed", "dry_run"}:
                    problems.append(f"{entry.name}: {state}")
            except PipelineError as exc:
                problems.append(str(exc))
                print(f"  {entry.name}: повреждён журнал")
    print("Проблемы: " + ("; ".join(problems) if problems else "нет"))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--run-dir", required=True)
    init.add_argument("--request-file", required=True)
    init.add_argument("--base-sha")
    call = commands.add_parser("call")
    call.add_argument("--run-dir", required=True)
    call.add_argument("--spec", required=True)
    call.add_argument("--dry-run", action="store_true")
    imported = commands.add_parser("import-result")
    imported.add_argument("--run-dir", required=True)
    imported.add_argument("--spec", required=True)
    imported.add_argument("--result", required=True)
    check = commands.add_parser("check")
    check.add_argument("--run-dir", required=True)
    check.add_argument("--spec", required=True)
    status = commands.add_parser("status")
    status.add_argument("--run-dir", required=True)
    finish = commands.add_parser("finish")
    finish.add_argument("--run-dir", required=True)
    finish.add_argument("--spec", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    handlers = {"init": command_init, "call": command_call, "import-result": command_import_result, "check": command_check, "status": command_status, "finish": command_finish}
    try:
        return handlers[args.command](args)
    except PipelineError as exc:
        print(f"Ошибка диспетчера: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
