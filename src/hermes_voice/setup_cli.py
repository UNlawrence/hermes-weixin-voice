"""Interactive setup CLI for Hermes Voice.

Downloads a Piper TTS voice model and writes its path into the user's .env.
Uses stdlib only so it can run before project deps are installed.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Optional

HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
MODELS_DIR = Path.home() / ".hermes" / "models" / "piper"

# (key, description)
VOICES: list[tuple[str, str]] = [
    ("zh_CN-huayan-medium", "Chinese (Mandarin) - medium quality, ~63 MB  [recommended]"),
    ("zh_CN-huayan-x_low", "Chinese (Mandarin) - smallest, ~28 MB"),
    ("en_US-amy-medium", "English (US) - female, medium quality, ~63 MB"),
    ("en_US-lessac-medium", "English (US) - male, medium quality, ~63 MB"),
    ("en_GB-alan-medium", "English (UK) - male, medium quality, ~63 MB"),
]
DEFAULT_VOICE = VOICES[0][0]
VOICE_KEYS = [v[0] for v in VOICES]


def build_voice_url(voice_key: str) -> str:
    """Build the .onnx URL for a voice key like 'zh_CN-huayan-medium'."""
    parts = voice_key.split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid voice key: {voice_key!r}")
    lang_country, voice, quality = parts
    lang = lang_country.split("_")[0]
    filename = f"{lang_country}-{voice}-{quality}.onnx"
    return f"{HF_BASE}{lang}/{lang_country}/{voice}/{quality}/{filename}"


def build_config_url(voice_key: str) -> str:
    return build_voice_url(voice_key) + ".json"


def _progress_reporter(label: str) -> Callable[[int, int, int], None]:
    state = {"last_mb": -1}

    def hook(block_num: int, block_size: int, total_size: int) -> None:
        downloaded = block_num * block_size
        mb = downloaded // (1024 * 1024)
        if mb != state["last_mb"]:
            state["last_mb"] = mb
            if total_size > 0:
                pct = min(100, int(downloaded * 100 / total_size))
                print(f"  {label}: {mb} MB ({pct}%)", flush=True)
            else:
                print(f"  {label}: {mb} MB", flush=True)

    return hook


def download_voice(voice_key: str, dest_dir: Path,
                   retrieve: Optional[Callable[..., tuple]] = None) -> Path:
    """Download <voice>.onnx and <voice>.onnx.json. Returns path to .onnx."""
    if retrieve is None:
        retrieve = urllib.request.urlretrieve
    dest_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = dest_dir / f"{voice_key}.onnx"
    json_path = dest_dir / f"{voice_key}.onnx.json"

    if onnx_path.exists() and onnx_path.stat().st_size > 0 \
            and json_path.exists() and json_path.stat().st_size > 0:
        print(f"  model already present at {onnx_path}")
        return onnx_path

    onnx_url = build_voice_url(voice_key)
    json_url = build_config_url(voice_key)

    print(f"  downloading {onnx_url}")
    retrieve(onnx_url, str(onnx_path), _progress_reporter("model"))
    print(f"  downloading {json_url}")
    retrieve(json_url, str(json_path), _progress_reporter("config"))
    return onnx_path


def update_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """Insert/replace the given key=value pairs, preserving other lines."""
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    else:
        lines = []

    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        replaced = False
        for key in list(remaining):
            if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
                out.append(f"{key}={remaining.pop(key)}")
                replaced = True
                break
        if not replaced:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")

    env_path.write_text("\n".join(out) + "\n")


def verify_install(model_path: Path) -> bool:
    """Print verification checks. Returns True if all passed."""
    ok = True

    try:
        import piper  # noqa: F401
        print("  [ok] piper-tts installed")
    except Exception as exc:
        print(f"  [!!] piper-tts not importable: {exc}")
        ok = False

    if model_path.exists() and model_path.stat().st_size > 0:
        print(f"  [ok] model file present ({model_path.stat().st_size} bytes)")
    else:
        print(f"  [!!] model file missing or empty: {model_path}")
        ok = False

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        print(f"  [ok] ffmpeg found at {ffmpeg}")
    else:
        print("  [!!] ffmpeg not found in PATH")
        ok = False

    return ok


EDGE_SENTINEL = "__edge__"


def _prompt_choice() -> Optional[str]:
    """Returns voice key, EDGE_SENTINEL for edge-tts, or None if user picked Skip."""
    print("[1/3] Pick a TTS engine:")
    for i, (key, desc) in enumerate(VOICES, start=1):
        print(f"  {i}) {key:<22} {desc}")
    edge_idx = len(VOICES) + 1
    skip_idx = len(VOICES) + 2
    print(f"  {edge_idx}) edge-tts             Microsoft cloud (free, no key, needs network)")
    print(f"  {skip_idx}) Skip (configure manually later)")
    print()
    while True:
        raw = input("Choice [1]: ").strip()
        if raw == "":
            return DEFAULT_VOICE
        if not raw.isdigit():
            print("Please enter a number.")
            continue
        n = int(raw)
        if 1 <= n <= len(VOICES):
            return VOICES[n - 1][0]
        if n == edge_idx:
            return EDGE_SENTINEL
        if n == skip_idx:
            return None
        print("Out of range.")


def _print_list() -> None:
    for key, desc in VOICES:
        print(f"{key}\t{desc}")


def _find_env_path() -> Path:
    return Path.cwd() / ".env"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hermes-voice-setup",
        description="Interactive setup for Hermes Voice (downloads a Piper TTS model).",
    )
    parser.add_argument("--non-interactive", action="store_true",
                        help="Do not prompt; requires --voice or --engine edge.")
    parser.add_argument("--voice", choices=VOICE_KEYS,
                        help="Piper voice key to install (used with --non-interactive).")
    parser.add_argument("--engine", choices=["piper", "edge"], default=None,
                        help="Force a TTS engine. 'edge' skips Piper model download.")
    parser.add_argument("--list", action="store_true",
                        help="Print available voices and exit.")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Skip the final verification block.")
    parser.add_argument("--env-file", type=Path, default=None,
                        help="Path to .env file (default: ./.env).")
    parser.add_argument("--models-dir", type=Path, default=None,
                        help="Override models directory (default: ~/.hermes/models/piper).")
    args = parser.parse_args(argv)

    if args.list:
        _print_list()
        return 0

    print("Hermes Voice setup")
    print("==================")
    print()

    if args.engine == "edge":
        voice_key = EDGE_SENTINEL
        print("[1/3] Selected: edge-tts (Microsoft cloud, free)")
    elif args.non_interactive:
        if not args.voice:
            print("--non-interactive requires --voice or --engine edge", file=sys.stderr)
            return 2
        voice_key = args.voice
        print(f"[1/3] Non-interactive: selected {voice_key}")
    else:
        voice_key = _prompt_choice()
        if voice_key is None:
            print("Skipped - set HV_TTS_ENGINE / HV_TTS_MODEL_PATH manually before using TTS.")
            return 0

    env_path = args.env_file or _find_env_path()

    if voice_key == EDGE_SENTINEL:
        print(f"\n[2/3] Writing config to {env_path}...")
        update_env_file(env_path, {"HV_TTS_ENGINE": "edge"})
        print("  HV_TTS_ENGINE=edge")
        if not args.skip_verify:
            print("\n[3/3] Verifying installation...")
            try:
                import edge_tts  # noqa: F401
                print("  [ok] edge-tts installed")
            except Exception as exc:
                print(f"  [!!] edge-tts not importable: {exc}")
            ffmpeg = shutil.which("ffmpeg")
            print(f"  [{'ok' if ffmpeg else '!!'}] ffmpeg {'found at ' + ffmpeg if ffmpeg else 'not found in PATH'}")
        print("\nSetup complete. Try:")
        print('  uv run hermes-voice wxid_xxx "你好,这是 Hermes"')
        return 0

    models_dir = args.models_dir or MODELS_DIR
    print(f"\nDownloading to {models_dir} ...")
    try:
        model_path = download_voice(voice_key, models_dir)
    except Exception as exc:
        print(f"  [!!] download failed: {exc}", file=sys.stderr)
        return 1

    print(f"\n[2/3] Writing config to {env_path}...")
    update_env_file(env_path, {
        "HV_TTS_ENGINE": "piper",
        "HV_TTS_MODEL_PATH": str(model_path),
    })
    print(f"  HV_TTS_ENGINE=piper")
    print(f"  HV_TTS_MODEL_PATH={model_path}")

    if not args.skip_verify:
        print("\n[3/3] Verifying installation...")
        verify_install(model_path)

    print("\nSetup complete. Try:")
    print('  uv run hermes-voice wxid_xxx "你好,这是 Hermes"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
