"""Tests for hermes_voice.setup_cli."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import importlib.util
import sys

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "hermes_voice" / "setup_cli.py"
_spec = importlib.util.spec_from_file_location("hermes_voice_setup_cli_under_test", _MODULE_PATH)
setup_cli = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = setup_cli
_spec.loader.exec_module(setup_cli)


def test_voice_url_builder() -> None:
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    cases = {
        "zh_CN-huayan-medium":
            base + "zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx",
        "zh_CN-huayan-x_low":
            base + "zh/zh_CN/huayan/x_low/zh_CN-huayan-x_low.onnx",
        "en_US-amy-medium":
            base + "en/en_US/amy/medium/en_US-amy-medium.onnx",
        "en_US-lessac-medium":
            base + "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "en_GB-alan-medium":
            base + "en/en_GB/alan/medium/en_GB-alan-medium.onnx",
    }
    for key, expected in cases.items():
        assert setup_cli.build_voice_url(key) == expected
        assert setup_cli.build_config_url(key) == expected + ".json"


def test_env_file_update_preserves_other_lines(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "FOO=bar\n"
        "HV_TTS_MODEL_PATH=/old/path.onnx\n"
        "BAZ=qux\n"
    )
    new_model = tmp_path / "new.onnx"
    setup_cli.update_env_file(env, {"HV_TTS_MODEL_PATH": str(new_model)})
    contents = env.read_text().splitlines()
    assert "FOO=bar" in contents
    assert "BAZ=qux" in contents
    assert f"HV_TTS_MODEL_PATH={new_model}" in contents
    assert "HV_TTS_MODEL_PATH=/old/path.onnx" not in contents
    assert sum(1 for L in contents if L.startswith("HV_TTS_MODEL_PATH=")) == 1


def test_env_file_creates_when_missing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    assert not env.exists()
    model = tmp_path / "voice.onnx"
    setup_cli.update_env_file(env, {"HV_TTS_MODEL_PATH": str(model)})
    assert env.exists()
    assert env.read_text().strip() == f"HV_TTS_MODEL_PATH={model}"


def test_env_file_writes_multiple_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nHV_TTS_ENGINE=piper\n")
    setup_cli.update_env_file(env, {
        "HV_TTS_ENGINE": "edge",
        "HV_TTS_MODEL_PATH": "/p/m.onnx",
    })
    contents = env.read_text().splitlines()
    assert "FOO=bar" in contents
    assert "HV_TTS_ENGINE=edge" in contents
    assert "HV_TTS_MODEL_PATH=/p/m.onnx" in contents
    assert sum(1 for L in contents if L.startswith("HV_TTS_ENGINE=")) == 1


def test_engine_edge_skips_download(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    calls: list[tuple] = []

    def fake_retrieve(url, filename, reporthook=None):
        calls.append((url, filename))
        return (filename, None)

    with patch.object(setup_cli.urllib.request, "urlretrieve",
                      side_effect=fake_retrieve):
        rc = setup_cli.main([
            "--engine", "edge",
            "--skip-verify",
            "--env-file", str(env_path),
        ])

    assert rc == 0
    assert len(calls) == 0  # no download
    contents = env_path.read_text()
    assert "HV_TTS_ENGINE=edge" in contents


def test_non_interactive_flag_skips_prompt(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    env_path = tmp_path / ".env"
    calls: list[tuple] = []

    def fake_retrieve(url: str, filename: str, reporthook=None):
        # Simulate creating the file
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_bytes(b"x" * 16)
        calls.append((url, filename))
        return (filename, None)

    with patch.object(setup_cli.urllib.request, "urlretrieve",
                      side_effect=fake_retrieve):
        rc = setup_cli.main([
            "--non-interactive",
            "--voice", "zh_CN-huayan-medium",
            "--skip-verify",
            "--env-file", str(env_path),
            "--models-dir", str(models_dir),
        ])

    assert rc == 0
    assert len(calls) == 2
    urls = [c[0] for c in calls]
    assert urls[0] == setup_cli.build_voice_url("zh_CN-huayan-medium")
    assert urls[1] == setup_cli.build_config_url("zh_CN-huayan-medium")
    # env updated
    contents = env_path.read_text()
    assert "HV_TTS_ENGINE=piper" in contents
    assert "HV_TTS_MODEL_PATH=" in contents
    assert str(models_dir / "zh_CN-huayan-medium.onnx") in contents
