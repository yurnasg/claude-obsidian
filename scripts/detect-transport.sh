#!/usr/bin/env bash
# Detect the supported Obsidian CLI and write a normalized transport snapshot.
#
# Official Obsidian CLI syntax is `obsidian version`. The detector never treats
# binary presence alone, a legacy --version response, or exit status zero alone
# as proof of capability.
#
# Usage:
#   bash scripts/detect-transport.sh [--vault PATH] [--force] [--quiet]
#   bash scripts/detect-transport.sh --peek [--vault PATH]
#   bash scripts/detect-transport.sh [PATH]          # legacy positional vault
#
# --peek is strictly read-only with respect to the vault. It neither creates
# .vault-meta nor refreshes transport.json.

set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" != "${BASH_SOURCE[0]}" ] || SCRIPT_DIR="."
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 "$PLUGIN_ROOT/scripts/claude-obsidian.py" detect-transport "$@"
