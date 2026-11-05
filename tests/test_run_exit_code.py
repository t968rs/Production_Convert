"""Tests that run.py reports copy failures through its exit code."""
import runpy
import sys
from pathlib import Path

import pytest

import conversion.prod_deploy as prod_deploy
from conversion.prod_deploy import CopyResult

RUN_PY = Path(__file__).resolve().parents[1] / "conversion" / "run.py"


class _FakeCopier:
    result = CopyResult((), (), (), ())
    load_calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    def run(self):
        return self.result


@pytest.fixture
def fake_copy(monkeypatch):
    """Patch run.py's collaborators with a fresh per-test copier class."""
    copier = type(
        "Copier",
        (_FakeCopier,),
        {"result": CopyResult((), (), (), ()), "load_calls": []},
    )

    def _fake_load_project(name, version):
        copier.load_calls.append((name, version))
        return "cfg", "paths"

    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr("sys.argv", [str(RUN_PY)])
    monkeypatch.setattr("builtins.input", lambda prompt="": "v0.0.0-test")
    monkeypatch.setattr(prod_deploy, "load_project", _fake_load_project)
    monkeypatch.setattr(prod_deploy, "ProdCopier", copier)
    return copier


def _run_main() -> int:
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(RUN_PY), run_name="__main__")
    return exc.value.code


def test_failed_copy_exits_1(fake_copy, capsys):
    fake_copy.result = CopyResult((), (), (), ("copy failed a -> b",))
    assert _run_main() == 1
    assert "copy failed a -> b" in capsys.readouterr().err


def test_successful_copy_exits_0(fake_copy):
    assert _run_main() == 0


def test_cli_version_reaches_load_project(fake_copy, monkeypatch):
    def _no_input(prompt=""):
        raise AssertionError("input() must not be called when a version is given")

    monkeypatch.setattr("sys.argv", [str(RUN_PY), "v1.2.3"])
    monkeypatch.setattr("builtins.input", _no_input)
    assert _run_main() == 0
    assert fake_copy.load_calls == [("fpm", "v1.2.3")]


def test_prompted_version_reaches_load_project(fake_copy):
    assert _run_main() == 0
    assert fake_copy.load_calls == [("fpm", "v0.0.0-test")]
