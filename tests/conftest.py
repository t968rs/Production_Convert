"""Shared pytest configuration for the tests package.

The sibling ``__init__.py`` makes ``tests`` a package, so pytest's default import mode inserts the repository root
(the first directory above the package) into ``sys.path`` and the tests can import ``conversion``.
"""
from pathlib import Path

import pytest


@pytest.fixture
def isolate_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git discovery inside tmp_path, independent of any enclosing repo or env overrides."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)
    monkeypatch.delenv("GIT_INDEX_FILE", raising=False)
    monkeypatch.delenv("GIT_OBJECT_DIRECTORY", raising=False)
    monkeypatch.delenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", raising=False)
    monkeypatch.delenv("GIT_COMMON_DIR", raising=False)
