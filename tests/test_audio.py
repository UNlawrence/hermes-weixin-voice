import math
import struct

import pytest

from hermes_voice.audio import pcm_to_silk
from hermes_voice.errors import VoiceTooLongError


def _make_sine_pcm(seconds: float, freq: float = 440.0, rate: int = 24000) -> bytes:
    n = int(seconds * rate)
    amp = 16000
    out = bytearray()
    for i in range(n):
        s = int(amp * math.sin(2 * math.pi * freq * i / rate))
        out += struct.pack("<h", s)
    return bytes(out)


def test_pcm_to_silk_produces_tencent_header():
    pcm = _make_sine_pcm(1.0)
    silk, dur = pcm_to_silk(pcm)
    assert silk.startswith(b"\x02#!SILK_V3"), f"bad header: {silk[:12]!r}"
    assert 900 <= dur <= 1100, f"duration off: {dur}ms (expected ~1000ms)"
    assert len(silk) > 200


def test_pcm_to_silk_duration_matches_input_length():
    pcm = _make_sine_pcm(2.5)
    silk, dur = pcm_to_silk(pcm)
    assert 2400 <= dur <= 2600, f"duration off: {dur}ms"


def test_voice_too_long_raises(monkeypatch):
    from hermes_voice import config as cfg
    monkeypatch.setattr(cfg.settings, "max_duration_ms", 500)
    pcm = _make_sine_pcm(1.5)
    with pytest.raises(VoiceTooLongError):
        pcm_to_silk(pcm)
