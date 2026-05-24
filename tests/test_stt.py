import asyncio
import struct
import wave
from io import BytesIO
from unittest.mock import patch

import pytest

from hermes_voice import STTError, transcribe
from hermes_voice.audio import audio_to_silk


def _silent_wav_bytes(seconds: float = 0.5, rate: int = 16000) -> bytes:
    buf = BytesIO()
    n = int(seconds * rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return buf.getvalue()


def test_transcribe_rejects_empty():
    with pytest.raises(STTError):
        asyncio.run(transcribe(b""))


def test_auto_detects_silk_header():
    fake_silk = b"\x02#!SILK_V3" + b"\x00" * 32
    with patch("hermes_voice.stt._silk_to_wav16k", return_value=_silent_wav_bytes()) as m_silk, \
         patch("hermes_voice.stt._container_to_wav16k") as m_ffmpeg, \
         patch("hermes_voice.stt._transcribe_sync", return_value=""):
        result = asyncio.run(transcribe(fake_silk, source_format="auto"))
    assert m_silk.called
    assert not m_ffmpeg.called
    assert result == ""


def test_transcribe_wav_passthrough():
    wav = _silent_wav_bytes(0.3)
    result = asyncio.run(transcribe(wav, source_format="wav", language="en"))
    assert isinstance(result, str)
    assert len(result) < 50  # silence shouldn't transcribe to anything substantial


@pytest.mark.slow
def test_transcribe_silk_roundtrip():
    from pathlib import Path

    from hermes_voice.config import settings
    from hermes_voice.tts import synthesize

    if not settings.tts_model_path:
        pytest.skip("HV_TTS_MODEL_PATH not set; run `hermes-voice-setup` to install a Piper model")

    model_name = Path(settings.tts_model_path).name
    if model_name.startswith("zh"):
        phrase = "今天天气真好"
        lang = "zh"
        expected = ["今天", "天气", "天氣"]
    else:
        phrase = "hello world"
        lang = "en"
        expected = ["hello", "world"]

    try:
        wav = asyncio.run(synthesize(phrase))
    except Exception as e:
        pytest.skip(f"Piper TTS failed: {e}")

    silk, _dur = audio_to_silk(wav)
    text = asyncio.run(transcribe(silk, source_format="silk", language=lang))
    assert text, "expected non-empty transcript"
    lowered = text.lower()
    assert any(w in lowered for w in expected), f"unexpected transcript: {text!r}"
