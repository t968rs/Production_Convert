"""End-to-end tests: ProdCopier.run swaps help links in the copied .atbx and never in the source archive."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

import conversion.prod_deploy as prod_deploy
from conversion.prod_deploy import _PROJECT_DEF_DIR, CopyResult, ProdCopier, load_project
from conversion.project_model import ProdConfig, ProjectPaths

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

_GIT_IDENTITY = (
    "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
)
_HELP_ROOT = "//srv/share/fpm_releases"
_VERSION = "v1.0.0"
_ATBX = "floodplain_mapping.atbx"
_EXTRA = "extra_tools.atbx"
_RC = "SmoothAndSimplifyPolygons.tool/tool.content.rc"
_PAGE = "tool_metadata/tool_help/smooth_simplify.html"
_GONE = "tool_metadata/tool_help/gone.html"
_FRAGMENT = "tool_metadata/tool_help/_fragments/x.html"
_STALE = "tool_metadata/tool_help/stale.html"
_DEBUG = "scripts/fpm/__init__.py"
_SOURCE_FILES = {
    _DEBUG: "_debug_override = True\n",
    "calcs/calc.py": "x = 1\n",
    "reference/notes.txt": "notes\n",
    _PAGE: "<html></html>\n",
    _FRAGMENT: "<section></section>\n",
    "tool_metadata/tool_help/_template.html": "$title\n",
}


@pytest.fixture(autouse=True)
def _isolate_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git discovery inside tmp_path, independent of any enclosing repo or env overrides."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_WORK_TREE", raising=False)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *_GIT_IDENTITY, "-C", str(root), *args], check=True, capture_output=True)


def _archive(path: Path, href: Optional[str]) -> None:
    """An .atbx whose tool.content.rc links to href (JSON-escaped as Pro writes it), or holds no link."""
    usage = "No link here." if href is None else f'<a href="{href}">Full Tool Help</a>'
    text = json.dumps({"map": {"usage": usage}}, indent=1)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_RC, text.encode("utf-8"))


def _source(src: Path, archives: Dict[str, Optional[str]]) -> None:
    """A committed source checkout; archives maps each top-level .atbx name to its link's tail, or None."""
    for rel, text in _SOURCE_FILES.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text, encoding="utf-8")
    for name, tail in archives.items():
        _archive(src / name, None if tail is None else src.as_uri() + "/" + tail)
    _git(src, "init", "-q")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "release")


def _project(
    tmp_path: Path,
    archives: Optional[Dict[str, Optional[str]]] = None,
    help_root: Optional[str] = _HELP_ROOT,
) -> Tuple[ProdConfig, ProjectPaths]:
    """Load the real fpm.json and a test fpm.env through load_project, as run.py does.

    DEST_ROOT is a local folder under tmp_path; HELP_ROOT is the UNC share unless help_root is None.
    """
    src, defs = tmp_path / "src", tmp_path / "defs"
    src.mkdir()
    defs.mkdir()
    _source(src, archives if archives is not None else {_ATBX: _PAGE})
    shutil.copyfile(_PROJECT_DEF_DIR / "fpm.json", defs / "fpm.json")
    env = [f"SOURCE_ROOT={src.as_posix()}", f"DEST_ROOT={(tmp_path / 'releases').as_posix()}"]
    env += [] if help_root is None else [f"HELP_ROOT={help_root}"]
    (defs / "fpm.env").write_text("\n".join(env) + "\n", encoding="utf-8")
    return load_project("fpm", _VERSION, project_def_dir=defs)


def _rc_text(atbx: Path) -> str:
    with zipfile.ZipFile(atbx) as zf:
        return zf.read(_RC).decode("utf-8")


def _errors_naming(result: CopyResult, text: str) -> List[str]:
    return [error for error in result.errors if text in error]


# --- real run ----------------------------------------------------------------------------------------------

