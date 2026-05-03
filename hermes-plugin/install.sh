#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TARGET="$HERMES_HOME/plugins/projecthub"

if [[ ! -d "$HERMES_HOME" ]]; then
  echo "ERROR: Hermes home not found at $HERMES_HOME" >&2
  exit 1
fi

mkdir -p "$HERMES_HOME/plugins"

# Remove existing symlink/dir (only if it points at our SRC_DIR, otherwise abort)
if [[ -L "$TARGET" ]]; then
  if [[ "$(readlink -f "$TARGET")" != "$SRC_DIR" ]]; then
    echo "ERROR: $TARGET is a symlink to $(readlink -f "$TARGET") — refusing to replace." >&2
    exit 1
  fi
  rm "$TARGET"
elif [[ -e "$TARGET" ]]; then
  echo "ERROR: $TARGET already exists and is not a symlink. Move/delete it manually." >&2
  exit 1
fi

ln -s "$SRC_DIR" "$TARGET"
echo "Symlinked $TARGET -> $SRC_DIR"

# Verify httpx is available in Hermes' venv
HERMES_VENV_PY="$HERMES_HOME/hermes-agent/venv/bin/python"
if [[ -x "$HERMES_VENV_PY" ]]; then
  if ! "$HERMES_VENV_PY" -c "import httpx" 2>/dev/null; then
    echo "Installing httpx in Hermes venv..."
    "$HERMES_HOME/hermes-agent/venv/bin/pip" install httpx
  fi
fi

echo
echo "Plugin installed. Activate by setting in ~/.hermes/config.yaml:"
echo "    memory:"
echo "      provider: projecthub"
