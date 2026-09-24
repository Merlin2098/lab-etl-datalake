from __future__ import annotations

from pathlib import Path

from install_linux import copy_skeleton, validate_target


def test_existing_host_file_is_left_untouched(tmp_path: Path) -> None:
    target = tmp_path / "host-existing"
    target.mkdir(parents=True)
    custom_file = target / "pyproject.toml"
    original = '[project]\nname = "custom"\nversion = "1.0.0"\n'
    custom_file.write_text(original, encoding="utf-8")

    copy_skeleton(target, force=False, dry_run=False, include_structure=False)

    assert custom_file.read_text(encoding="utf-8") == original


def test_force_overwrites_existing_host_file(tmp_path: Path) -> None:
    target = tmp_path / "host-force"
    target.mkdir(parents=True)
    custom_file = target / "pyproject.toml"
    custom_file.write_text("stale", encoding="utf-8")

    copy_skeleton(target, force=True, dry_run=False, include_structure=False)

    assert custom_file.read_text(encoding="utf-8") != "stale"


def test_copy_skeleton_copies_pyproject(tmp_path: Path) -> None:
    target = tmp_path / "host-requirements"

    summary = copy_skeleton(target, force=False, dry_run=False, include_structure=False)

    assert "pyproject.toml" in summary["copied"]
    assert (target / "pyproject.toml").exists()


def test_copy_skeleton_copies_agents_md(tmp_path: Path) -> None:
    target = tmp_path / "host-agents"

    summary = copy_skeleton(target, force=False, dry_run=False, include_structure=False)

    assert "AGENTS.md" in summary["copied"]
    assert (target / "AGENTS.md").exists()


def test_without_structure_does_not_copy_src_infra_tests(tmp_path: Path) -> None:
    target = tmp_path / "host-without-structure"

    copy_skeleton(target, force=False, dry_run=False, include_structure=False)

    assert not (target / "src").exists()
    assert not (target / "infra").exists()
    assert not (target / "tests").exists()


def test_with_structure_copies_src_infra_tests(tmp_path: Path) -> None:
    target = tmp_path / "host-with-structure"

    copy_skeleton(target, force=False, dry_run=False, include_structure=True)

    assert (target / "src").exists()
    assert (target / "infra").exists()
    assert (target / "tests").exists()


def test_settings_local_json_is_not_copied_to_host(tmp_path: Path) -> None:
    target = tmp_path / "host-settings"

    summary = copy_skeleton(target, force=False, dry_run=False, include_structure=False)

    assert ".claude/settings.local.json" not in summary["copied"]
    assert not (target / ".claude" / "settings.local.json").exists()


def test_docs_directory_is_not_copied_to_host(tmp_path: Path) -> None:
    target = tmp_path / "host-docs"

    summary = copy_skeleton(target, force=False, dry_run=False, include_structure=False)

    assert not any(p.startswith("docs/") or p == "docs" for p in summary["copied"])
    assert not (target / "docs").exists()


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    target = tmp_path / "host-dry"

    summary = copy_skeleton(target, force=False, dry_run=True, include_structure=False)

    assert "AGENTS.md" in summary["copied"]
    assert not (target / "AGENTS.md").exists()


def test_validate_target_rejects_template_root_itself() -> None:
    from install_linux import TEMPLATE_ROOT

    try:
        validate_target(TEMPLATE_ROOT)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_validate_target_rejects_path_inside_template_root() -> None:
    from install_linux import TEMPLATE_ROOT

    try:
        validate_target(TEMPLATE_ROOT / "src")
        assert False, "expected ValueError"
    except ValueError:
        pass
