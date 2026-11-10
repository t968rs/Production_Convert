"""Tests that project_definitions/fpm.json ships the built help pages and keeps their sources out."""
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import pytest

from conversion.prod_deploy import _PROJECT_DEF_DIR, ProdCopier, _walk_folder, load_project
from conversion.project_model import FolderSpec, ProdConfig, ProjectPaths

_GIT_IDENTITY = (
    "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
)
_SHIPPED = (
    "tool_metadata/tool_help/smooth_simplify.html",
    "tool_metadata/tool_help/img/flow.png",
    "tool_metadata/tool_help/img/detail/zoom.svg",
)
_KEPT_OUT = (
    "tool_metadata/tool_help/_template.html",
    "tool_metadata/tool_help/_fragments/smooth_simplify.html",
    "tool_metadata/tool_help/notes.md",
    "tool_metadata/tools/SmoothAndSimplifyPolygons.xml",
    "tool_metadata/floodplain_mapping.atbx.xml",
    "tool_metadata/RECENT_CHANGES.md",
)
_UNTRACKED_PAGE = "tool_metadata/tool_help/draft.html"
_REQUIRED_SOURCE = ("scripts/fpm/__init__.py", "calcs/calc.py", "reference/notes.txt")


@pytest.fixture(autouse=True)
def _isolate_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git discovery inside tmp_path, independent of any enclosing repo or env overrides."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *_GIT_IDENTITY, "-C", str(root), *args], check=True, capture_output=True)


def _fpm_config() -> ProdConfig:
    return ProdConfig.from_json(_PROJECT_DEF_DIR / "fpm.json")


def _help_spec(cfg: ProdConfig) -> FolderSpec:
    specs = {spec.name: spec for spec in cfg.folders}
    assert "tool_metadata" in specs, f"fpm.json has no tool_metadata folder: {sorted(specs)}"
    return specs["tool_metadata"]


def _write(root: Path, rels: Iterable[str]) -> None:
    for rel in rels:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x\n")


def test_tool_metadata_folder_is_optional():
    assert _help_spec(_fpm_config()).required is False


def test_walk_ships_pages_and_images_only(tmp_path):
    cfg = _fpm_config()
    spec = _help_spec(cfg)
    _write(tmp_path, _SHIPPED + _KEPT_OUT)
    files, _ = _walk_folder(tmp_path / spec.name, list(spec.denied), list(cfg.global_denied), list(spec.allowed))
    assert sorted(f.relative_to(tmp_path).as_posix() for f in files) == sorted(_SHIPPED)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_run_ships_tracked_pages_only(tmp_path):
    src, defs = tmp_path / "src", tmp_path / "defs"
    _write(src, _REQUIRED_SOURCE + _SHIPPED + _KEPT_OUT)
    _git(src, "init", "-q")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "release")
    _write(src, [_UNTRACKED_PAGE])
    defs.mkdir()
    shutil.copyfile(_PROJECT_DEF_DIR / "fpm.json", defs / "fpm.json")
    env = f"SOURCE_ROOT={src.as_posix()}\nDEST_ROOT={(tmp_path / 'releases').as_posix()}\n"
    (defs / "fpm.env").write_text(env, encoding="utf-8")
    cfg, paths = load_project("fpm", "v1.0.0", project_def_dir=defs)
    result = ProdCopier(cfg, paths).run()
    assert result.ok, result.errors
    shipped = {p.relative_to(paths.dest_root).as_posix() for p in result.copied}
    assert set(_SHIPPED) <= shipped
    assert not shipped & set(_KEPT_OUT)
    assert _UNTRACKED_PAGE not in shipped


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry"])
def test_absent_optional_folder_is_skipped(tmp_path, dry_run):
    src = tmp_path / "src"
    _write(src, ["scripts/fpm/__init__.py"])
    cfg = ProdConfig(
        folders=[FolderSpec(name="scripts", allowed=["fpm/**"]), FolderSpec(name="tool_metadata", required=False)],
        debug_override_rel="scripts/fpm/__init__.py",
        tracked_only=False,
    )
    try:
        result = ProdCopier(cfg, ProjectPaths(src, tmp_path / "dst"), dry_run=dry_run).run()
    except FileNotFoundError as exc:
        raise AssertionError(f"an absent required: false folder crashed the copy: {exc}") from exc
    assert result.ok, result.errors
    assert not any("tool_metadata" in error for error in result.errors)
