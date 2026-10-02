"""R3: расшифровка голоса через OpenAI Audio Transcriptions API (без локального whisper)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from support_agent.config import OpenAiCfg, TranscribeCfg
from support_agent.transcribe import TranscribeError, Transcriber, ffmpeg_to_wav, sniff

KEY = "sk-TEST-SECRET-KEY-VALUE"
OGG = b"OggS" + b"\x00" * 40


def client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_ogg_goes_as_is_with_model_language_and_bearer_key() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": " не открывается поставка "})

    t = Transcriber(TranscribeCfg(), OpenAiCfg(api_key=KEY), http=client(httpx.MockTransport(handle)))
    assert t.transcribe(OGG) == "не открывается поставка"
    req = seen[0]
    body = req.read()
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert b"gpt-4o-mini-transcribe" in body and b'name="language"' in body and b"\r\nru\r\n" in body
    assert b'filename="voice.ogg"' in body and b"audio/ogg" in body  # без конвертации


def test_rejected_format_is_converted_once_and_retried() -> None:
    codes = iter([400, 200])
    names: list[bytes] = []

    def handle(request: httpx.Request) -> httpx.Response:
        code = next(codes)
        names.append(request.read())
        return httpx.Response(code, json={"text": "готово"} if code == 200 else {"error": "format"})

    converted: list[bytes] = []

    def convert(ffmpeg: str, audio: bytes) -> bytes:
        converted.append(audio)
        return b"RIFFwav"

    t = Transcriber(TranscribeCfg(), OpenAiCfg(api_key=KEY), http=client(httpx.MockTransport(handle)),
                    convert=convert)
    assert t.transcribe(b"\x00weird-bytes") == "готово"
    assert len(converted) == 1 and b'filename="voice.wav"' in names[1]


@pytest.mark.parametrize("code, reason", [(401, "openai_auth"), (403, "openai_auth"),
                                           (429, "openai_http_429"), (500, "openai_http_500")])
def test_api_failures_raise_without_leaking_the_key(code: int, reason: str) -> None:
    t = Transcriber(TranscribeCfg(), OpenAiCfg(api_key=KEY), http=client(
        httpx.MockTransport(lambda r: httpx.Response(code, text=f"bad key {KEY}"))))
    with pytest.raises(TranscribeError) as err:
        t.transcribe(OGG)
    assert str(err.value) == reason and KEY not in str(err.value)


def test_transport_error_and_empty_inputs_never_leak_key() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout " + request.headers["authorization"])

    t = Transcriber(TranscribeCfg(), OpenAiCfg(api_key=KEY), http=client(httpx.MockTransport(boom)))
    with pytest.raises(TranscribeError) as err:
        t.transcribe(OGG)
    assert KEY not in str(err.value) and "ReadTimeout" in str(err.value)
    with pytest.raises(TranscribeError, match="empty_audio"):
        t.transcribe(b"")
    empty = Transcriber(TranscribeCfg(), OpenAiCfg(api_key=KEY), http=client(
        httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "  "}))))
    with pytest.raises(TranscribeError, match="empty_transcript"):
        empty.transcribe(OGG)


def test_key_comes_from_config_or_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    no_key = Transcriber(TranscribeCfg(), OpenAiCfg(), http=client(
        httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "x"}))))
    with pytest.raises(TranscribeError, match="openai_key_missing"):
        no_key.transcribe(OGG)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env-value")
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"text": "x"})

    Transcriber(TranscribeCfg(), OpenAiCfg(), http=client(httpx.MockTransport(handle))).transcribe(OGG)
    assert seen == ["Bearer sk-from-env-value"]


def test_sniff_formats() -> None:
    assert sniff(b"OggS....")[0] == "voice.ogg" and sniff(b"RIFF....")[0] == "voice.wav"
    assert sniff(b"ID3....")[0] == "voice.mp3" and sniff(b"\x00\x00\x00\x18ftypisom")[0] == "voice.mp4"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_real_ffmpeg_fallback_converts_opus_to_wav(tmp_path: Path) -> None:
    ogg = tmp_path / "tone.ogg"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "libopus", str(ogg)], check=True)
    wav = ffmpeg_to_wav("ffmpeg", ogg.read_bytes())
    assert wav[:4] == b"RIFF" and len(wav) > 1000
    with pytest.raises(TranscribeError, match="ffmpeg_failed"):
        ffmpeg_to_wav("ffmpeg", b"not audio at all")
