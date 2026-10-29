"""Native multi-host Agent Plugins 1.0 & standalone Agent Skills installer."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PLUGIN_NAME = "claude-obsidian"
REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


def _inspect_link(
    host: str,
    source: Path,
    destination: Path,
    confinement_root: Path | None,
    mode: str,
) -> tuple[int, str]:
    """Inspect or create one plugin/skill link.
    Returns (status_code, output_line).
    status_code: 0=ok, 1=planned (for check mode), 2=conflict/error.
    """
    parent = destination.parent

    if destination.is_symlink():
        try:
            target = destination.resolve()
            # Also check os.readlink for exact equivalence
            link_target = Path(os.readlink(destination))
            if not link_target.is_absolute():
                link_target = (parent / link_target).resolve()
        except OSError:
            target = Path()
            link_target = Path()
        if target == source.resolve() or link_target == source.resolve():
            return 0, f"READY {host} {destination}"
        try:
            points_to = os.readlink(destination)
        except OSError:
            points_to = str(target)
        sys.stderr.write(f"CONFLICT {host} {destination} points to {points_to}\n")
        return 2, ""

    if destination.exists():
        sys.stderr.write(f"CONFLICT {host} {destination} already exists\n")
        return 2, ""

    if confinement_root is not None:
        cursor = confinement_root
        try:
            rel = parent.relative_to(confinement_root)
        except ValueError:
            sys.stderr.write(f"CONFLICT {host} parent escapes workspace: {parent}\n")
            return 2, ""

        for part in rel.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                sys.stderr.write(f"CONFLICT {host} parent is a symlink: {cursor}\n")
                return 2, ""
            if cursor.exists():
                if not cursor.is_dir():
                    sys.stderr.write(f"CONFLICT {host} parent is not a directory: {cursor}\n")
                    return 2, ""
            elif mode == "apply":
                try:
                    cursor.mkdir()
                except OSError:
                    sys.stderr.write(f"CONFLICT {host} cannot create confined parent: {cursor}\n")
                    return 2, ""
            if cursor.exists():
                if cursor.is_symlink() or not cursor.is_dir():
                    sys.stderr.write(f"CONFLICT {host} parent changed during install: {cursor}\n")
                    return 2, ""

    if mode == "apply":
        if confinement_root is None:
            parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.symlink_to(source, target_is_directory=True)
        except OSError as exc:
            # On Windows without developer mode/admin rights
            sys.stderr.write(f"ERROR {host} cannot create symlink {destination} -> {source}: {exc}\n")
            return 2, ""
        return 0, f"CREATED {host} {destination}"
    else:
        status = 1 if mode == "check" else 0
        return status, f"PLANNED {host} {destination}"


def setup_multi_agent(
    *,
    mode: str = "dry-run",
    hosts: list[str] | None = None,
    workspace: Path | None = None,
    home: Path | None = None,
) -> int:
    if not SKILLS_DIR.is_dir():
        sys.stderr.write(f"ERROR: missing skills directory: {SKILLS_DIR}\n")
        return 2

    if home is None:
        home_env = os.environ.get("HOME") or os.environ.get("USERPROFILE")
        home = Path(home_env) if home_env else Path.home()

    if not hosts:
        hosts = ["copilot", "antigravity", "antigravity-cli", "codex"]

    expanded: list[str] = []
    for h in hosts:
        if h == "all":
            expanded.extend(["copilot", "antigravity", "antigravity-cli", "codex", "cursor", "opencode"])
        elif h == "gemini":
            expanded.append("antigravity-cli")
        elif h in {"copilot", "antigravity", "antigravity-cli", "codex", "cursor", "opencode", "zcode", "windsurf"}:
            expanded.append(h)
        else:
            sys.stderr.write(f"ERROR: unsupported host: {h}\n")
            return 2

    overall_status = 0
    seen: set[str] = set()

    for host in expanded:
        if host in seen:
            continue
        seen.add(host)

        confinement_root: Path | None = None
        if host == "copilot":
            destination = home / f".copilot/installed-plugins/_direct/{PLUGIN_NAME}"
            st, line = _inspect_link(host, REPO_ROOT, destination, None, mode)
            if line:
                print(line)
            if st > overall_status:
                overall_status = st
            continue
        elif host == "antigravity":
            if workspace is not None:
                destination = workspace / f".agents/plugins/{PLUGIN_NAME}"
                confinement_root = workspace
            else:
                destination = home / f".gemini/config/plugins/{PLUGIN_NAME}"
            st, line = _inspect_link(host, REPO_ROOT, destination, confinement_root, mode)
            if line:
                print(line)
            if st > overall_status:
                overall_status = st
            continue
        elif host == "antigravity-cli":
            destination = home / f".gemini/antigravity-cli/plugins/{PLUGIN_NAME}"
            st, line = _inspect_link(host, REPO_ROOT, destination, None, mode)
            if line:
                print(line)
            if st > overall_status:
                overall_status = st
            continue
        elif host == "codex":
            if workspace is not None:
                destination = workspace / f".agents/plugins/{PLUGIN_NAME}"
                confinement_root = workspace
            else:
                destination = home / f".agents/plugins/{PLUGIN_NAME}"
            st, line = _inspect_link(host, REPO_ROOT, destination, confinement_root, mode)
            if line:
                print(line)
            if st > overall_status:
                overall_status = st
            continue
        elif host == "cursor":
            if workspace is not None:
                destination = workspace / f".agents/plugins/{PLUGIN_NAME}"
                confinement_root = workspace
            else:
                destination = home / f".cursor/plugins/local/{PLUGIN_NAME}"
            st, line = _inspect_link(host, REPO_ROOT, destination, confinement_root, mode)
            if line:
                print(line)
            if st > overall_status:
                overall_status = st
            continue
        elif host == "opencode":
            destination_root = home / ".config/opencode/skills"
        elif host == "zcode":
            destination_root = home / ".zcode/skills"
        elif host == "windsurf":
            if workspace is None:
                sys.stderr.write(f"ERROR: --host {host} requires --workspace PATH\n")
                overall_status = max(overall_status, 2)
                continue
            destination_root = workspace / ".windsurf/skills"
            confinement_root = workspace
        else:
            continue

        for source in sorted(SKILLS_DIR.iterdir()):
            if not source.is_dir() or not (source / "SKILL.md").is_file():
                continue
            skill_name = source.name
            st, line = _inspect_link(
                host,
                source,
                destination_root / skill_name,
                confinement_root,
                mode,
            )
            if line:
                print(line)
            if st > overall_status:
                overall_status = st

    if mode == "dry-run":
        print("Dry run only. Repeat with --apply to create the planned links.")
    return overall_status


def command_setup_multi_agent(args: argparse.Namespace) -> int:
    mode = "dry-run"
    if getattr(args, "check", False):
        mode = "check"
    elif getattr(args, "apply", False):
        mode = "apply"
    hosts = getattr(args, "host", None) or []
    workspace_str = getattr(args, "workspace", None)
    workspace = Path(workspace_str).resolve() if workspace_str else None
    return setup_multi_agent(
        mode=mode,
        hosts=hosts if hosts else None,
        workspace=workspace,
    )
