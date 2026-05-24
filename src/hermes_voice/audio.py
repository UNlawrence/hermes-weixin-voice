import shutil
import subprocess
import tempfile
from pathlib import Path

import pilk

from .config import settings
from .errors import AudioError, VoiceTooLongError


def audio_to_pcm(audio_bytes: bytes, sample_rate: int | None = None) -> bytes:
    """Decode any ffmpeg-readable container (wav/mp3/m4a/opus/...) to signed
    16-bit little-endian mono PCM at the given sample rate. Pipes via stdin/stdout."""
    rate = sample_rate or settings.pcm_sample_rate
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-ar", str(rate),
        "-ac", "1",
        "-f", "s16le",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(
            cmd, input=audio_bytes, capture_output=True, check=True, timeout=60
        )
    except FileNotFoundError as e:
        raise AudioError(f"ffmpeg not found at {settings.ffmpeg_bin!r}") from e
    except subprocess.CalledProcessError as e:
        raise AudioError(f"ffmpeg failed: {e.stderr.decode(errors='replace')}") from e
    if not proc.stdout:
        raise AudioError("ffmpeg produced empty PCM")
    return proc.stdout


def pcm_to_silk(pcm_bytes: bytes, sample_rate: int | None = None) -> tuple[bytes, int]:
    """Encode raw PCM to WeChat-compatible SILK (SILK_V3, tencent variant).
    Returns (silk_bytes, duration_ms). Raises VoiceTooLongError if over the limit."""
    rate = sample_rate or settings.pcm_sample_rate

    tmpdir = Path(tempfile.mkdtemp(prefix="hv_silk_", dir=str(settings.work_dir)))
    pcm_path = tmpdir / "in.pcm"
    silk_path = tmpdir / "out.silk"
    try:
        pcm_path.write_bytes(pcm_bytes)
        try:
            pilk.encode(str(pcm_path), str(silk_path), pcm_rate=rate, tencent=True)
        except Exception as e:
            raise AudioError(f"silk encode failed: {e}") from e

        if not silk_path.exists() or silk_path.stat().st_size == 0:
            raise AudioError("silk encoder produced empty file")

        silk_bytes = silk_path.read_bytes()
        if not silk_bytes.startswith(b"\x02#!SILK_V3"):
            raise AudioError(
                f"silk header mismatch (tencent flag missing): {silk_bytes[:12]!r}"
            )

        duration_ms = pilk.get_duration(str(silk_path))
        if duration_ms <= 0:
            raise AudioError("silk duration is zero")
        if duration_ms > settings.max_duration_ms:
            raise VoiceTooLongError(duration_ms, settings.max_duration_ms)

        return silk_bytes, duration_ms
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def audio_to_silk(audio_bytes: bytes) -> tuple[bytes, int]:
    pcm = audio_to_pcm(audio_bytes)
    return pcm_to_silk(pcm)
