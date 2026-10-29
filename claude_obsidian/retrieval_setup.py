"""Vault-scoped bootstrap for optional retrieval cache."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .paths import resolve_vault_root


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"


def setup_retrieve(
    vault_root: Path,
    *,
    check: bool = False,
    apply: bool = False,
    no_llm: bool = False,
    allow_egress: bool = False,
    rebuild: bool = False,
    allow_remote_ollama: bool = False,
) -> int:
    if no_llm and allow_egress:
        sys.stderr.write("ERROR: --no-llm and --allow-egress are mutually exclusive\n")
        return 2

    for helper in ("contextual-prefix.py", "bm25-index.py", "rerank.py", "retrieve.py"):
        if not (SCRIPTS_DIR / helper).is_file():
            sys.stderr.write(f"ERROR: missing product helper: scripts/{helper}\n")
            return 3

    print(f"Vault: {vault_root}")
    print(f"Product helpers: {SCRIPTS_DIR}")

    if check:
        res = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "bm25-index.py"), "--vault", str(vault_root), "stats"],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print("READY: retrieval helpers are installed; vault index is not built yet.")
        else:
            if res.stdout:
                sys.stdout.write(res.stdout)
        return 0

    prefix_args = [sys.executable, str(SCRIPTS_DIR / "contextual-prefix.py"), "--vault", str(vault_root), "--all"]
    if no_llm:
        prefix_args.append("--no-llm")
    if allow_egress:
        prefix_args.append("--allow-egress")
    if rebuild:
        prefix_args.append("--rebuild")

    if not apply:
        prefix_args.append("--peek")
        res = subprocess.run(prefix_args)
        if res.returncode != 0:
            return res.returncode
        print("Dry run only. Repeat with --apply to write derived retrieval state.")
        return 0

    res = subprocess.run(prefix_args)
    if res.returncode != 0:
        return res.returncode

    res = subprocess.run([sys.executable, str(SCRIPTS_DIR / "bm25-index.py"), "--vault", str(vault_root), "build"])
    if res.returncode != 0:
        return res.returncode

    retrieve_args = [sys.executable, str(SCRIPTS_DIR / "retrieve.py"), "--vault", str(vault_root), "wiki", "--top", "1", "--no-rerank"]
    if allow_remote_ollama:
        retrieve_args.append("--allow-remote-ollama")
    subprocess.run(retrieve_args, stdout=subprocess.DEVNULL)
    print("Retrieval state built successfully.")
    return 0


def command_setup_retrieve(args: argparse.Namespace) -> int:
    vault_str = getattr(args, "vault", None)
    selection = resolve_vault_root(vault_str, start=Path.cwd())
    return setup_retrieve(
        selection.root,
        check=getattr(args, "check", False),
        apply=getattr(args, "apply", False),
        no_llm=getattr(args, "no_llm", False),
        allow_egress=getattr(args, "allow_egress", False),
        rebuild=getattr(args, "rebuild", False),
        allow_remote_ollama=getattr(args, "allow_remote_ollama", False),
    )
