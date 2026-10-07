"""The ordinary moderator can observe real compaction without a dispatcher."""
import json
from pathlib import Path

import pytest

from support_agent.native_bridge import NativeBridge

from .conftest import make_config

THREAD = "01a116a6-e508-7a31-a056-1a68f5b5880c"


def usage(tokens):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "last_token_usage": {"input_tokens": tokens, "output_tokens": 100},
        "model_context_window": 354350}}}


def test_compaction_signal_preserves_first_after_count_and_current_context(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    directory = tmp_path / ".codex/sessions/2026/10/07"
    directory.mkdir(parents=True)
    records = [usage(170000), {"type": "compacted", "timestamp": "2026-10-07T16:36:27Z",
                              "payload": {"message": "short summary"}}, usage(47000), usage(48000)]
    (directory / f"rollout-{THREAD}.jsonl").write_text(
        "not-json\n[]\n" + "\n".join(json.dumps(record) for record in records))
    result = NativeBridge(make_config(tmp_path)).context(THREAD)
    assert result["context_tokens"] == 48100
    assert result["compaction_count"] == 1
    assert result["last_compaction"] == {"timestamp": "2026-10-07T16:36:27Z",
                                          "before_tokens": 170100, "after_tokens": 47100}


def test_context_without_saved_counter_is_unknown_not_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = NativeBridge(make_config(tmp_path)).context(THREAD)
    assert result["context_tokens"] is None
    assert result["last_compaction"] is None
    assert result["compaction_count"] == 0


def test_context_does_not_accept_a_glob_as_thread_identity(tmp_path):
    with pytest.raises(ValueError):
        NativeBridge(make_config(tmp_path)).context("*")
