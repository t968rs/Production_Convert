"""Tests that ProdCopier ships only git-tracked files when tracked_only is set."""
import shutil
from pathlib import Path

import pytest

from conversion.project_model import FolderSpec, ProdConfig, ProjectPaths
from conversion.prod_deploy import ProdCopier
from tests._git import git as _git

pytestmark = [
    pytest.mark.skipif(shutil.which("git") is None, reason="git not installed"),
    pytest.mark.usefixtures("isolate_git"),
]


def _make_source(root: Path) -> None:
    (root / "scripts" / "fpm" / "cache").mkdir(parents=True)
    (root / "scripts" / "fpm" / "__init__.py").write_text("_debug_override = False\n", encoding="utf-8")
    (root / "scripts" / "fpm" / "tool.py").write_text("x = 1\n", encoding="utf-8")
    (root / "scripts" / "fpm" / "cache" / "local.db").write_text("cache", encoding="utf-8")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    (root / "NOTES.md").write_text("local notes\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "scripts/fpm/__init__.py", "scripts/fpm/tool.py", "README.md")


def _config(tracked_only: bool = True) -> ProdConfig:
    return ProdConfig(
        folders=[FolderSpec(name="scripts", allowed=["fpm/**"])],
        top_level_files=["*.md"],
        debug_override_rel="scripts/fpm/__init__.py",
        tracked_only=tracked_only,
    )


def _run(tmp_path: Path, tracked_only: bool = True):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    _make_source(src)
    result = ProdCopier(_config(tracked_only), ProjectPaths(src, dst)).run()
    shipped = sorted(p.relative_to(dst).as_posix() for p in result.copied)
    return result, shipped, src


def test_untracked_folder_file_is_not_copied(tmp_path):
    result, shipped, _ = _run(tmp_path)
    assert result.ok, result.errors
    assert "scripts/fpm/tool.py" in shipped
    assert "scripts/fpm/cache/local.db" not in shipped


def test_untracked_top_level_file_is_not_copied(tmp_path):
    _, shipped, _ = _run(tmp_path)
    assert "README.md" in shipped
    assert "NOTES.md" not in shipped


def test_untracked_files_are_reported_as_skipped(tmp_path):
    result, _, src = _run(tmp_path)
    skipped = {p.relative_to(src).as_posix() for p in result.skipped}
    assert {"scripts/fpm/cache/local.db", "NOTES.md"} <= skipped


def test_tracked_only_false_copies_untracked_files(tmp_path):
    _, shipped, _ = _run(tmp_path, tracked_only=False)
    assert "scripts/fpm/cache/local.db" in shipped
    assert "NOTES.md" in shipped


def test_non_git_source_is_an_error(tmp_path):
    src, dst = tmp_path / "plain", tmp_path / "dst"
    (src / "scripts").mkdir(parents=True)
    result = ProdCopier(_config(), ProjectPaths(src, dst)).run()
    assert not result.ok
    assert any("git ls-files" in e for e in result.errors)
