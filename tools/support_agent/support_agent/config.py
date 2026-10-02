"""Один локальный файл конфигурации вне Git. Секреты не печатаются (R37)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, TypeVar

DEFAULT_CONFIG_PATH = "~/.wms-support-agent/config.json"
T = TypeVar("T")


@dataclass
class ChatCfg:
    role: str  # client | partner
    seller: str = ""


@dataclass
class TelegramCfg:
    bot_token: str = field(default="", repr=False)
    owner_user_id: int = 0
    owner_chat_id: int = 0
    chats: dict[int, ChatCfg] = field(default_factory=dict)


@dataclass
class TrelloCfg:
    api_key: str = field(default="", repr=False)
    token: str = field(default="", repr=False)
    board_id: str = ""
    client_list_id: str = ""
    partner_list_id: str = ""
    in_progress_list_id: str = ""
    completed_list_id: str = ""
    client_label_id: str = ""


@dataclass
class WmsCfg:
    base_url: str = ""
    agent_key: str = field(default="", repr=False)
    poll_interval_sec: int = 60


@dataclass
class LimitsCfg:
    max_parallel: int = 3
    quiet_sec: int = 120
    batch_wait_sec: int = 45
    urgency_wait_sec: int = 900
    data_wait_sec: int = 7200
    context_window_min: int = 30
    downtime_notice_sec: int = 600
    ci_timeout_sec: int = 2400
    deploy_timeout_sec: int = 1800


@dataclass
class LlmCfg:
    cli_order: list[str] = field(default_factory=lambda: ["claude", "codex"])
    cooldown_sec: int = 1800
    claude_bin: str = "claude"
    codex_bin: str = "codex"
    models: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "claude": {
                "filter": "haiku",
                "routine": "sonnet",
                "analyst": "opus",
                "review": "opus",
                "mockup": "opus",
                "frontend": "opus",
            },
            # Sol 5.6 — рабочая модель Codex и запасная при недоступности Claude (разбор, хотфикс,
            # интерфейс, макеты); Astra — только ревью и перекрёстная проверка.
            "codex": {
                "filter": "gpt-5.6-sol",
                "routine": "gpt-5.6-sol",
                "analyst": "gpt-5.6-sol",
                "frontend": "gpt-5.6-sol",
                "mockup": "gpt-5.6-sol",
                "review": "gpt-6-astra",
            },
        }
    )
    codex_effort: str = "high"
    analyst_data_hint: str = ""


@dataclass
class OpenAiCfg:
    api_key: str = field(default="", repr=False)  # или переменная окружения OPENAI_API_KEY


@dataclass
class TranscribeCfg:
    model: str = "gpt-4o-mini-transcribe"
    language: str = "ru"
    api_url: str = "https://api.openai.com/v1/audio/transcriptions"
    ffmpeg_bin: str = "ffmpeg"
    max_attempts: int = 3


@dataclass
class HotfixCfg:
    backend_bin: str = ""
    merge_method: str = "merge"
    deployed_sha_cmd: str = ""
    preflight_cmd: str = ""
    public_base_url: str = ""
    allow_foreign_commits: bool = False


@dataclass
class MockupCfg:
    publish_cmd: str = ""
    base_url: str = ""


@dataclass
class Config:
    state_dir: str = "~/.wms-support-agent"
    repo: str = ""
    telegram: TelegramCfg = field(default_factory=TelegramCfg)
    trello: TrelloCfg = field(default_factory=TrelloCfg)
    wms: WmsCfg = field(default_factory=WmsCfg)
    limits: LimitsCfg = field(default_factory=LimitsCfg)
    llm: LlmCfg = field(default_factory=LlmCfg)
    openai: OpenAiCfg = field(default_factory=OpenAiCfg)
    transcribe: TranscribeCfg = field(default_factory=TranscribeCfg)
    hotfix: HotfixCfg = field(default_factory=HotfixCfg)
    mockups: MockupCfg = field(default_factory=MockupCfg)

    @property
    def state_path(self) -> Path:
        return Path(os.path.expanduser(self.state_dir))

    @property
    def db_path(self) -> Path:
        return self.state_path / "state.db"

    def secrets(self) -> list[str]:
        values = [
            self.telegram.bot_token,
            self.trello.api_key,
            self.trello.token,
            self.wms.agent_key,
            self.openai.api_key,
            os.environ.get("OPENAI_API_KEY", ""),
        ]
        return [v for v in values if v and len(v) >= 6]

    def redact(self, text: str) -> str:
        for value in self.secrets():
            text = text.replace(value, "***")
        return text

    def owner_chat_ids(self) -> set[int]:
        return {self.telegram.owner_chat_id} if self.telegram.owner_chat_id else set()


def _build(cls: type[T], data: dict[str, Any]) -> T:
    known = {f.name: f for f in fields(cls)}  # type: ignore[arg-type]
    values: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            continue  # "_comment" and unknown keys are ignored
        values[key] = value
    return cls(**values)


def load_config(path: str | None = None) -> Config:
    raw_path = path or os.environ.get("SUPPORT_AGENT_CONFIG") or DEFAULT_CONFIG_PATH
    data = json.loads(Path(os.path.expanduser(raw_path)).read_text(encoding="utf-8"))
    return config_from_dict(data)


def config_from_dict(data: dict[str, Any]) -> Config:
    cfg = Config(
        state_dir=data.get("state_dir", "~/.wms-support-agent"),
        repo=data.get("repo", ""),
    )
    tg = dict(data.get("telegram", {}))
    chats = {int(k): _build(ChatCfg, v) for k, v in tg.pop("chats", {}).items()}
    cfg.telegram = _build(TelegramCfg, tg)
    cfg.telegram.chats = chats
    cfg.trello = _build(TrelloCfg, data.get("trello", {}))
    cfg.wms = _build(WmsCfg, data.get("wms", {}))
    cfg.limits = _build(LimitsCfg, data.get("limits", {}))
    cfg.llm = _build(LlmCfg, data.get("llm", {}))
    cfg.openai = _build(OpenAiCfg, data.get("openai", {}))
    cfg.transcribe = _build(TranscribeCfg, data.get("transcribe", {}))
    cfg.hotfix = _build(HotfixCfg, data.get("hotfix", {}))
    cfg.mockups = _build(MockupCfg, data.get("mockups", {}))
    return cfg
