#!/bin/zsh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
"$REPO_ROOT/scripts/install.sh"

echo ""
read -r "?Press Enter to close this window..."
