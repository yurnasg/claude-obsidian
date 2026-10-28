#!/usr/bin/env python3
"""Hermetic tests for the safe multi-host Agent Plugins 1.0 & Agent Skills installer."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/setup-multi-agent.sh"


class SetupMultiAgentTests(unittest.TestCase):
    def invoke(self, home: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["HOME"] = str(home)
        return subprocess.run(
            ["bash", str(SCRIPT), *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_default_is_no_write_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.invoke(home)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Dry run only", result.stdout)
            self.assertFalse((home / ".copilot").exists())
            self.assertFalse((home / ".gemini").exists())
            self.assertFalse((home / ".agents").exists())

    def test_apply_is_idempotent_for_default_agent_plugin_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            first = self.invoke(home, "--apply")
            self.assertEqual(0, first.returncode, first.stderr)
            plugin_links = {
                "copilot": home / ".copilot/installed-plugins/_direct/claude-obsidian",
                "antigravity": home / ".gemini/config/plugins/claude-obsidian",
                "antigravity-cli": home
                / ".gemini/antigravity-cli/plugins/claude-obsidian",
                "codex": home / ".agents/plugins/claude-obsidian",
            }
            expected_skills = sorted(
                path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
            )
            self.assertEqual(15, len(expected_skills))
            for host, link in plugin_links.items():
                self.assertTrue(link.is_symlink(), host)
                self.assertEqual(ROOT, link.resolve(), host)
                self.assertTrue((link / "plugin.json").is_file(), host)
                discovered = sorted(
                    path.parent.name for path in (link / "skills").glob("*/SKILL.md")
                )
                self.assertEqual(expected_skills, discovered, host)
            second = self.invoke(home, "--apply")
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(4, second.stdout.count("READY"))

    def test_conflict_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            conflict = home / ".agents/plugins/claude-obsidian"
            conflict.mkdir(parents=True)
            marker = conflict / "mine"
            marker.write_text("preserve", encoding="utf-8")
            result = self.invoke(home, "--apply", "--host", "codex")
            self.assertEqual(2, result.returncode)
            self.assertEqual("preserve", marker.read_text(encoding="utf-8"))

    def test_antigravity_and_cursor_plugin_global_and_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            global_run = self.invoke(
                base,
                "--apply",
                "--host",
                "antigravity",
                "--host",
                "gemini",
                "--host",
                "cursor",
            )
            self.assertEqual(0, global_run.returncode, global_run.stderr)
            for link in (
                base / ".gemini/config/plugins/claude-obsidian",
                base / ".gemini/antigravity-cli/plugins/claude-obsidian",
                base / ".cursor/plugins/local/claude-obsidian",
            ):
                self.assertTrue(link.is_symlink(), str(link))
                self.assertEqual(ROOT, link.resolve())
                self.assertTrue((link / "plugin.json").is_file())

            workspace = base / "workspace"
            workspace.mkdir()
            ws_run = self.invoke(
                base,
                "--apply",
                "--host",
                "antigravity",
                "--workspace",
                str(workspace),
            )
            self.assertEqual(0, ws_run.returncode, ws_run.stderr)
            ws_plugin = workspace / ".agents/plugins/claude-obsidian"
            self.assertTrue(ws_plugin.is_symlink())
            self.assertEqual(ROOT, ws_plugin.resolve())
            self.assertTrue((ws_plugin / "plugin.json").is_file())

    def test_standalone_skills_hosts_opencode_zcode_windsurf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            first = self.invoke(
                home, "--apply", "--host", "opencode", "--host", "zcode"
            )
            self.assertEqual(0, first.returncode, first.stderr)
            expected = sorted(
                path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
            )
            self.assertEqual(15, len(expected))
            for skill_root in (
                home / ".config/opencode/skills",
                home / ".zcode/skills",
            ):
                discovered = sorted(
                    path.parent.name for path in skill_root.glob("*/SKILL.md")
                )
                self.assertEqual(expected, discovered)
                for skill_name in expected:
                    link = skill_root / skill_name
                    self.assertTrue(link.is_symlink(), skill_name)
                    self.assertEqual(ROOT / "skills" / skill_name, link.resolve())

            missing_ws = self.invoke(home, "--host", "windsurf")
            self.assertEqual(2, missing_ws.returncode)
            workspace = home / "workspace"
            workspace.mkdir()
            ws_applied = self.invoke(
                home,
                "--apply",
                "--host",
                "windsurf",
                "--workspace",
                str(workspace),
            )
            self.assertEqual(0, ws_applied.returncode, ws_applied.stderr)
            self.assertEqual(
                15,
                len(list((workspace / ".windsurf/skills").glob("*/SKILL.md"))),
            )

    def test_workspace_parent_symlinks_cannot_redirect_apply(self) -> None:
        for symlink_component in (".agents", ".agents/plugins"):
            with (
                self.subTest(component=symlink_component),
                tempfile.TemporaryDirectory() as directory,
            ):
                base = Path(directory)
                workspace = base / "workspace"
                outside = base / "outside"
                workspace.mkdir()
                outside.mkdir()
                link = workspace / symlink_component
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(outside, target_is_directory=True)
                preview = self.invoke(
                    base,
                    "--dry-run",
                    "--host",
                    "antigravity",
                    "--workspace",
                    str(workspace),
                )
                self.assertEqual(2, preview.returncode)
                self.assertIn("parent is a symlink", preview.stderr)
                result = self.invoke(
                    base,
                    "--apply",
                    "--host",
                    "antigravity",
                    "--workspace",
                    str(workspace),
                )
                self.assertEqual(2, result.returncode)
                self.assertIn("parent is a symlink", result.stderr)
                self.assertEqual([], list(outside.iterdir()))


if __name__ == "__main__":
    unittest.main()
