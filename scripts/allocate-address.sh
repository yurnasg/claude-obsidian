#!/usr/bin/env bash
# Read-only compatibility diagnostic for the legacy address allocator.
#
# Address reservation now belongs exclusively to a reviewed
# claude-obsidian.transaction.v1 operation with address_requests. This helper
# only prints the next observed counter value and never creates locks, counters,
# directories, or files.
#
# Usage:
#   scripts/allocate-address.sh [--vault PATH] [--peek]
#
# Legacy `allocate` and `--rebuild` modes fail closed with migration guidance.

set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" != "${BASH_SOURCE[0]}" ] || SCRIPT_DIR="."
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec python3 "$PLUGIN_ROOT/scripts/claude-obsidian.py" allocate-address "$@"
