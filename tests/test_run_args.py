"""Tests for run.py command-line parsing and the interactive version fallback."""
import pytest

from conversion import run


@pytest.mark.parametrize(
    "argv",
    [
        ["v3.17.2"],
        ["-v", "v3.17.2"],
        ["-vv3.17.2"],
        ["--version", "v3.17.2"],
        ["--version=v3.17.2"],
        ["--target-version", "v3.17.2"],
        ["--target_version", "v3.17.2"],
        ["--", "v3.17.2"],
    ],
)
def test_version_forms(argv):
    assert run._resolve_version(run._get_args(argv)) == "v3.17.2"


def test_same_value_twice_is_accepted():
    assert run._resolve_version(run._get_args(["v3.17.2", "-v", "v3.17.2"])) == "v3.17.2"


def test_conflicting_values_exit_2():
    with pytest.raises(SystemExit) as exc:
        run._resolve_version(run._get_args(["v3.17.2", "--version", "v3.17.3"]))
    assert exc.value.code == 2


def test_unknown_flag_exits_2():
    with pytest.raises(SystemExit) as exc:
        run._get_args(["--bogus"])
    assert exc.value.code == 2


def test_no_version_falls_back_to_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "  v3.17.2  ")
    assert run._resolve_version(run._get_args([])) == "v3.17.2"


def test_empty_input_exits_2(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    with pytest.raises(SystemExit) as exc:
        run._resolve_version(run._get_args([]))
    assert exc.value.code == 2


def test_target_version_constant_removed():
    assert not hasattr(run, "TARGET_VERSION")
