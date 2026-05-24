import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_hermes_weixin_config() -> dict[str, str]:
    accounts_dir = Path.home() / ".hermes" / "weixin" / "accounts"
    if not accounts_dir.exists():
        return {}

    for account_file in sorted(accounts_dir.glob("*.json")):
        if account_file.name.endswith(".context-tokens.json"):
            continue
        try:
            data = json.loads(account_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue

        base_url = str(data.get("base_url") or "").strip()
        token = str(data.get("token") or "").strip()
        if base_url or token:
            return {
                "ilink_account_id": account_file.stem,
                "ilink_base_url": base_url,
                "ilink_cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
                "ilink_token": token,
            }
    return {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HV_", extra="ignore")

    ilink_account_id: str = ""
    ilink_base_url: str = "http://127.0.0.1:8080"
    ilink_cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    ilink_token: str = ""

    tts_engine: str = "piper"          # "piper" (local) or "edge" (Microsoft cloud, free)
    tts_model_path: str = ""           # Piper .onnx path
    tts_voice: str = "zh-CN-XiaoxiaoNeural"  # edge-tts voice
    tts_rate: str = "+0%"              # edge-tts rate
    tts_pitch: str = "+0Hz"            # edge-tts pitch

    pcm_sample_rate: int = 24000
    max_duration_ms: int = 60_000
    max_text_chars: int = 800

    stt_model: str = "base"
    stt_compute_type: str = "int8"
    stt_device: str = "cpu"

    ffmpeg_bin: str = "ffmpeg"
    work_dir: Path = Path("/tmp/hermes_voice")


settings = Settings()
_hermes_weixin = _load_hermes_weixin_config()
if not settings.ilink_account_id and _hermes_weixin.get("ilink_account_id"):
    settings.ilink_account_id = _hermes_weixin["ilink_account_id"]
if settings.ilink_base_url == "http://127.0.0.1:8080" and _hermes_weixin.get("ilink_base_url"):
    settings.ilink_base_url = _hermes_weixin["ilink_base_url"]
if (
    settings.ilink_cdn_base_url == "https://novac2c.cdn.weixin.qq.com/c2c"
    and _hermes_weixin.get("ilink_cdn_base_url")
):
    settings.ilink_cdn_base_url = _hermes_weixin["ilink_cdn_base_url"]
if not settings.ilink_token and _hermes_weixin.get("ilink_token"):
    settings.ilink_token = _hermes_weixin["ilink_token"]
if not settings.tts_model_path:
    default_model = Path.home() / ".hermes" / "models" / "piper" / "zh_CN-huayan-medium.onnx"
    if default_model.exists():
        settings.tts_model_path = str(default_model)
settings.work_dir.mkdir(parents=True, exist_ok=True)
