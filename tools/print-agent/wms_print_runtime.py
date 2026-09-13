"""WMS-442: paired unattended runtime around the WMS-402 file/queue adapter.

The single inflight file is an acknowledgement outbox, not a print history.
After submitting may have begun, it is NEVER used to resubmit a document.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import plistlib
import secrets
import subprocess
import sys
import time
import urllib.error
import uuid
from pathlib import Path
from typing import Any

import wms_print_agent as agent

PREFIX = "/operations/print"


def state_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "WMS Print"
    if sys.platform.startswith("linux"):
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "wms-print"
    raise ValueError("Эта сборка поддерживает macOS/CUPS. Windows пока не поддерживается.")


def write_private(path: Path, value: dict[str, Any]) -> None:
    """Atomic replacement with fsync, so restart cannot lose the submission boundary."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    tmp = path.with_suffix(".new")
    descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(tmp, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_private(path: Path) -> dict[str, Any]:
    with path.open() as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Неверный файл настройки программы")
    return value


@contextlib.contextmanager
def single_instance(directory: Path):
    import fcntl

    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "runtime.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Программа печати уже запущена в этом профиле") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class CupsAdapter:
    """Only installed queues, fixed executable, no shell or downloaded commands."""

    def __init__(self, run: Any = subprocess.run, platform: str = sys.platform):
        if platform not in {"darwin", "linux"}:
            raise ValueError("Очередь этой ОС не поддерживается")
        self.run = run

    def queues(self) -> list[str]:
        result = self.run(
            ["/usr/bin/lpstat", "-p"], capture_output=True, text=True, timeout=15,
            check=False, env={**os.environ, "LC_ALL": "C"},
        )
        names = []
        for line in result.stdout.splitlines():
            words = line.split()
            if len(words) > 1 and words[0] == "printer":
                names.append(agent.check_queue(words[1]))
        return sorted(set(names))

    def submit(self, data: bytes, mime: str, queue: str, copies: int) -> str:
        agent.check_queue(queue)
        if queue not in self.queues():
            raise ValueError("Назначенная очередь отсутствует в ОС. Проверьте установленный принтер.")
        return agent.submit_to_queue(data, mime, queue, self.run, copies=copies,
                                     executable="/usr/bin/lp")


