import argparse
import asyncio
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from hermes_voice.audio import pcm_to_silk
from hermes_voice.config import settings
from hermes_voice.errors import AudioError
from hermes_voice.tts import synthesize


def _run_ffmpeg_to_wav(input_path: Path, wav_path: Path) -> None:
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-ar",
        str(settings.pcm_sample_rate),
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=60)
    except FileNotFoundError as e:
        raise AudioError(f"ffmpeg not found at {settings.ffmpeg_bin!r}") from e
    except subprocess.CalledProcessError as e:
        raise AudioError(f"ffmpeg wav normalize failed: {e.stderr.decode(errors='replace')}") from e


def _run_ffmpeg_wav_to_pcm(wav_path: Path) -> bytes:
    cmd = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(settings.pcm_sample_rate),
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True, timeout=60)
    except FileNotFoundError as e:
        raise AudioError(f"ffmpeg not found at {settings.ffmpeg_bin!r}") from e
    except subprocess.CalledProcessError as e:
        raise AudioError(f"ffmpeg pcm export failed: {e.stderr.decode(errors='replace')}") from e
    if not proc.stdout:
        raise AudioError("ffmpeg produced empty PCM")
    return proc.stdout


async def _build_source_file(text: str | None, input_path: str | None, tmpdir: Path) -> Path:
    if bool(text) == bool(input_path):
        raise SystemExit("Provide exactly one of --text or --input")

    if text:
        mp3_bytes = await synthesize(text)
        source_path = tmpdir / "tts.mp3"
        source_path.write_bytes(mp3_bytes)
        return source_path

    path = Path(input_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise SystemExit(f"Input file not found: {path}")
    return path


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a real Tencent-style .silk test file at /tmp/test.silk.",
    )
    parser.add_argument("--text", help="Text to synthesize via OpenAI TTS before SILK encoding.")
    parser.add_argument("--input", help="Existing wav/mp3 file to convert into SILK.")
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="Keep the normalized mono 24kHz wav at /tmp/test.normalized.wav for debugging.",
    )
    args = parser.parse_args()

    tmpdir = Path(tempfile.mkdtemp(prefix="hv_test_silk_", dir=str(settings.work_dir)))
    try:
        source_path = await _build_source_file(args.text, args.input, tmpdir)
        wav_path = tmpdir / "normalized.wav"
        _run_ffmpeg_to_wav(source_path, wav_path)
        pcm = _run_ffmpeg_wav_to_pcm(wav_path)
        silk_bytes, duration_ms = pcm_to_silk(pcm)

        output_path = Path("/tmp/test.silk")
        output_path.write_bytes(silk_bytes)
        kept_wav_path = Path("/tmp/test.normalized.wav")
        if args.keep_wav:
            shutil.copyfile(wav_path, kept_wav_path)

        print(f"output_path={output_path}")
        print(f"file_size={output_path.stat().st_size}")
        print(f"md5={hashlib.md5(silk_bytes).hexdigest()}")
        print(f"first16_hex={silk_bytes[:16].hex()}")
        print(f"duration_ms={duration_ms}")
        if args.keep_wav:
            print(f"normalized_wav_path={kept_wav_path}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(_main())
