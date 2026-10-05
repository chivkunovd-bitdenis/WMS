"""Интерактивные макеты выполняет Sonnet и публикует с проверкой открытой ссылки."""

from __future__ import annotations

import hashlib
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
        if self.p.clock() < float(d.get("mockup_next_poll", 0)):
            return
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
            prompt = prompts.mockup_prompt(task, str(tid))
            previous_review = d.get("mockup_review") or {}
            if previous_review.get("version") == version and previous_review.get("feedback"):
                prompt += "\n\nИсправь замечания Astra по этому макету: " + previous_review["feedback"]
            if mockup.get("recovery_note"):
                prompt += ("\n\nPrevious run was interrupted. Inspect the existing worktree and "
                           "already published URL before changing files or publishing. "
                           "Reuse the completed artifact if valid; do not delete or duplicate it.")
            try:
                turn = self.p.llm.agent_turn(
                    prompt,
                    session_key=f"mockup:{tid}", model="sonnet", provider="claude",
                    mode="write", cwd=str(path), timeout=3600,
                )
            except LlmUnavailable:
                turn = self.p.llm.agent_turn(
                    prompt,
                    session_key=f"mockup:{tid}", model="gpt-5.6-sol", provider="codex",
                    effort="high", mode="write", cwd=str(path), timeout=3600,
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
            review, _ = self.p.llm.ask_json(
                "review",
                "Проверь кликабельный макет по требованиям ниже. Прочитай AGENTS.md, "
                "docs/reviews/2026-09-11-analyst-draft/owner-cases.md и failure-cases.md "
                "из той же папки целиком. Проверь сохранение текущего интерфейса и объёма задачи. "
                f"Файлы макета: {rel}. Ничего не изменяй. "
                'Верни JSON {"accepted":true|false,"summary":"конкретные дефекты или результат"}.\n'
                + task,
                ticket_id=tid, mode="readonly", cli_only="codex", cwd=str(path), timeout=1800,
                session_key=f"mockup:{tid}:review",
            )
            if version and self.p.store.data(tid).get("agent", {}).get("version") != version:
                return
            if review.get("accepted") is not True:
                feedback = str(review.get("summary") or "есть замечания")
                digest = hashlib.sha256()
                for item in sorted(out.rglob("*")):
                    if item.is_file() and not item.is_symlink():
                        digest.update(str(item.relative_to(out)).encode())
                        digest.update(item.read_bytes())
                fingerprint = digest.hexdigest()
                if (previous_review.get("version") == version
                        and previous_review.get("fingerprint") == fingerprint
                        and previous_review.get("feedback") == feedback):
                    raise StepFailed("макет не исправлен после замечаний Astra: " + feedback)
                self.p.store.patch_data(tid, mockup_review={
                    "version": version, "feedback": feedback, "fingerprint": fingerprint,
                })
                if version:
                    latest = self.p.store.data(tid).get("agent") or {}
                    if latest.get("version") == version:
                        latest["mockup"] = {**latest["mockup"], "status": "queued"}
                        self.p.store.patch_data(tid, agent=latest)
                return
            self.hf.git("add", "--", str(out.relative_to(path)), cwd=path)
            if self.hf.git("diff", "--cached", "--name-only", cwd=path):
                task_number = agent.get("wms_number") or "641"
                self.hf.git("commit", "-m", f"docs(WMS-{task_number}): save mockup {name}", cwd=path)
            sha = self.hf.git("rev-parse", "HEAD", cwd=path).strip()
            self.hf.git("push", "-u", "origin", branch, cwd=path)
            link = self._publish(name, out, tid, version)
        except (LlmError, LlmUnavailable) as exc:
            latest = self.p.store.data(tid).get("agent") or {}
            if version and latest.get("version") != version:
                return
            if version:
                latest["mockup"] = {**latest["mockup"], "status": "queued"}
                self.p.store.patch_data(tid, agent=latest)
            self.p.store.patch_data(tid, mockup_next_poll=self.p.clock() + 60,
                                    mockup_retry_reason=str(exc))
            return
        except (StepFailed, PublishError, ValueError) as exc:
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
