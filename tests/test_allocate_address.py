#!/usr/bin/env python3
"""Cross-platform test for address allocation diagnostic CLI."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class AllocateAddressCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.vault = Path(self._temp.name)
        (self.vault / "wiki").mkdir()
        (self.vault / ".obsidian").mkdir()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "claude-obsidian.py"),
            "allocate-address",
            "--vault",
            str(self.vault),
            *args,
        ]
        return subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_peek_and_default_are_read_only(self) -> None:
        files_before = sorted(p.relative_to(self.vault) for p in self.vault.rglob("*") if p.is_file())
        res_peek = self._run_cli("--peek")
        self.assertEqual(res_peek.returncode, 0, res_peek.stderr)
        self.assertEqual(res_peek.stdout.strip(), "1")

        res_default = self._run_cli()
        self.assertEqual(res_default.returncode, 0, res_default.stderr)
        self.assertEqual(res_default.stdout.strip(), "1")

        files_after = sorted(p.relative_to(self.vault) for p in self.vault.rglob("*") if p.is_file())
        self.assertEqual(files_before, files_after)

    def test_reads_existing_page_address(self) -> None:
        page = self.vault / "wiki" / "Page.md"
        page.write_text("---\naddress: c-000500\n---\n# Page\n", encoding="utf-8", newline="")
        res = self._run_cli("--peek")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "501")

    def test_legacy_allocate_is_rejected_as_read_only(self) -> None:
        res = self._run_cli("allocate")
        self.assertEqual(res.returncode, 2)
        self.assertIn("LEGACY_ALLOCATOR_READ_ONLY", res.stderr)
        self.assertFalse((self.vault / ".vault-meta").exists())


if __name__ == "__main__":
    unittest.main()
