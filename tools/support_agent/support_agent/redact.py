"""Маскировка секретов в журнале и во ВСЕХ исходящих текстах (Telegram, Trello): R37.

Нужна и против прямой утечки, и против того, что модель-аналитик, прочитавшая домашний каталог,
процитирует найденное в своём ответе."""

from __future__ import annotations

import re

from .config import Config

SECRET_PATTERNS = [
    (re.compile(r"bot\d+:[\w-]{10,}"), "bot***"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"), "***telegram-token***"),
    (re.compile(r"(?i)\b(key|token|api_key|access_token|auth|password|secret)=[^&\s\"']+"), r"\1=***"),
    (re.compile(r"(?i)bearer\s+[\w.\-]+"), "Bearer ***"),
    (re.compile(r"\bsk-[\w\-]{12,}"), "sk-***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "gh-***"),
    (re.compile(r"\bgithub_pat_\w{20,}"), "github_pat_***"),
    (re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"), "***jwt***"),
    (re.compile(r"\brt_[\w-]{20,}"), "rt_***"),
    (re.compile(r"\b[a-fA-F0-9]{64}\b"), "***hex64***"),
    (re.compile(r"\b[a-fA-F0-9]{32}\b"), "***hex32***"),
    (re.compile(r"(?i)(\"?(?:access_token|refresh_token|id_token|api_key|OPENAI_API_KEY)\"?\s*[:=]\s*)\"?[\w.\-]{12,}\"?"),
     r"\1***"),
]


def scrub(cfg: Config, text: str) -> str:
    """Известные значения секретов и типовые формы токенов OpenAI, Codex, Telegram, Trello, GitHub."""
    text = cfg.redact(text)
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text
