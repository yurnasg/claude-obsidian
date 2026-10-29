#!/usr/bin/env bash
# Safe, vault-scoped bootstrap for the optional retrieval cache.

set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" != "${BASH_SOURCE[0]}" ] || SCRIPT_DIR="."
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 "$PLUGIN_ROOT/scripts/claude-obsidian.py" setup-retrieve "$@"
