"""CLI diagnostics must redact token-bearing HTTP diagnostics before calling Telegram."""

from __future__ import annotations

import io
import logging

from support_agent import __main__ as cli
from support_agent.config import config_from_dict


def test_check_bots_redacts_token_url_without_network(monkeypatch, capsys) -> None:
    token = "123456:TEST-TOKEN-NOT-REAL"
    cfg = config_from_dict({"telegram": {"bot_token": token,
                                           "owner_user_id": 42, "owner_chat_id": 99}})
    monkeypatch.setattr(cli, "load_config", lambda _: cfg)
    monkeypatch.setattr("httpx.Client", lambda: object())

    class FakeTelegram:
        def __init__(self, supplied_token: str, _http: object) -> None:
            self.token = supplied_token

        def get_me(self) -> dict[str, object]:
            logging.getLogger("telegram.diagnostic").warning(
                "HTTP request: https://api.telegram.org/bot%s/getMe", self.token)
            return {"username": "fake", "id": 1}

    monkeypatch.setattr("support_agent.telegram.TelegramClient", FakeTelegram)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    before = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        assert cli.check_bots(None) == 0
        assert token not in stream.getvalue()
        assert token not in capsys.readouterr().out
        assert "***" in stream.getvalue()
    finally:
        root.removeHandler(handler)
        root.setLevel(before)
