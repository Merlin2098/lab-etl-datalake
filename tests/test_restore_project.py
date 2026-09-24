from __future__ import annotations

from pathlib import Path

from scripts.restore_project import restore_project


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_restore_dry_run_skips_dependency_install(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[project]\nname = \"demo\"\nversion = \"0.1.0\"\n")

    payload = restore_project(tmp_path, dry_run=True)

    assert payload["status"] == "ok"
    assert payload["dependencies"]["status"] == "skipped"
    assert payload["dependencies"]["reason"] == "dry-run"


def test_restore_skips_dependency_install_without_pyproject(tmp_path: Path) -> None:
    payload = restore_project(tmp_path, dry_run=False)

    assert payload["dependencies"]["status"] == "skipped"
    assert payload["dependencies"]["reason"] == "no pyproject.toml found"
