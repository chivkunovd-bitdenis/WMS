"""One Codex app-server turn, with native project tools and service-owned dynamic tools.

The process is short lived. Codex stores the thread; SQLite stores its ID and the
authoritative business state. This keeps model sessions independent from the bot's
poller and allows a restart without replaying side effects.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class AppServerError(RuntimeError):
    pass


Event = dict[str, Any]
ToolHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


def _occupancy(usage: dict[str, Any]) -> int:
    """Only the last context, never cumulative total lifetime token usage."""
    last = usage.get("last") or {}
    return int(last.get("totalTokens") or 0)


class AppServerTurn:
    def __init__(self, binary: str, *, timeout: int = 900) -> None:
        self.binary = binary
        self.timeout = timeout

    def run(
        self,
        prompt: str,
        *,
        model: str,
        provider: str,
        effort: str,
        cwd: str,
        mode: str,
        system: str,
        session_id: str | None,
        tools: list[dict[str, Any]],
        tool_handler: ToolHandler | None,
        session_started: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        redact_error: Callable[[str], str] | None = None,
    ) -> tuple[str, str, int]:
        if mode not in ("readonly", "write", "owner"):
            raise ValueError(f"unsupported agent mode: {mode}")
        if not Path(cwd).is_dir():
            raise ValueError("agent cwd must exist")
        if tools and tool_handler is None:
            raise ValueError("dynamic tools need a handler")
        # Bot credentials are kept out of native shell processes. Dynamic tools
        # perform all Telegram/Trello actions behind trusted service boundaries.
        from . import sandbox

        env = {key: value for key, value in os.environ.items() if key not in sandbox.SENSITIVE_ENV}
        argv = [self.binary, "app-server", "--stdio", "-c", "web_search=\"disabled\"",
                "-c", "approval_policy=\"never\""]
        for feature in ("apps", "plugins", "remote_plugin", "multi_agent", "browser_use",
                        "computer_use", "image_generation"):
            argv += ["--disable", feature]
        if mode == "readonly":
            # Client messages get service tools, not native shell/file mutation.
            argv += ["--disable", "shell_tool", "--disable", "unified_exec"]
        elif mode == "write":
            # Native Codex shell/editor handles arbitrary owner jobs, including
            # exports and build commands. The workspace sandbox bounds writes.
            argv += ["-c", "sandbox_workspace_write.network_access=false"]
        # 'owner' uses native shell/editor with normal project access and network.
        # It is reachable only after LlmRouter's explicit trusted owner gate.
        proc = subprocess.Popen(  # noqa: S603 - fixed binary and arguments
            argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        inbox: queue.Queue[Event | None] = queue.Queue()

        def read_stdout() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        inbox.put(parsed)
                except json.JSONDecodeError:
                    continue
            inbox.put(None)

        reader = threading.Thread(target=read_stdout, daemon=True)
        reader.start()
        next_id = 1
        deadline = time.monotonic() + self.timeout
        events: list[Event] = []
        active_turn: dict[str, str] = {}

        def send(payload: Event) -> None:
            if proc.stdin is None:
                raise AppServerError("app-server stdin unavailable")
            try:
                proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise AppServerError("app-server stopped") from exc

        def receive() -> Event:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppServerError("app-server turn timed out; outcome unknown")
                if cancelled is not None and cancelled():
                    if active_turn:
                        send({"id": -1, "method": "turn/interrupt", "params": active_turn})
                    raise AppServerError("agent turn cancelled; external outcome must be verified")
                try:
                    event = inbox.get(timeout=min(remaining, 1.0))
                except queue.Empty:
                    continue
                if event is None:
                    raise AppServerError(f"app-server stopped (exit {proc.poll()})")
                return event

        def rpc(method: str, params: Event) -> Event:
            nonlocal next_id
            request_id = next_id
            next_id += 1
            send({"id": request_id, "method": method, "params": params})
            while True:
                event = receive()
                if event.get("id") == request_id:
                    if "error" in event:
                        raise AppServerError(f"{method}: {event['error']}")
                    return event.get("result") or {}
                events.append(event)

        try:
            rpc("initialize", {"clientInfo": {"name": "wms-support-agent", "version": "1"},
                               "capabilities": {"experimentalApi": True}})
            send({"method": "initialized", "params": {}})
            if session_id:
                # A thread may have been compacted or moved; failure is reported
                # rather than silently losing its context.
                thread = rpc("thread/resume", {"threadId": session_id}).get("thread") or {}
            else:
                thread_response = rpc("thread/start", {
                    "model": model,
                    "allowProviderModelFallback": False,
                    "cwd": cwd, "sandbox": {"readonly": "read-only", "write": "workspace-write",
                                                "owner": "danger-full-access"}[mode],
                    "approvalPolicy": "never", "developerInstructions": system,
                    "dynamicTools": tools,
                })
                if thread_response.get("model") != model:
                    raise AppServerError("requested model was not selected")
                thread = thread_response.get("thread") or {}
            thread_id = thread.get("id") or session_id
            if not isinstance(thread_id, str) or not thread_id:
                raise AppServerError("app-server did not return a thread ID")
            if session_started is not None:
                session_started(thread_id)
            started_turn = rpc("turn/start", {"threadId": thread_id,
                                              "input": [{"type": "text", "text": prompt}],
                                              "model": model, "effort": effort})
            turn_id = (started_turn.get("turn") or {}).get("id")
            if isinstance(turn_id, str):
                active_turn.update({"threadId": thread_id, "turnId": turn_id})
            answer = ""
            occupied = 0
            while True:
                event = events.pop(0) if events else receive()
                method = event.get("method")
                params = event.get("params") or {}
                if method == "item/tool/call":
                    call_id = event.get("id")
                    name = params.get("tool")
                    namespace = params.get("namespace")
                    if namespace:
                        name = f"{namespace}.{name}"
                    allowed = {spec["name"] for spec in tools if spec.get("type") == "function"}
                    allowed.update(f"{spec['name']}.{tool['name']}" for spec in tools
                                   if spec.get("type") == "namespace"
                                   for tool in spec.get("tools", []))
                    try:
                        if name not in allowed or tool_handler is None:
                            raise ValueError("tool unavailable in this scope")
                        result = tool_handler(str(name), params.get("arguments") or {})
                        response = {"success": True, "contentItems": [{"type": "inputText",
                                    "text": json.dumps(result, ensure_ascii=False)}]}
                    except Exception as exc:  # noqa: BLE001 - tool failure returns to the model
                        detail = str(exc)[:160] if isinstance(exc, (ValueError, PermissionError)) else ""
                        if redact_error is not None:
                            detail = redact_error(detail)
                        response = {"success": False, "contentItems": [{"type": "inputText",
                                    "text": f"Tool failed: {type(exc).__name__}: {detail}"}]}
                    send({"id": call_id, "result": response})
                elif method == "thread/tokenUsage/updated":
                    occupied = _occupancy(params.get("tokenUsage") or {})
                elif method == "item/completed":
                    item = params.get("item") or {}
                    if item.get("type") == "agentMessage" and item.get("phase") in ("final", None):
                        answer = str(item.get("text") or answer)
                elif method == "turn/completed":
                    turn = params.get("turn") or {}
                    if turn.get("status") == "failed":
                        raise AppServerError(f"agent turn failed: {turn.get('error')}")
                    return answer, thread_id, occupied
                elif "id" in event and "method" in event:
                    # Never strand an approval or account request indefinitely.
                    send({"id": event["id"], "error": {"code": -32000,
                          "message": "unsupported app-server request"}})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
