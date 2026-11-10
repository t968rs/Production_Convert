"""Tests that the optional HELP_ROOT key of a project .env becomes ProjectPaths.help_root."""
from pathlib import Path

from conversion.prod_deploy import (
    _PROJECT_DEF_DIR,
    _generate_project_version_folder_name,
    _load_paths,
    _parse_env,
    load_project,
)
from conversion.project_model import ProjectPaths

_HELP_ROOT = "//srv/share/fpm_releases"
_VERSION = "v3.17.2"


def _env(folder: Path, *extra: str) -> Path:
    """Write folder/fpm.env with SOURCE_ROOT, DEST_ROOT and the extra lines; return its path."""
    env = folder / "fpm.env"
    lines = ["SOURCE_ROOT=C:/checkout", "DEST_ROOT=C:/releases", *extra]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env


def test_help_root_gets_the_release_folder(tmp_path):
    paths = _load_paths(_env(tmp_path, f"HELP_ROOT={_HELP_ROOT}"), _VERSION)
    assert paths.help_root == Path(_HELP_ROOT) / _generate_project_version_folder_name("fpm", _VERSION)
    assert paths.help_root.name == paths.dest_root.name


def test_help_root_absent_is_none(tmp_path):
    assert _load_paths(_env(tmp_path), _VERSION).help_root is None


def test_empty_help_root_is_none(tmp_path):
    assert _load_paths(_env(tmp_path, "HELP_ROOT="), _VERSION).help_root is None


def test_two_field_construction_keeps_working():
    assert ProjectPaths(Path("checkout"), Path("releases")).help_root is None


def test_load_project_reads_help_root(tmp_path):
    (tmp_path / "fpm.json").write_text('{"folders": []}', encoding="utf-8")
    _env(tmp_path, f'HELP_ROOT="{_HELP_ROOT}"')
    _, paths = load_project("fpm", _VERSION, project_def_dir=tmp_path)
    assert paths.help_root == Path(_HELP_ROOT) / paths.dest_root.name


def test_fpm_env_shows_help_root_as_a_comment():
    env = _PROJECT_DEF_DIR / "fpm.env"
    lines = env.read_text(encoding="utf-8").splitlines()
    example = [n for n, line in enumerate(lines) if line.startswith("# HELP_ROOT=//")]
    assert len(example) == 1, lines
    assert lines[example[0] - 1].startswith("#"), "a comment line states the example's purpose"
    assert "HELP_ROOT" not in _parse_env(env)
