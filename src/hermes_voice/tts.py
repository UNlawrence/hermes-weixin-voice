import asyncio
import io
import wave
from pathlib import Path

from .config import settings
from .errors import TTSError

_piper_voice = None
_piper_path: str | None = None


def _load_piper():
    """Lazy-load Piper. Imported here so edge-only users don't pay startup cost."""
    from piper import PiperVoice

    global _piper_voice, _piper_path
    model_path = settings.tts_model_path
    if not model_path:
        raise TTSError(
            "HV_TTS_MODEL_PATH is not set; run `hermes-voice-setup` to install a voice model"
        )
    if not Path(model_path).exists():
        raise TTSError(f"TTS model not found at {model_path!r}; run `hermes-voice-setup`")
    if _piper_voice is None or _piper_path != model_path:
        try:
            _piper_voice = PiperVoice.load(model_path)
            _piper_path = model_path
        except Exception as e:
            raise TTSError(f"failed to load Piper voice {model_path!r}: {e}") from e
    return _piper_voice


def _synthesize_piper(text: str) -> bytes:
    voice = _load_piper()
    buf = io.BytesIO()
    try:
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
    except Exception as e:
        raise TTSError(f"Piper synthesis failed: {e}") from e
    data = buf.getvalue()
    if not data:
        raise TTSError("Piper produced empty audio")
    return data


async def _synthesize_edge(text: str, retries: int = 2) -> bytes:
    import edge_tts

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            communicate = edge_tts.Communicate(
                text, settings.tts_voice, rate=settings.tts_rate, pitch=settings.tts_pitch
            )
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            audio = b"".join(chunks)
            if not audio:
                raise TTSError("edge-tts returned no audio")
            return audio
        except TTSError:
            raise
        except Exception as e:
            last_exc = e
            if attempt < retries:
                await asyncio.sleep(0.5 * (2**attempt))
            continue
    raise TTSError(f"edge-tts failed after {retries + 1} attempts: {last_exc}") from last_exc


async def synthesize(text: str) -> bytes:
    """Synthesize text to audio bytes (WAV for Piper, MP3 for edge-tts).

    Engine is selected by HV_TTS_ENGINE: 'piper' (default, offline) or 'edge'
    (Microsoft cloud, free, needs network). Downstream ffmpeg handles either.
    """
    if not text or not text.strip():
        raise TTSError("empty text")

    engine = (settings.tts_engine or "piper").lower()
    if engine == "piper":
        return await asyncio.to_thread(_synthesize_piper, text)
    if engine == "edge":
        return await _synthesize_edge(text)
    raise TTSError(f"unknown HV_TTS_ENGINE={engine!r}; expected 'piper' or 'edge'")
