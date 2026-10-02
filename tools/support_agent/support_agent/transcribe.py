"""Расшифровка голоса через OpenAI Audio Transcriptions API по ключу владельца (R3).

Telegram-голос — OGG/Opus, API принимает ogg как есть. Если формат всё же отвергнут (400),
один раз конвертируем ffmpeg в wav и повторяем. Ключ не попадает в тексты ошибок и логи.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx

from .config import OpenAiCfg, TranscribeCfg

URL = "https://api.openai.com/v1/audio/transcriptions"


class TranscribeError(Exception):
    pass


def sniff(audio: bytes) -> tuple[str, str]:
    """(имя файла, mime) по началу данных; Telegram чаще всего отдаёт OggS (voice)."""
    if audio[:4] == b"OggS":
        return "voice.ogg", "audio/ogg"
    if audio[:4] == b"RIFF":
        return "voice.wav", "audio/wav"
    if audio[:3] == b"ID3" or audio[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "voice.mp3", "audio/mpeg"
    if audio[4:8] == b"ftyp":
        return "voice.mp4", "audio/mp4"
    if audio[:4] == b"\x1a\x45\xdf\xa3":
        return "voice.webm", "audio/webm"
    return "voice.ogg", "audio/ogg"


def api_key(openai: OpenAiCfg) -> str:
    return openai.api_key or os.environ.get("OPENAI_API_KEY", "")


def ffmpeg_to_wav(ffmpeg_bin: str, audio: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="wms-voice-") as tmp:
        src, wav = Path(tmp, "in.bin"), Path(tmp, "voice.wav")
        src.write_bytes(audio)
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-y", "-loglevel", "error", "-i", str(src), "-ar", "16000", "-ac", "1",
                 "-c:a", "pcm_s16le", str(wav)],
                capture_output=True, timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise TranscribeError("ffmpeg_failed") from None
        if res.returncode != 0 or not wav.exists():
            raise TranscribeError("ffmpeg_failed")
        return wav.read_bytes()


class Transcriber:
    def __init__(
        self,
        cfg: TranscribeCfg,
        openai: OpenAiCfg,
        http: httpx.Client | None = None,
        convert: Callable[[str, bytes], bytes] = ffmpeg_to_wav,
    ) -> None:
        self.cfg, self.openai = cfg, openai
        self.http = http or httpx.Client()
        self.convert = convert

    def _post(self, name: str, mime: str, audio: bytes) -> httpx.Response:
        key = api_key(self.openai)
        if not key:
            raise TranscribeError("openai_key_missing")
        try:
            return self.http.post(
                self.cfg.api_url,
                headers={"Authorization": f"Bearer {key}"},
                data={"model": self.cfg.model, "language": self.cfg.language,
                      "response_format": "json"},
                files={"file": (name, audio, mime)},
                timeout=120,
            )
        except httpx.HTTPError as exc:  # тексты httpx не пробрасываем
            raise TranscribeError(f"openai_transport_{type(exc).__name__}") from None

    def transcribe(self, audio: bytes) -> str:
        if not audio:
            raise TranscribeError("empty_audio")
        name, mime = sniff(audio)
        res = self._post(name, mime, audio)
        if res.status_code == 400:  # формат не принят: один раз через ffmpeg -> wav
            res = self._post("voice.wav", "audio/wav", self.convert(self.cfg.ffmpeg_bin, audio))
        if res.status_code in (401, 403):
            raise TranscribeError("openai_auth")
        if res.status_code != 200:
            raise TranscribeError(f"openai_http_{res.status_code}")
        try:
            text = str(res.json().get("text", "")).strip()
        except ValueError:
            raise TranscribeError("openai_invalid_response") from None
        if not text:
            raise TranscribeError("empty_transcript")
        return text
