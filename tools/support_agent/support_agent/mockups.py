"""Интерактивные макеты выполняет Sonnet и публикует с проверкой открытой ссылки."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from . import prompts
from .hotfix import HotfixRunner, StepFailed
from .llm import LlmError, LlmUnavailable, extract_json
from .pipeline import Pipeline
from .publish_mockup import PublishError, publish


class MockupRunner:
    def __init__(self, pipe: Pipeline, hotfix: HotfixRunner) -> None:
        self.p = pipe
        self.hf = hotfix

    def run(self, tid: int) -> None:
        cfg = self.p.cfg
        d = self.p.store.data(tid)
        agent = d.get("agent") or {}
        version = agent.get("version")
        mockup = agent.get("mockup") or {}
        name = f"mockup-{tid}-{version[:12]}" if version else f"mockup-{tid}"
        branch = f"mockup/wms-support-{tid}-{version[:12]}" if version else f"mockup/wms-support-{tid}"
        base = f"origin/{agent['document_branch']}" if agent.get("document_branch") else "origin/etalon"
        path = Path(cfg.repo) / ".worktrees" / name
        try:
            if version and mockup.get("version") != version:
                raise StepFailed("версия описания макета изменилась")
            if not path.exists():
                self.hf.fetch()
                self.hf.git("worktree", "add", "-b", branch, str(path), base)
            task = str(agent.get("description") or
                       (self.p._task_text(d) if d.get("draft") else d.get("raw", "")))
            prompt = prompts.mockup_prompt(task, str(tid)).replace("Ты — Opus", "Ты — Sonnet")
            if mockup.get("recovery_note"):
                prompt += ("\n\nPrevious run was interrupted. Inspect the existing worktree and "
                           "already published URL before changing files or publishing. "
                           "Reuse the completed artifact if valid; do not delete or duplicate it.")
            turn = self.p.llm.agent_turn(
                prompt,
                session_key=f"mockup:{tid}", model="sonnet", provider="claude",
                mode="write", cwd=str(path), timeout=3600,
            )
            res = extract_json(turn.text)
            out = (path / str(res.get("dir", ""))).resolve()
            if not out.is_dir() or path.resolve() not in out.parents:
                raise StepFailed("макет не собран: папка с результатом не найдена")
            if version and self.p.store.data(tid).get("agent", {}).get("version") != version:
                return  # Устаревший макет не публикуем и не называем готовым.
            variants = "\n".join(f"- {v}" for v in res.get("variants") or [])
            changed = self.hf.git("status", "--porcelain", cwd=path).splitlines()
            rel = str(out.relative_to(path)) + "/"
            if any(not line[3:].startswith(rel) for line in changed):
                raise StepFailed("макет изменил файлы вне своей папки")
            self.hf.git("add", "--", str(out.relative_to(path)), cwd=path)
            if self.hf.git("diff", "--cached", "--name-only", cwd=path):
                task_number = agent.get("wms_number") or "641"
                self.hf.git("commit", "-m", f"docs(WMS-{task_number}): save mockup {name}", cwd=path)
            sha = self.hf.git("rev-parse", "HEAD", cwd=path).strip()
            self.hf.git("push", "-u", "origin", branch, cwd=path)
            link = self._publish(name, out, tid, version)
        except (StepFailed, LlmError, LlmUnavailable, PublishError, ValueError) as exc:
            self.p.store.set_stage(tid, "failed")
            self.p.say_owner(f"mockup_fail:{tid}", f"Макет по задаче №{tid} не получился: {exc}", tid)
            return
        if version:
            latest = self.p.store.data(tid).get("agent") or {}
            if latest.get("version") != version:
                return  # Публикация могла завершиться после правки; не сообщаем устаревшую ссылку.
            if (latest.get("mockup") or {}).get("url") != link:
                latest.pop("mockup_approval", None)
            latest["mockup"] = {"version": version, "status": "published", "url": link,
                                "variants": res.get("variants") or [], "source_sha": sha}
            self.p.store.patch_data(tid, agent=latest, mockup_link=link)
        else:
            self.p.store.set_stage(tid, "done", mockup_link=link,
                                   mockup_variants=json.dumps(res.get("variants")))
        text = f"Макеты по задаче №{tid} готовы:\n{variants}\n{link}"
        self.p.say_owner(f"mockup_done:{tid}:{version or 'legacy'}", text, tid, "mockup")

    def _publish(self, name: str, out: Path, tid: int, version: str | None) -> str:
        key = f"mockup_public_id:{tid}:{version or 'legacy'}"
        public_id = self.p.store.kv_get(key)
        if not public_id:
            public_id = secrets.token_hex(12)
            self.p.store.kv_set(key, public_id)
        return publish(out, public_id=public_id)
