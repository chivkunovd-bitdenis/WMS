"""Макеты по просьбе владельца (R31): только Opus, отдельный worktree, в основную ветку не вливается."""

from __future__ import annotations

import json
from pathlib import Path

from . import prompts
from .hotfix import HotfixRunner, StepFailed
from .pipeline import Pipeline


class MockupRunner:
    def __init__(self, pipe: Pipeline, hotfix: HotfixRunner) -> None:
        self.p = pipe
        self.hf = hotfix

    def run(self, tid: int) -> None:
        cfg = self.p.cfg
        d = self.p.store.data(tid)
        name = f"mockup-{tid}"
        path = Path(cfg.repo) / ".worktrees" / name
        try:
            if not path.exists():
                self.hf.fetch()
                self.hf.git("worktree", "add", "-b", f"mockup/wms-support-{tid}", str(path),
                            "origin/etalon")
            task = self.p._task_text(d) if d.get("draft") else d.get("raw", "")
            res, _ = self.p.llm.ask_json(
                "mockup", prompts.mockup_prompt(task, str(tid)), ticket_id=tid,
                session_key="mockup", mode="write", cwd=str(path), cli_only="claude", timeout=3600,
            )
            out = (path / str(res.get("dir", ""))).resolve()
            if not out.is_dir() or path.resolve() not in out.parents:
                raise StepFailed("макет не собран: папка с результатом не найдена")
            variants = "\n".join(f"- {v}" for v in res.get("variants") or [])
            link = self._publish(name, out)
        except StepFailed as exc:
            self.p.store.set_stage(tid, "failed")
            self.p.say_owner(f"mockup_fail:{tid}", f"Макет по задаче №{tid} не получился: {exc}", tid)
            return
        text = f"Макеты по задаче №{tid} готовы:\n{variants}\n{link}"
        self.p.say_owner(f"mockup_done:{tid}", text, tid, "mockup")
        self.p.store.set_stage(tid, "done", mockup_link=link, mockup_variants=json.dumps(res.get("variants")))

    def _publish(self, name: str, out: Path) -> str:
        cfg = self.p.cfg.mockups
        if not cfg.publish_cmd:
            return (f"Публикация по ссылке не настроена (mockups.publish_cmd), макет лежит локально: {out}")
        cmd = cfg.publish_cmd.replace("{dir}", str(out)).replace("{name}", name)
        self.hf.must(["bash", "-lc", cmd], timeout=600)
        return f"{cfg.base_url.rstrip('/')}/{name}/"
