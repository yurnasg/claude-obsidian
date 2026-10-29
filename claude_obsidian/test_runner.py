"""Unified cross-platform test runner for claude-obsidian."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class TestResult:
    name: str
    category: str
    status: str  # "PASS", "FAIL", "SKIP", "TIMEOUT"
    duration_seconds: float
    returncode: int
    stdout: str = ""
    stderr: str = ""
    message: str = ""


class TestRunner:
    def __init__(
        self,
        *,
        plugin_root: Path = PLUGIN_ROOT,
        timeout: float = 180.0,
        fail_fast: bool = False,
        verbose: bool = False,
        pattern: str | None = None,
        as_json: bool = False,
    ) -> None:
        self.plugin_root = plugin_root
        self.timeout = timeout
        self.fail_fast = fail_fast
        self.verbose = verbose
        self.pattern = pattern
        self.as_json = as_json
        self.results: list[TestResult] = []

    def _clean_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.plugin_root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("CLAUDE_OBSIDIAN_VAULT", None)
        return env

    def _matches_pattern(self, name: str) -> bool:
        if not self.pattern:
            return True
        basename = os.path.basename(name)
        if fnmatch.fnmatch(name, self.pattern) or fnmatch.fnmatch(basename, self.pattern):
            return True
        try:
            if re.search(self.pattern, name):
                return True
        except re.error:
            pass
        return False

    def _execute_process(
        self,
        name: str,
        category: str,
        command: list[str],
        *,
        timeout: float | None = None,
    ) -> TestResult:
        eff_timeout = timeout or self.timeout
        start = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.plugin_root),
                env=self._clean_env(),
                capture_output=True,
                text=True,
                timeout=eff_timeout,
            )
            duration = time.perf_counter() - start
            status = "PASS" if completed.returncode == 0 else "FAIL"
            return TestResult(
                name=name,
                category=category,
                status=status,
                duration_seconds=round(duration, 3),
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.perf_counter() - start
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "")
            return TestResult(
                name=name,
                category=category,
                status="TIMEOUT",
                duration_seconds=round(duration, 3),
                returncode=-1,
                stdout=stdout,
                stderr=stderr,
                message=f"Execution timed out after {eff_timeout} seconds",
            )
        except Exception as exc:
            duration = time.perf_counter() - start
            return TestResult(
                name=name,
                category=category,
                status="FAIL",
                duration_seconds=round(duration, 3),
                returncode=-1,
                message=str(exc),
            )

    def _report_single(self, result: TestResult) -> None:
        if self.as_json:
            return
        status_label = result.status
        cat = f"[{result.category}]".ljust(12)
        print(f"{cat} {result.name.ljust(45)} ... {status_label} ({result.duration_seconds:.2f}s)")
        if self.verbose or result.status in ("FAIL", "TIMEOUT"):
            if result.message:
                print(f"      Note: {result.message}")
            if result.stdout.strip():
                print("      --- stdout ---")
                for line in result.stdout.strip().splitlines()[-25:]:
                    print(f"      {line}")
            if result.stderr.strip():
                print("      --- stderr ---")
                for line in result.stderr.strip().splitlines()[-25:]:
                    print(f"      {line}")

    def run_unit_tests(self) -> bool:
        tests_dir = self.plugin_root / "tests"
        test_files = sorted(tests_dir.glob("test_*.py"))
        for test_file in test_files:
            rel_name = test_file.relative_to(self.plugin_root).as_posix()
            if not self._matches_pattern(rel_name):
                continue
            res = self._execute_process(
                name=rel_name,
                category="unit",
                command=[sys.executable, str(test_file)],
            )
            self.results.append(res)
            self._report_single(res)
            if self.fail_fast and res.status in ("FAIL", "TIMEOUT"):
                return False
        return True

    def run_contract_tests(self) -> bool:
        cli_script = self.plugin_root / "scripts" / "claude-obsidian.py"
        tasks = [
            ("contracts:check-only", ["contracts", "--check-only"]),
            ("contracts:verify", ["contracts", "--verify"]),
        ]
        for name, args in tasks:
            if not self._matches_pattern(name):
                continue
            res = self._execute_process(
                name=name,
                category="contracts",
                command=[sys.executable, str(cli_script), *args],
            )
            self.results.append(res)
            self._report_single(res)
            if self.fail_fast and res.status in ("FAIL", "TIMEOUT"):
                return False
        return True

    def run_package_validation(self) -> bool:
        name = "package:validate"
        if not self._matches_pattern(name):
            return True
        cli_script = self.plugin_root / "scripts" / "claude-obsidian.py"
        res = self._execute_process(
            name=name,
            category="package",
            command=[sys.executable, str(cli_script), "package", "validate"],
        )
        self.results.append(res)
        self._report_single(res)
        if self.fail_fast and res.status in ("FAIL", "TIMEOUT"):
            return False
        return True

    def run_shell_tests(self) -> bool:
        tests_dir = self.plugin_root / "tests"
        shell_files = sorted(tests_dir.glob("test_*.sh"))
        bash_path = shutil.which("bash") if os.name != "nt" else None
        for shell_file in shell_files:
            rel_name = shell_file.relative_to(self.plugin_root).as_posix()
            if not self._matches_pattern(rel_name):
                continue
            if os.name == "nt":
                res = TestResult(
                    name=rel_name,
                    category="shell",
                    status="SKIP",
                    duration_seconds=0.0,
                    returncode=0,
                    message="shell tests require POSIX platform (native Windows uses Python test runner)",
                )
            elif not bash_path:
                res = TestResult(
                    name=rel_name,
                    category="shell",
                    status="SKIP",
                    duration_seconds=0.0,
                    returncode=0,
                    message="bash not available on this platform",
                )
            else:
                res = self._execute_process(
                    name=rel_name,
                    category="shell",
                    command=[bash_path, str(shell_file)],
                )
            self.results.append(res)
            self._report_single(res)
            if self.fail_fast and res.status in ("FAIL", "TIMEOUT"):
                return False
        return True

    def render_summary(self, total_duration: float) -> int:
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status in ("FAIL", "TIMEOUT"))
        skipped = sum(1 for r in self.results if r.status == "SKIP")
        total = len(self.results)
        ok = failed == 0

        if self.as_json:
            payload = {
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                    "duration_seconds": round(total_duration, 3),
                    "ok": ok,
                },
                "results": [asdict(r) for r in self.results],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if ok else 1

        print("=" * 70)
        if failed > 0 and not self.verbose:
            print("FAILURES SUMMARY:")
            print("-" * 70)
            for r in self.results:
                if r.status in ("FAIL", "TIMEOUT"):
                    print(f"FAILED: {r.name} ({r.category})")
                    if r.message:
                        print(f"  Note: {r.message}")
                    if r.stderr.strip():
                        for line in r.stderr.strip().splitlines()[-20:]:
                            print(f"  {line}")
                    elif r.stdout.strip():
                        for line in r.stdout.strip().splitlines()[-20:]:
                            print(f"  {line}")
                    print("-" * 70)

        print(
            f"Results: {passed} passed, {failed} failed, {skipped} skipped "
            f"in {total_duration:.2f}s"
        )
        print(f"STATUS: {'OK' if ok else 'FAILED'}")
        print("=" * 70)
        return 0 if ok else 1


def run_tests(
    *,
    all_suites: bool = False,
    unit: bool = False,
    contracts: bool = False,
    package: bool = False,
    shell: bool = False,
    validate: bool = False,
    pattern: str | None = None,
    verbose: bool = False,
    fail_fast: bool = False,
    timeout: float = 180.0,
    as_json: bool = False,
    plugin_root: Path = PLUGIN_ROOT,
) -> int:
    if validate:
        contracts = True
        package = True

    # If no specific suite is selected, default to all
    if not (unit or contracts or package or shell or validate):
        all_suites = True

    if all_suites:
        unit = True
        contracts = True
        package = True
        shell = True

    runner = TestRunner(
        plugin_root=plugin_root,
        timeout=timeout,
        fail_fast=fail_fast,
        verbose=verbose,
        pattern=pattern,
        as_json=as_json,
    )

    if not as_json:
        print("=" * 70)
        print("claude-obsidian unified test runner")
        print(f"Python: {sys.version.split()[0]} | Platform: {sys.platform} | Root: {plugin_root}")
        print("=" * 70)

    start_time = time.perf_counter()

    if unit:
        if not runner.run_unit_tests() and fail_fast:
            return runner.render_summary(time.perf_counter() - start_time)

    if shell:
        if not runner.run_shell_tests() and fail_fast:
            return runner.render_summary(time.perf_counter() - start_time)

    if contracts:
        if not runner.run_contract_tests() and fail_fast:
            return runner.render_summary(time.perf_counter() - start_time)

    if package:
        if not runner.run_package_validation() and fail_fast:
            return runner.render_summary(time.perf_counter() - start_time)

    total_duration = time.perf_counter() - start_time
    return runner.render_summary(total_duration)
