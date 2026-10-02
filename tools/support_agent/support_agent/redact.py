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
    # Токены с пробелом или переводом строки внутри (перенос в ответе модели): префикс и до трёх
    # последующих кусков.
    (re.compile(r"\bsk-[\w\-]*(?:\s+[\w\-]{6,}){0,3}"), "sk-***"),
    (re.compile(r"\bgithub_pat_\w*(?:\s+\w{6,}){0,3}"), "github_pat_***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "gh-***"),
    (re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"), "***jwt***"),
    (re.compile(r"\brt_[\w-]{20,}"), "rt_***"),
    (re.compile(r"\b[a-fA-F0-9]{64}\b"), "***hex64***"),
    (re.compile(r"\b[a-fA-F0-9]{32}\b"), "***hex32***"),
    # JSON и key: value / key = value: значение целиком (в кавычках — с пробелами)
    (re.compile(r"(?i)(\"?(?:password|passwd|secret|token|api[_-]?key|authorization|access_token|"
                r"refresh_token|id_token|openai_api_key)\"?\s*[:=]\s*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s,;&\"']+)"),
     r"\1***"),
]


def scrub(cfg: Config, text: str) -> str:
    """Известные значения секретов и типовые формы токенов OpenAI, Codex, Telegram, Trello, GitHub."""
    text = cfg.redact(text)
    for pattern, repl in SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text
