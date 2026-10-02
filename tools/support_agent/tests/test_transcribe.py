"""R3: расшифровка голоса локально (ffmpeg + whisper.cpp)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from support_agent.config import TranscribeCfg
from support_agent.llm import ExecResult
from support_agent.transcribe import TranscribeError, Transcriber


def test_commands_and_text_assembly() -> None:
    calls: list[list[str]] = []

    def fake(argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        calls.append(argv)
        if argv[0] == "ffmpeg":
            Path(argv[-1]).write_bytes(b"wav")
            return ExecResult(0, "", "")
        return ExecResult(0, "\n  не открывается \n поставка  \n", "")

    cfg = TranscribeCfg(model_path="/m/ggml-small.bin")
    text = Transcriber(cfg, exec_fn=fake).transcribe(b"ogg-bytes")
    assert text == "не открывается поставка"
    assert calls[0][0] == "ffmpeg" and "16000" in calls[0]
    assert calls[1][0] == "whisper-cli" and "-m" in calls[1] and "/m/ggml-small.bin" in calls[1]
    assert calls[1][calls[1].index("-l") + 1] == "ru"


@pytest.mark.parametrize("stage", ["ffmpeg", "whisper", "empty", "no_audio"])
def test_failures_raise_instead_of_returning_garbage(stage: str) -> None:
    def fake(argv: list[str], cwd: str | None, timeout: int, stdin: str | None) -> ExecResult:
        if argv[0] == "ffmpeg":
            if stage == "ffmpeg":
                return ExecResult(1, "", "bad")
            Path(argv[-1]).write_bytes(b"wav")
            return ExecResult(0, "", "")
        return ExecResult(1, "", "") if stage == "whisper" else ExecResult(0, "  \n", "")

    with pytest.raises(TranscribeError):
        Transcriber(TranscribeCfg(), exec_fn=fake).transcribe(b"" if stage == "no_audio" else b"x")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_real_ffmpeg_converts_and_stub_whisper_is_called(tmp_path: Path) -> None:
    """Настоящий ffmpeg превращает ogg/opus в wav 16 кГц; whisper заменён скриптом-заглушкой."""
    ogg = tmp_path / "tone.ogg"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "libopus", str(ogg)],
        check=True,
    )
    stub = tmp_path / "whisper-stub"
    stub.write_text(
        "#!/bin/bash\n"
        'f=""; while [ $# -gt 0 ]; do [ "$1" = "-f" ] && f="$2"; shift; done\n'
        '[ -s "$f" ] && echo "тест расшифровки"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    cfg = TranscribeCfg(whisper_bin=str(stub))
    assert Transcriber(cfg).transcribe(ogg.read_bytes()) == "тест расшифровки"
