import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import pilk
from faster_whisper import WhisperModel

from .config import settings
from .errors import STTError

# Tencent SILK files start with \x02 prefix before the standard SILK_V3 magic.
_SILK_HEADER = b"\x02#!SILK_V3"
_STT_SAMPLE_RATE = 16000  # faster-whisper expects 16kHz mono audio.

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        try:
            _model = WhisperModel(
                settings.stt_model,
                device=settings.stt_device,
                compute_type=settings.stt_compute_type,
            )
        except Exception as e:
            raise STTError(f"failed to load whisper model {settings.stt_model!r}: {e}") from e
    return _model


def _silk_to_wav16k(silk_bytes: bytes) -> bytes:
    tmpdir = Path(tempfile.mkdtemp(prefix="hv_stt_silk_", dir=str(settings.work_dir)))
    silk_path = tmpdir / "in.silk"
    pcm_path = tmpdir / "out.pcm"
    try:
        silk_path.write_bytes(silk_bytes)
        try:
            pilk.decode(str(silk_path), str(pcm_path), pcm_rate=_STT_SAMPLE_RATE)
        except Exception as e:
            raise STTError(f"silk decode failed: {e}") from e
        if not pcm_path.exists() or pcm_path.stat().st_size == 0:
            raise STTError("silk decoder produced empty PCM")
        pcm_bytes = pcm_path.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-f", "s16le",
        "-ar", str(_STT_SAMPLE_RATE),
        "-ac", "1",
        "-i", "pipe:0",
        "-ar", str(_STT_SAMPLE_RATE),
        "-ac", "1",
        "-f", "wav",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=pcm_bytes, capture_output=True, check=True, timeout=60)
    except FileNotFoundError as e:
        raise STTError(f"ffmpeg not found at {settings.ffmpeg_bin!r}") from e
    except subprocess.CalledProcessError as e:
        raise STTError(f"ffmpeg failed: {e.stderr.decode(errors='replace')}") from e
    if not proc.stdout:
        raise STTError("ffmpeg produced empty WAV")
    return proc.stdout


def _container_to_wav16k(audio_bytes: bytes) -> bytes:
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-ar", str(_STT_SAMPLE_RATE),
        "-ac", "1",
        "-f", "wav",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=audio_bytes, capture_output=True, check=True, timeout=60)
    except FileNotFoundError as e:
        raise STTError(f"ffmpeg not found at {settings.ffmpeg_bin!r}") from e
    except subprocess.CalledProcessError as e:
        raise STTError(f"ffmpeg failed: {e.stderr.decode(errors='replace')}") from e
    if not proc.stdout:
        raise STTError("ffmpeg produced empty WAV")
    return proc.stdout


def _transcribe_sync(wav_path: str, language: str | None) -> str:
    model = _get_model()
    try:
        segments, _info = model.transcribe(wav_path, language=language, beam_size=5)
        text = "".join(seg.text for seg in segments)
    except Exception as e:
        raise STTError(f"whisper transcribe failed: {e}") from e
    return text.strip()


async def transcribe(
    audio: bytes,
    *,
    source_format: Literal["silk", "wav", "mp3", "auto"] = "auto",
    language: str | None = None,
) -> str:
    """Transcribe SILK/WAV/MP3 audio bytes to text via faster-whisper."""
    if not audio:
        raise STTError("empty audio")

    fmt = source_format
    if fmt == "auto":
        fmt = "silk" if audio.startswith(_SILK_HEADER) else "wav"

    if fmt == "silk":
        wav_bytes = _silk_to_wav16k(audio)
    else:
        wav_bytes = _container_to_wav16k(audio)

    tmpdir = Path(tempfile.mkdtemp(prefix="hv_stt_wav_", dir=str(settings.work_dir)))
    wav_path = tmpdir / "in.wav"
    try:
        wav_path.write_bytes(wav_bytes)
        return await asyncio.to_thread(_transcribe_sync, str(wav_path), language)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def stt_main() -> None:
    import argparse
    import asyncio as _asyncio

    parser = argparse.ArgumentParser(
        prog="hermes-voice-stt",
        description="Transcribe a SILK/WAV/MP3 audio file via faster-whisper.",
    )
    parser.add_argument("audio_path", help="Path to the audio file.")
    parser.add_argument(
        "--language",
        default=None,
        help="Language hint (e.g. zh, en). Defaults to auto-detect.",
    )
    args = parser.parse_args()

    audio_bytes = Path(args.audio_path).read_bytes()
    text = _asyncio.run(transcribe(audio_bytes, language=args.language))
    print(text)
