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


@pytest.mark.parametrize("name", [
    "spectrum.vsz", "hatching.vsz", "contour_labels.vsz", "example_import.vsz",
    "profile.vsz", "1dto2d.vsz", "mathml.vsz", "3d_errors.vsz",
    "3d_function.vsz", "3d_points.vsz", "3d_surface.vsz", "3d_volume.vsz",
])
def test_formerly_excluded_graphics_fail_on_changed_output(
        runner, tmp_path, monkeypatch, capsys, name):
    comparison = tmp_path / "comparison"
    comparison.mkdir()
    (comparison / (name + ".selftest")).write_text("expected", encoding="utf-8")
    monkeypatch.setattr(runner, "Dirs", lambda: SimpleNamespace(
        thisdir=str(tmp_path), infiles=[str(tmp_path / name)]))
    monkeypatch.setattr(runner, "renderVszTest",
                        lambda source, output, **kwargs:
                        Path(output).write_text("changed", encoding="utf-8"))
    with pytest.raises(SystemExit) as error:
        runner.runTests()
    assert error.value.code == 1
    assert "FAIL: results differed" in capsys.readouterr().out
    assert (tmp_path / (name + ".temp.selftest")).is_file()


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


def test_contour_labels_use_the_same_device_metrics_as_their_text(
        runner, tmp_path, monkeypatch):
    monkeypatch.setitem(runner.setting.transient_settings, "unsafe_mode", True)
    monkeypatch.setattr(runner.utils, "FontMetrics", runner.StupidFontMetrics)
    monkeypatch.setattr(
        runner.utils.textrender, "FontMetrics", runner.StupidFontMetrics)
    monkeypatch.setattr(runner.utils.textrender, "PartText", runner.PartTextAscii)
    monkeypatch.setattr(runner.svg_export, "fltStr", runner.fltStr)
    source = Path(__file__).resolve().parents[1] / "examples/contour_labels.vsz"
    expected = tmp_path / "expected.selftest"
    actual = tmp_path / "actual.selftest"
    runner.renderVszTest(str(source), str(expected))

    def unexpected_native_metrics(*args):
        raise AssertionError("Contour label padding bypassed device font metrics")

    monkeypatch.setattr(runner.qt, "QFontMetricsF", unexpected_native_metrics)
    runner.renderVszTest(str(source), str(actual))
    assert actual.read_bytes() == expected.read_bytes()
