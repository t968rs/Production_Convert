"""Tests that ProdCopier warns about, then still copies, tracked files with uncommitted changes."""
import shutil
import subprocess
from pathlib import Path

import pytest

from conversion.project_model import FolderSpec, ProdConfig, ProjectPaths
from conversion.prod_deploy import ProdCopier, _parse_porcelain_z

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

_GIT_IDENTITY = (
    "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
)


@pytest.fixture(autouse=True)
def _isolate_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git discovery inside tmp_path, independent of any enclosing repo or env overrides."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *_GIT_IDENTITY, "-C", str(root), *args], check=True, capture_output=True)


def _make_committed_source(root: Path) -> None:
    (root / "scripts" / "fpm").mkdir(parents=True)
    (root / "scripts" / "fpm" / "__init__.py").write_text("_debug_override = False\n", encoding="utf-8")
    (root / "scripts" / "fpm" / "tool.py").write_text("x = 1\n", encoding="utf-8")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "release")


def _config() -> ProdConfig:
    return ProdConfig(
        folders=[FolderSpec(name="scripts", allowed=["fpm/**"])],
        top_level_files=["*.md"],
        debug_override_rel="scripts/fpm/__init__.py",
    )


def _paths(tmp_path: Path) -> ProjectPaths:
    src = tmp_path / "src"
    src.mkdir()
    _make_committed_source(src)
    return ProjectPaths(src, tmp_path / "dst")


def test_dirty_tracked_file_is_warned_and_copied(tmp_path, capsys):
    paths = _paths(tmp_path)
    (paths.source_root / "scripts" / "fpm" / "tool.py").write_text("x = 2\n", encoding="utf-8")
    result = ProdCopier(_config(), paths).run()
    err = capsys.readouterr().err
    assert result.ok, result.errors
    assert "WARNING" in err
    assert "scripts/fpm/tool.py" in err
    assert "README.md" not in err
    shipped = (paths.dest_root / "scripts" / "fpm" / "tool.py").read_text(encoding="utf-8")
    assert shipped == "x = 2\n"


def test_staged_change_is_warned(tmp_path, capsys):
    paths = _paths(tmp_path)
    (paths.source_root / "README.md").write_text("edited\n", encoding="utf-8")
    _git(paths.source_root, "add", "README.md")
    result = ProdCopier(_config(), paths).run()
    assert result.ok, result.errors
    assert "README.md" in capsys.readouterr().err


def test_clean_tree_prints_no_warning(tmp_path, capsys):
    paths = _paths(tmp_path)
    (paths.source_root / "NOTES.md").write_text("untracked\n", encoding="utf-8")
    result = ProdCopier(_config(), paths).run()
    assert result.ok, result.errors
    assert "WARNING" not in capsys.readouterr().err


def test_parse_porcelain_drops_rename_source():
    output = "R  new.py\0old.py\0 M tool.py\0"
    assert _parse_porcelain_z(output) == ["new.py", "tool.py"]
