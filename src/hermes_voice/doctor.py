from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .config import settings
from .ilink import _load_context_token


def _print_status(label: str, ok: bool, detail: str) -> None:
    prefix = "OK" if ok else "FAIL"
    print(f"[{prefix}] {label}: {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hermes-voice-doctor",
        description="Check Hermes Voice local prerequisites and Weixin context.",
    )
    parser.add_argument("to_wxid", nargs="?", help="Optional target wxid to check.")
    args = parser.parse_args()

    ffmpeg = shutil.which(settings.ffmpeg_bin)
    _print_status(
        "ffmpeg",
        ffmpeg is not None,
        ffmpeg or f"`{settings.ffmpeg_bin}` not found in PATH",
    )

    using_default_local = settings.ilink_base_url.rstrip("/") == "http://127.0.0.1:8080"
    _print_status(
        "iLink base URL",
        not using_default_local,
        settings.ilink_base_url,
    )
    _print_status(
        "iLink token",
        bool(settings.ilink_token),
        "present" if settings.ilink_token else "missing",
    )

    hermes_dir = Path.home() / ".hermes"
    _print_status(
        "Hermes home",
        hermes_dir.exists(),
        str(hermes_dir),
    )

    account_dir = hermes_dir / "weixin" / "accounts"
    _print_status(
        "Hermes Weixin account config",
        account_dir.exists() and any(account_dir.glob("*.json")),
        str(account_dir),
    )

    if args.to_wxid:
        has_context = bool(_load_context_token(settings.ilink_account_id, args.to_wxid))
        _print_status(
            "Target context token",
            has_context,
            args.to_wxid,
        )
