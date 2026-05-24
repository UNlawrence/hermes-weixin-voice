#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_SOURCE="$REPO_ROOT/skills/hermes-voice"
SKILL_TARGET="$HERMES_HOME/skills/hermes-voice"

echo "==> Hermes Voice installer"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv with pip"
  python3 -m pip install --user uv
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "==> Installing ffmpeg with Homebrew"
    brew install ffmpeg
  else
    echo "ffmpeg is required. Install Homebrew or add ffmpeg to PATH, then rerun."
    exit 1
  fi
fi

mkdir -p "$HERMES_HOME/skills"

echo "==> Installing hermes-voice CLI"
UV_CACHE_DIR="$REPO_ROOT/.uv-cache" uv tool install --force "$REPO_ROOT"

echo "==> Installing Hermes skill"
rm -rf "$SKILL_TARGET"
cp -R "$SKILL_SOURCE" "$SKILL_TARGET"

echo "==> Verifying installation"
export PATH="$HOME/.local/bin:$PATH"
hermes-voice-doctor || true

if [ -t 0 ]; then
  echo "==> Running interactive TTS model setup"
  (cd "$REPO_ROOT" && UV_CACHE_DIR="$REPO_ROOT/.uv-cache" uv run hermes-voice-setup) || true
else
  echo "Skipping interactive setup - run 'uv run hermes-voice-setup' to configure TTS."
fi

echo ""
echo "Install complete."
echo "Use in Hermes with: /hermes-voice wxid_xxx 你好，这是一条测试语音"
echo "Or in terminal with: hermes-voice wxid_xxx \"你好，这是一条测试语音\""
