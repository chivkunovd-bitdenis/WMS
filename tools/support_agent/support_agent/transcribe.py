"""Расшифровка голоса локально (R3): ffmpeg + whisper.cpp (whisper-cli), без платных ключей."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .config import TranscribeCfg
from .llm import ExecFn, default_exec


class TranscribeError(Exception):
    pass


class Transcriber:
    def __init__(self, cfg: TranscribeCfg, exec_fn: ExecFn = default_exec) -> None:
        self.cfg = cfg
        self.exec = exec_fn

    def transcribe(self, audio: bytes) -> str:
        if not audio:
            raise TranscribeError("empty_audio")
        model = os.path.expanduser(self.cfg.model_path)
        with tempfile.TemporaryDirectory(prefix="wms-voice-") as tmp:
            src, wav = Path(tmp, "in.bin"), Path(tmp, "voice.wav")
            src.write_bytes(audio)
            conv = self.exec(
                [self.cfg.ffmpeg_bin, "-y", "-loglevel", "error", "-i", str(src),
                 "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                tmp, 120, None,
            )
            if conv.rc != 0 or not wav.exists():
                raise TranscribeError("ffmpeg_failed")
            res = self.exec(
                [self.cfg.whisper_bin, "-m", model, "-f", str(wav), "-l", self.cfg.language,
                 "-nt", "-np"],
                tmp, 600, None,
            )
        if res.rc != 0:
            raise TranscribeError("whisper_failed")
        text = " ".join(line.strip() for line in res.out.splitlines() if line.strip())
        if not text:
            raise TranscribeError("empty_transcript")
        return text