class Client:
    def __init__(self, config: dict[str, Any]):
        self.base = agent.check_base_url(config["base_url"])
        self.token = config["device_token"]

    def api(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return agent._api(self.base, self.token, "POST", PREFIX + path, body=body or {})

    def fetch(self, job: dict[str, Any], expected: dict[str, Any]) -> bytes:
        return agent.fetch_label(
            self.base, self.token, str(uuid.UUID(job["id"])), job["warehouse_id"], expected,
            claim_id=str(uuid.UUID(job["claim_id"])),
        )


def validate_destination(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    expected = agent.validate_job(job, config["warehouse_id"])
    uuid.UUID(job["claim_id"])
    if job.get("connection_id") != config["connection_id"] or job.get("queue_name") != config["queue_name"]:
        raise ValueError("Назначение задания отличается от сопряжённой очереди")
    copies = job.get("copies")
    if type(copies) is not int or not 1 <= copies <= 999:
        raise ValueError("Некорректное число копий")
    size = job.get("content_bytes")
    if type(size) is not int or not 1 <= size <= agent.MAX_BYTES:
        raise ValueError("Некорректный размер этикетки")
    expected["content_bytes"] = size
    return expected


def acknowledge(client: Client, inflight: dict[str, Any]) -> None:
    client.api("/agent/jobs/" + str(uuid.UUID(inflight["job_id"])) + "/result", inflight["result"])


def process_once(config: dict[str, Any], directory: Path, client: Client,
                 adapter: CupsAdapter) -> str:
    """Caller holds the profile lock. Server independently claims across profiles/PCs."""
    outbox = directory / "inflight.json"
    if outbox.exists():
        previous = read_private(outbox)
        if previous["phase"] == "result":
            acknowledge(client, previous)
            outbox.unlink()
            return "Квитанция восстановлена; повторной передачи в ОС не было."
        # Crash in/before native call: no receipt proves rejection. WMS already
        # retains running. Discard only the local outbox and continue on next tick.
        outbox.unlink()
        return "Результат печати неизвестен. Проверьте очередь принтера; повтор не выполнялся."
    job = client.api("/agent/next").get("job")
    if job is None:
        return ""
    job_id = str(uuid.UUID(job["id"]))
    claim_id = str(uuid.UUID(job["claim_id"]))
    marker: dict[str, Any] = {"phase": "preparing", "job_id": job_id, "claim_id": claim_id}
    write_private(outbox, marker)
    try:
        expected = validate_destination(job, config)
        content = client.fetch(job, expected)
        if len(content) != expected["content_bytes"]:
            raise ValueError("Размер этикетки изменился после создания задания")
        # Failures before the durable boundary below are known not to have spooled.
        if job["queue_name"] not in adapter.queues():
            raise ValueError("Назначенная очередь отсутствует в ОС")
    except (ValueError, KeyError, TypeError, OSError, urllib.error.URLError) as exc:
        marker["phase"] = "result"
        marker["result"] = {"claim_id": claim_id, "queue_receipt": None,
                            "handed_to_queue": False,
                            "error_message": "Файл или очередь не прошли проверку: " + type(exc).__name__}
    else:
        marker["phase"] = "submitting"
        write_private(outbox, marker)
        try:
            receipt = adapter.submit(content, expected["content_type"], job["queue_name"], job["copies"])
        except (agent.UnknownPrintOutcome, OSError, ValueError):
            # Keep the boundary until next start/tick. Neither a retry nor a
            # negative receipt is justified if the native call might have run.
            return "Результат печати неизвестен. Автоматическая повторная отправка запрещена."
        marker["phase"] = "result"
        marker["result"] = {"claim_id": claim_id, "queue_receipt": receipt,
                            "handed_to_queue": True, "error_message": None}
    write_private(outbox, marker)
    acknowledge(client, marker)
    outbox.unlink()
    return ("Передано в очередь принтера. Бумагу проверьте на принтере."
            if marker["result"]["handed_to_queue"] else "Не передано в очередь принтера.")


def enable_autostart(directory: Path, executable: Path) -> Path:
    if sys.platform != "darwin":
        raise ValueError("Автозапуск этой сборки проверяется только на macOS")
    if not getattr(sys, "frozen", False):
        raise ValueError("Автозапуск включается из распространяемой сборки программы")
    target = Path.home() / "Library" / "LaunchAgents" / "ru.wms.print-agent.plist"
    target.parent.mkdir(parents=True, exist_ok=True)
    value = {"Label": "ru.wms.print-agent", "ProgramArguments": [str(executable), "--run"],
             "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 15,
             "StandardOutPath": str(directory / "runtime.log"),
             "StandardErrorPath": str(directory / "runtime.log")}
    target.write_bytes(plistlib.dumps(value))
    target.chmod(0o600)
    return target


def setup(directory: Path, adapter: CupsAdapter) -> dict[str, Any]:
    config_path = directory / "connection.json"
    if config_path.exists():
        config = read_private(config_path)
    else:
        base = agent.check_base_url(input("HTTPS-адрес API WMS: ").strip())
        queues = adapter.queues()
        if not queues:
            raise ValueError("В ОС нет принтеров. Сначала установите драйвер и очередь через настройки ОС.")
        print("Установленные очереди принтеров:")
        for index, queue in enumerate(queues, 1):
            print(f"{index}. {queue}")
        chosen = int(input("Номер принтера: "))
        if not 1 <= chosen <= len(queues):
            raise ValueError("Номер принтера отсутствует")
        config = {"base_url": base, "queue_name": queues[chosen - 1], "platform": sys.platform,
                  "connection_id": str(uuid.uuid4()), "device_token": secrets.token_urlsafe(32)}
        write_private(config_path, config)
    client = Client(config)
    paired = client.api("/pairing", {k: config[k] for k in
                       ("connection_id", "device_token", "queue_name", "platform")})
    if not paired["paired"]:
        print("В WMS выберите склад и введите код подключения: " + paired["pairing_code"])
        print("Код действует 15 минут. После подтверждения программа подключится сама.")
        while True:
            time.sleep(3)
            paired = client.api("/agent/heartbeat")
            if paired["paired"]:
                break
    config["warehouse_id"] = paired["warehouse_id"]
    write_private(config_path, config)
    print("Подключено. Очередь: " + config["queue_name"])
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        if input("Запускать при входе в macOS? [д/Н]: ").strip().lower() in {"д", "y"}:
            enable_autostart(directory, Path(sys.executable).resolve())
            print("Автозапуск включён для следующего входа в macOS.")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WMS: подключение ПК и печать этикеток")
    parser.add_argument("--run", action="store_true", help="Работать с сохранённым подключением")
    parser.add_argument("--once", action="store_true", help="Проверить соединение и одно задание")
    parser.add_argument("--list-printers", action="store_true", help="Показать очереди ОС и выйти")
    args = parser.parse_args(argv)
    try:
        adapter = CupsAdapter()
        if args.list_printers:
            print("\n".join(adapter.queues()) or "В ОС нет настроенных очередей принтеров.")
            return 0
        directory = state_directory()
        with single_instance(directory):
            config = read_private(directory / "connection.json") if args.run else setup(directory, adapter)
            client = Client(config)
            while True:
                try:
                    status = client.api("/agent/heartbeat")
                    if not status["paired"]:
                        raise ValueError("Подключение ещё не подтверждено в WMS")
                    message = process_once(config, directory, client, adapter)
                    if message:
                        print(message, flush=True)
                except (OSError, ValueError, KeyError, urllib.error.URLError):
                    print("Связь с WMS недоступна. Квитанция сохранена; передача в ОС не повторяется.",
                          file=sys.stderr, flush=True)
                    if args.once:
                        return 2
                if args.once:
                    return 0
                time.sleep(3)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        # Never dump HTTP bodies, URLs or credential-bearing configuration.
        print("Программа не подключена. Проверьте адрес WMS, очередь ОС и срок кода подключения.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
