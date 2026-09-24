from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_installer(
    script: str, target: Path, *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            script,
            "--target",
            str(target),
            "--dry-run",
            "--without-structure",
            *args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        input=input_text,
        check=False,
    )


def test_windows_installer_dry_run_reports_summary(tmp_path: Path) -> None:
    target = tmp_path / "windows-host"

    result = _run_installer("install_windows.py", target)

    assert result.returncode == 0, result.stderr
    assert "Dry run summary" in result.stdout
    assert "did not create or synchronize .venv" in result.stdout
    assert not target.exists()


def test_linux_installer_dry_run_reports_summary(tmp_path: Path) -> None:
    target = tmp_path / "linux-host"

    result = _run_installer("install_linux.py", target)

    assert result.returncode == 0, result.stderr
    assert "Dry run summary" in result.stdout
    assert "did not create or synchronize .venv" in result.stdout
    assert not target.exists()


def test_installers_reject_removed_environment_shortcuts(tmp_path: Path) -> None:
    result = _run_installer("install_linux.py", tmp_path / "host", "--local")

    assert result.returncode != 0
    assert "unrecognized arguments: --local" in result.stderr


def test_installer_rerun_copies_only_missing_files(tmp_path: Path) -> None:
    target = tmp_path / "rerun-host"

    first = subprocess.run(
        [
            sys.executable,
            "install_linux.py",
            "--target",
            str(target),
            "--without-structure",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    assert (target / "AGENTS.md").exists()

    second = subprocess.run(
        [
            sys.executable,
            "install_linux.py",
            "--target",
            str(target),
            "--without-structure",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr
    assert "Skipped existing" in second.stdout
