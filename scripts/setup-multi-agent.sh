#!/usr/bin/env bash
# Install Agent Plugins 1.0 packages (or standalone Agent Skills for legacy hosts)
# without overwriting existing host configuration.

set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" != "${BASH_SOURCE[0]}" ] || SCRIPT_DIR="."
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 "$PLUGIN_ROOT/scripts/claude-obsidian.py" setup-multi-agent "$@"
