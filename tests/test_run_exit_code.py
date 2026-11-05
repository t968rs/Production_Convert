"""Tests that run.py reports copy failures through its exit code."""
import runpy
from pathlib import Path

import pytest

import conversion.prod_deploy as prod_deploy
from conversion.prod_deploy import CopyResult

RUN_PY = Path(__file__).resolve().parents[1] / "conversion" / "run.py"


class _FakeCopier:
    result = CopyResult((), (), (), ())

    def __init__(self, *args, **kwargs):
        pass

    def run(self):
        return self.result


@pytest.fixture
def fake_copy(monkeypatch):
    monkeypatch.setattr("sys.argv", [str(RUN_PY)])
    monkeypatch.setattr("builtins.input", lambda prompt="": "v0.0.0-test")
    monkeypatch.setattr(prod_deploy, "load_project", lambda name, version: ("cfg", "paths"))
    monkeypatch.setattr(prod_deploy, "ProdCopier", _FakeCopier)
    return _FakeCopier


def test_failed_copy_exits_1(fake_copy, capsys):
    fake_copy.result = CopyResult((), (), (), ("copy failed a -> b",))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(RUN_PY), run_name="__main__")
    assert exc.value.code == 1
    assert "copy failed a -> b" in capsys.readouterr().out


def test_successful_copy_exits_0(fake_copy):
    fake_copy.result = CopyResult((), (), (), ())
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(RUN_PY), run_name="__main__")
    assert exc.value.code == 0
