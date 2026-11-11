#!/usr/bin/env python3
"""Hermetic tests for the native-Windows to WSL command wrapper.

The wrapper runs in print mode (CLAUDE_OBSIDIAN_WSL_PRINT_COMMAND=1), so these
tests never start WSL. They need PowerShell: ``pwsh`` anywhere, or Windows
PowerShell on native Windows; otherwise they are skipped.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "claude-obsidian.ps1"
CMD_SHIM = ROOT / "scripts" / "claude-obsidian.cmd"
CORE = ROOT / "scripts" / "claude-obsidian.py"
WRAPPER_ENVIRONMENT = (
    "CLAUDE_OBSIDIAN_VAULT",
    "CLAUDE_OBSIDIAN_WSL_DISTRO",
    "CLAUDE_OBSIDIAN_WSL_EXE",
    "CLAUDE_OBSIDIAN_WSL_MOUNT_ROOT",
    "CLAUDE_OBSIDIAN_WSL_PRINT_COMMAND",
    "CLAUDE_OBSIDIAN_WSL_PYTHON",
)


def _powershell() -> str | None:
    found = shutil.which("pwsh")
    if found:
        return found
    if os.name == "nt":
        return shutil.which("powershell")
    return None


POWERSHELL = _powershell()


def _expected_posix(path: Path) -> str:
    text = str(path)
    if os.name != "nt":
        return text
    return f"/mnt/{text[0].lower()}/{text[3:].replace(chr(92), '/')}"


@unittest.skipIf(POWERSHELL is None, "PowerShell is not available")
class WslWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.cwd = Path(self._temporary.name).resolve()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def run_wrapper(
        self,
        *arguments: str,
        env: dict[str, str] | None = None,
        print_only: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in WRAPPER_ENVIRONMENT
        }
        if print_only:
            environment["CLAUDE_OBSIDIAN_WSL_PRINT_COMMAND"] = "1"
        environment.update(env or {})
        command = [str(POWERSHELL), "-NoLogo", "-NoProfile", "-NonInteractive"]
        if os.name == "nt":
            command += ["-ExecutionPolicy", "Bypass"]
        command += ["-File", str(WRAPPER), *arguments]
        return subprocess.run(
            command,
            cwd=self.cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )

    def argv(self, *arguments: str, env: dict[str, str] | None = None) -> list[str]:
        completed = self.run_wrapper(*arguments, env=env)
        self.assertEqual(0, completed.returncode, completed.stderr)
        return json.loads(completed.stdout)[1:]

    def assert_refused(
        self, *arguments: str, env: dict[str, str] | None = None
    ) -> str:
        completed = self.run_wrapper(*arguments, env=env)
        self.assertEqual(2, completed.returncode, completed.stdout)
        self.assertIn("ERR WSL_WRAPPER:", completed.stderr)
        self.assertEqual("", completed.stdout.strip())
        return completed.stderr

    def test_default_runs_python3_in_wsl_from_the_converted_directory(self) -> None:
        self.assertEqual(
            [
                "--cd",
                _expected_posix(self.cwd),
                "-e",
                "env",
                "PYTHONDONTWRITEBYTECODE=1",
                "python3",
                _expected_posix(CORE),
                "doctor",
            ],
            self.argv("doctor"),
        )

    def test_drive_paths_are_converted_and_spaces_survive(self) -> None:
        argv = self.argv(
            "doctor",
            "--vault",
            r"D:\Notes\My Vault",
            "--out=E:/reports/lint.json",
            "C:\\",
        )
        self.assertEqual(
            [
                "doctor",
                "--vault",
                "/mnt/d/Notes/My Vault",
                "--out=/mnt/e/reports/lint.json",
                "/mnt/c/",
            ],
            argv[-5:],
        )

    def test_non_path_arguments_pass_through_unchanged(self) -> None:
        arguments = ["retrieve", "durable memory", "wiki/Page.md", "--top", "1", "C:", "a:b"]
        self.assertEqual(arguments, self.argv(*arguments)[-len(arguments) :])

    def test_pinned_distribution_is_passed_to_wsl(self) -> None:
        argv = self.argv("doctor", env={"CLAUDE_OBSIDIAN_WSL_DISTRO": "Ubuntu-24.04"})
        self.assertEqual(["-d", "Ubuntu-24.04", "--cd"], argv[:3])

    def test_wsl_unc_paths_convert_and_select_their_distribution(self) -> None:
        argv = self.argv(
            "doctor",
            "--vault",
            r"\\wsl.localhost\Debian\var\vault",
            r"\\wsl$\Debian\srv",
        )
        self.assertEqual(["-d", "Debian"], argv[:2])
        self.assertEqual(["--vault", "/var/vault", "/srv"], argv[-3:])

    def test_pinned_distribution_conflicting_with_a_path_is_refused(self) -> None:
        stderr = self.assert_refused(
            "doctor",
            "--vault",
            r"\\wsl.localhost\Debian\var\vault",
            env={"CLAUDE_OBSIDIAN_WSL_DISTRO": "Ubuntu"},
        )
        self.assertIn("one distribution", stderr)

    def test_paths_from_two_distributions_are_refused(self) -> None:
        self.assert_refused(
            r"\\wsl.localhost\Debian\var\a",
            r"\\wsl.localhost\Ubuntu\var\b",
        )

    def test_invalid_distribution_name_is_refused(self) -> None:
        self.assert_refused("doctor", env={"CLAUDE_OBSIDIAN_WSL_DISTRO": "bad name"})

    def test_mount_root_override_and_validation(self) -> None:
        argv = self.argv(
            r"C:\Projects\Test", env={"CLAUDE_OBSIDIAN_WSL_MOUNT_ROOT": "/"}
        )
        self.assertEqual("/c/Projects/Test", argv[-1])
        self.assert_refused("doctor", env={"CLAUDE_OBSIDIAN_WSL_MOUNT_ROOT": "mnt"})

    def test_vault_environment_is_converted_and_forwarded(self) -> None:
        argv = self.argv("doctor", env={"CLAUDE_OBSIDIAN_VAULT": r"C:\Vaults\Main"})
        index = argv.index("PYTHONDONTWRITEBYTECODE=1")
        self.assertEqual("CLAUDE_OBSIDIAN_VAULT=/mnt/c/Vaults/Main", argv[index + 1])

    def test_python_interpreter_is_configurable(self) -> None:
        argv = self.argv("doctor", env={"CLAUDE_OBSIDIAN_WSL_PYTHON": "python3.12"})
        self.assertEqual(["python3.12", _expected_posix(CORE)], argv[-3:-1])

    def test_missing_wsl_executable_is_refused_before_running(self) -> None:
        completed = self.run_wrapper(
            "doctor",
            env={"CLAUDE_OBSIDIAN_WSL_EXE": str(self.cwd / "missing-wsl.exe")},
            print_only=False,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("CLAUDE_OBSIDIAN_WSL_EXE does not exist", completed.stderr)

    def test_exit_code_of_the_wsl_command_is_propagated(self) -> None:
        if os.name == "nt":
            fake = self.cwd / "fake-wsl.cmd"
            fake.write_text("@exit /b 7\r\n", encoding="ascii")
        else:
            fake = self.cwd / "fake-wsl"
            fake.write_text("#!/bin/sh\nexit 7\n", encoding="ascii")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        completed = self.run_wrapper(
            "doctor", env={"CLAUDE_OBSIDIAN_WSL_EXE": str(fake)}, print_only=False
        )
        self.assertEqual(7, completed.returncode, completed.stderr)


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "CMD shim needs native Windows")
class CmdShimTests(unittest.TestCase):
    def test_cmd_shim_forwards_arguments_to_the_wrapper(self) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in WRAPPER_ENVIRONMENT
        }
        environment["CLAUDE_OBSIDIAN_WSL_PRINT_COMMAND"] = "1"
        completed = subprocess.run(
            [str(CMD_SHIM), "doctor", "--vault", r"D:\Notes\My Vault"],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            ["doctor", "--vault", "/mnt/d/Notes/My Vault"],
            json.loads(completed.stdout)[-3:],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