def test_run_swaps_links_in_the_copied_archive(tmp_path):
    cfg, paths = _project(tmp_path)
    source_atbx, dest_atbx = paths.source_root / _ATBX, paths.dest_root / _ATBX
    source_bytes = source_atbx.read_bytes()
    result = ProdCopier(cfg, paths).run()
    assert result.ok, result.errors
    assert dest_atbx in result.patched
    assert paths.dest_root / _DEBUG in result.patched
    new_href = (Path(_HELP_ROOT) / paths.dest_root.name).as_uri() + "/" + _PAGE
    assert new_href in _rc_text(dest_atbx)
    assert paths.source_root.as_uri() not in _rc_text(dest_atbx)
    assert source_atbx.read_bytes() == source_bytes


def test_run_reports_a_missing_target_and_keeps_the_copy(tmp_path):
    cfg, paths = _project(tmp_path, {_ATBX: _GONE})
    result = ProdCopier(cfg, paths).run()
    dest_atbx = paths.dest_root / _ATBX
    assert not result.ok
    assert _errors_naming(result, "gone.html"), result.errors
    assert dest_atbx not in result.patched
    assert dest_atbx.read_bytes() == (paths.source_root / _ATBX).read_bytes()


def test_local_dest_without_help_root_is_one_error(tmp_path):
    cfg, paths = _project(tmp_path, {_ATBX: _PAGE, _EXTRA: None}, help_root=None)
    result = ProdCopier(cfg, paths).run()
    dest_atbx = paths.dest_root / _ATBX
    assert len(result.errors) == 1, result.errors
    assert "HELP_ROOT" in result.errors[0]
    assert _ATBX in result.errors[0]
    assert not _errors_naming(result, _EXTRA)
    assert dest_atbx not in result.patched
    assert paths.dest_root / _EXTRA not in result.patched
    assert dest_atbx.read_bytes() == (paths.source_root / _ATBX).read_bytes()
    assert paths.source_root.as_uri() in _rc_text(dest_atbx)


def test_stale_dest_file_does_not_satisfy_a_link(tmp_path):
    cfg, paths = _project(tmp_path, {_ATBX: _STALE})
    stale = paths.dest_root / _STALE
    stale.parent.mkdir(parents=True)
    stale.write_text("<html>left from an earlier run</html>\n", encoding="utf-8")
    result = ProdCopier(cfg, paths).run()
    assert not result.ok
    assert _errors_naming(result, "stale.html"), result.errors
    assert paths.dest_root / _ATBX not in result.patched


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry"])
def test_link_to_a_denied_source_file_fails(tmp_path, dry_run):
    cfg, paths = _project(tmp_path, {_ATBX: _FRAGMENT})
    assert (paths.source_root / _FRAGMENT).is_file()
    result = ProdCopier(cfg, paths, dry_run=dry_run).run()
    assert not result.ok
    assert _errors_naming(result, "_fragments/x.html"), result.errors
    assert paths.dest_root / _ATBX not in result.patched


def _explode(*args, **kwargs):
    raise RuntimeError("swap exploded")


def test_swap_failure_is_one_error_and_keeps_debug_patch(tmp_path, monkeypatch):
    cfg, paths = _project(tmp_path)
    monkeypatch.setattr(prod_deploy, "swap_atbx_links", _explode)
    result = ProdCopier(cfg, paths).run()
    assert len(result.errors) == 1, result.errors
    assert "swap exploded" in result.errors[0]
    assert paths.dest_root / _DEBUG in result.patched
    assert paths.dest_root / _ATBX not in result.patched


# --- dry run -----------------------------------------------------------------------------------------------

def test_dry_run_checks_the_source_and_writes_nothing(tmp_path):
    cfg, paths = _project(tmp_path, {_ATBX: _PAGE, _EXTRA: _GONE})
    before = {name: (paths.source_root / name).read_bytes() for name in (_ATBX, _EXTRA)}
    result = ProdCopier(cfg, paths, dry_run=True).run()
    assert not result.ok
    assert _errors_naming(result, "gone.html"), result.errors
    assert not _errors_naming(result, "smooth_simplify.html"), result.errors
    assert paths.dest_root / _ATBX in result.patched
    assert paths.dest_root / _EXTRA not in result.patched
    assert not paths.dest_root.exists()
    assert {name: (paths.source_root / name).read_bytes() for name in before} == before
