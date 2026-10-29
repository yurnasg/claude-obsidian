"""Native cross-platform transport detection and caching."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .json_utils import strict_json_loads
from .paths import resolve_vault_root
from .transaction import (
    MutationLock,
    TransactionError,
    _atomic_vault_write,
    read_vault_regular,
)
from .transport_probe import _stop_probe, probe_selected_vault


def _run_version_probe(binary: str, vault_root: Path) -> tuple[int, str]:
    with tempfile.TemporaryFile() as output:
        process = None
        try:
            process = subprocess.Popen(
                [binary, "version"],
                cwd=str(vault_root),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=dict(os.environ),
                start_new_session=True if os.name != "nt" else False,
            )
            try:
                returncode = process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                _stop_probe(process)
                return 124, "ERR: obsidian version probe timed out after 5 seconds\n"
        except OSError as exc:
            return 126, f"ERR: cannot execute obsidian CLI: {exc.__class__.__name__}\n"
        output.seek(0)
        payload = output.read(8193)
    if len(payload) > 8192:
        payload = payload[:8192] + b"\n[output truncated]\n"
    return returncode, payload.decode("utf-8", errors="replace")


def detect_transport(
    vault_root: Path,
    *,
    peek: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    vault = vault_root.resolve()
    st_val = vault.stat()
    expected_vault_identity = {
        "state": "existing",
        "device": st_val.st_dev,
        "inode": st_val.st_ino,
    }

    # Cache check unless force or peek
    if not force and not peek:
        try:
            cached_raw = read_vault_regular(
                vault, ".vault-meta/transport.json", limit=8 * 1024 * 1024
            )
            if cached_raw is not None:
                cached = strict_json_loads(cached_raw.decode("utf-8"))
                if isinstance(cached, dict) and cached.get("schema_version") == 1:
                    detected_at = cached.get("detected_at")
                    if isinstance(detected_at, str):
                        try:
                            # 7 days freshness
                            parsed = dt.datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
                            age = (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds()
                            if 0 <= age <= 7 * 86400:
                                return cached
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass

    cli_candidate = shutil.which("obsidian")
    legacy_candidate = shutil.which("obsidian-cli")

    cli_binary = ""
    cli_kind = "missing"
    cli_exit_code = -1
    cli_output = ""

    if cli_candidate:
        cli_binary = cli_candidate
        cli_kind = "official"
        cli_exit_code, cli_output = _run_version_probe(cli_binary, vault)
        if len(cli_output) > 8192:
            cli_output = cli_output[:8192] + "\n[output truncated]"
    elif legacy_candidate:
        cli_binary = legacy_candidate
        cli_kind = "legacy"
        cli_exit_code = -1
        cli_output = "Legacy obsidian-cli found; enable and register the official obsidian CLI."

    # Classify
    raw_output = cli_output.strip()
    lowered = raw_output.casefold()

    def classify() -> tuple[str, bool, bool | None, str, str]:
        if cli_kind == "missing":
            return (
                "missing",
                False,
                None,
                "",
                "Obsidian CLI is not on PATH. Enable Command line interface in Obsidian Settings > General.",
            )
        if cli_kind == "legacy":
            return ("unsupported", False, None, "", raw_output)

        app_patterns = (
            "app is not running",
            "app not running",
            "obsidian is not running",
            "no running obsidian",
            "unable to connect",
            "failed to connect",
            "connection refused",
            "could not connect",
            "ipc connection",
        )
        unsupported_patterns = (
            "unknown command",
            "unrecognized command",
            "unsupported command",
            "command not found: version",
            "requires obsidian 1.12",
            "requires the obsidian 1.12",
            "command line interface is disabled",
            "cli is disabled",
            "enable command line interface",
        )
        if any(pattern in lowered for pattern in app_patterns):
            return (
                "app_not_running",
                False,
                False,
                "",
                raw_output or "Obsidian is not running or the CLI could not connect.",
            )
        if any(pattern in lowered for pattern in unsupported_patterns):
            return (
                "unsupported",
                False,
                None,
                "",
                raw_output or "Installed binary does not support 'obsidian version'.",
            )
        if cli_exit_code != 0:
            return (
                "capability_error",
                False,
                None,
                "",
                raw_output or f"'obsidian version' exited with status {cli_exit_code}.",
            )
        if re.search(r"(?im)^\s*(?:error|err|fatal|exception|failed)(?:\s*[:\-]|\s+)", raw_output):
            return ("capability_error", False, None, "", raw_output)
        if not raw_output:
            return (
                "capability_error",
                False,
                None,
                "",
                "'obsidian version' returned no version output.",
            )
        if not re.search(r"\b\d+\.\d+(?:\.\d+)?\b", raw_output):
            return (
                "capability_error",
                False,
                None,
                "",
                f"'obsidian version' returned an unrecognized response: {raw_output}",
            )
        version_string = next((line.strip() for line in raw_output.splitlines() if line.strip()), "")
        identity_verified, identity_diagnostic = probe_selected_vault(cli_binary, str(vault))
        if not identity_verified:
            return ("vault_unverified", False, True, version_string, identity_diagnostic)
        return ("ready", True, True, version_string, "")

    status, usable, app_running, version_string, diagnostic = classify()
    present = cli_kind != "missing"
    preferred = "cli" if usable else "filesystem"
    chain = ["cli", "filesystem"] if usable else ["filesystem"]
    manual_override = False

    # Check existing manual_override
    try:
        existing_raw = read_vault_regular(vault, ".vault-meta/transport.json", limit=8 * 1024 * 1024)
        existing = strict_json_loads(existing_raw.decode("utf-8")) if existing_raw is not None else {}
        if not isinstance(existing, dict):
            existing = {}
    except Exception:
        existing = {}

    if existing.get("manual_override") is True:
        candidate_preferred = existing.get("preferred")
        candidate_chain = existing.get("fallback_chain")
        if (
            isinstance(candidate_preferred, str)
            and candidate_preferred
            and isinstance(candidate_chain, list)
            and candidate_chain
            and all(isinstance(item, str) and item for item in candidate_chain)
        ):
            manual_override = True
            preferred = candidate_preferred if candidate_preferred != "cli" or usable else "filesystem"
            chain = candidate_chain if usable else [item for item in candidate_chain if item != "cli"]
            if not chain:
                chain = ["filesystem"]

    report: dict[str, Any] = {
        "schema_version": 1,
        "detected_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "host": socket.gethostname(),
        "vault_root": str(vault),
        "manual_override": manual_override,
        "preferred": preferred,
        "fallback_chain": chain,
        "available": {
            "cli": {
                "present": present,
                "usable": usable,
                "status": status,
                "binary": cli_binary,
                "probe": "obsidian version",
                "exit_code": None if cli_exit_code < 0 else cli_exit_code,
                "version_string": version_string,
                "diagnostic": diagnostic,
                "obsidian_app_running": app_running,
                "selected_vault_verified": usable,
                "identity_probe": "obsidian vault info=path",
                "capability_probe": "obsidian help read",
            },
            "filesystem": {
                "present": True,
                "vault_root": str(vault),
                "note": "universal fallback; uses the agent host's filesystem tools directly",
            },
            "mcp_obsidian": {
                "present": None,
                "detection": "deferred",
                "note": "MCP server detection is deferred; configure and pin it with manual_override if needed.",
            },
            "mcpvault": {
                "present": None,
                "detection": "deferred",
                "note": "MCP server detection is deferred; configure and pin it with manual_override if needed.",
            },
        },
    }

    if not peek:
        payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
        with MutationLock(vault, expected_vault_identity=expected_vault_identity) as lock:
            root_fd = lock.duplicate_root_fd()
            meta_fd = lock.duplicate_parent_fd()
            try:
                _atomic_vault_write(
                    vault,
                    ".vault-meta/transport.json",
                    payload,
                    mode=0o644,
                    root_fd=root_fd,
                    meta_fd=meta_fd,
                )
            finally:
                if meta_fd is not None and meta_fd >= 0:
                    os.close(meta_fd)
                if root_fd is not None and root_fd >= 0:
                    os.close(root_fd)

    return report


def command_transport_detect(args: argparse.Namespace) -> int:
    vault_str = getattr(args, "vault", None) or getattr(args, "vault_path", None)
    selection = resolve_vault_root(vault_str, start=Path.cwd())
    report = detect_transport(
        selection.root,
        peek=getattr(args, "peek", False),
        force=getattr(args, "force", False),
    )
    if not getattr(args, "quiet", False):
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0
