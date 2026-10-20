"""The graphical gate must report every failure and retain visual differences."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def runner(qapp):
    spec = importlib.util.spec_from_file_location(
        "plotex_selftest", Path(__file__).with_name("runselftest.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_graphical_runner_continues_after_render_and_baseline_failures(
        runner, tmp_path, monkeypatch, capsys):
    sources = [tmp_path / name for name in ("a.vsz", "b.vsz", "c.vsz")]
    comparison = tmp_path / "comparison"
    comparison.mkdir()
    (comparison / "c.vsz.selftest").write_text("valid output", encoding="utf-8")
    monkeypatch.setattr(runner, "Dirs", lambda: SimpleNamespace(
        thisdir=str(tmp_path), infiles=list(map(str, sources))))
    rendered = []

    def render(source, output, **kwargs):
        rendered.append(Path(source).name)
        if Path(source).name == "a.vsz":
            raise ValueError("broken input")
        Path(output).write_text("valid output", encoding="utf-8")

    monkeypatch.setattr(runner, "renderVszTest", render)
    with pytest.raises(SystemExit) as error:
        runner.runTests()
    assert error.value.code == 2
    assert rendered == ["a.vsz", "b.vsz", "c.vsz"]
    output = capsys.readouterr().out
    assert "missing comparison file" in output
    assert "2/3 tests FAILED" in output
    assert " PASS" in output


def test_comparison_only_normalizes_application_metadata(runner):
    old = '<desc>Veusz output document</desc><path d="m1,2l3,4"/>'
    new = old.replace("Veusz", "Plotex")
    assert runner.comparisonText(old) == runner.comparisonText(new)
    assert runner.comparisonText(old) != runner.comparisonText(
        new.replace("l3,4", "l4,4"))


def test_embedded_graphical_test_has_execution_timeout(runner, monkeypatch):
    calls = []
    monkeypatch.setattr(runner.subprocess, "call",
                        lambda args, **kwargs: calls.append((args, kwargs)) or 0)
    assert runner.renderPyTest("example.py", "output.selftest")
    assert calls == [([runner.sys.executable, "example.py", "output.selftest"],
                      {"timeout": 60})]


def test_save_roundtrip_keeps_document_filename_labels(runner, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "named.vsz"
    source.write_text(
        "Add('page', name='page')\nTo('page')\n"
        "Add('label', name='label')\nTo('label')\n"
        "Set('label', '%{{ BASENAME() }}%')\n", encoding="utf-8")
    output = tmp_path / "output.selftest"
    runner.renderVszTest(str(source), str(output), test_saves=True)
    text = output.read_text(encoding="utf-8")
    assert "named.vsz" in text
    assert "self-test-temporary" not in text
