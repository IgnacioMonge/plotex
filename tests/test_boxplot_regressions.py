"""Keep outlier visibility independent of the optional strip plot."""

import numpy as N
import pytest


@pytest.fixture
def boxplot():
    from veusz import datasets, document

    doc = document.Document()
    page = doc.applyOperation(document.OperationWidgetAdd(doc.basewidget, "page"))
    graph = doc.applyOperation(document.OperationWidgetAdd(page, "graph"))
    widget = doc.applyOperation(document.OperationWidgetAdd(graph, "boxplot"))
    doc.setData("sample", datasets.Dataset([1., 2., 2., 3., 100.]))
    widget.settings.values = ("sample",)
    widget.settings.pointsMarker = "square"
    widget.settings.outliersmarker = "diamond"
    return widget


def test_outlier_controls_are_available_without_individual_points(boxplot):
    settings = boxplot.settings
    assert settings.showOutliers is True
    assert settings.showPoints is False
    controlled = settings.get("showPoints").strue
    assert "showOutliers" not in controlled
    assert "outliersmarker" not in controlled


@pytest.mark.parametrize("show_points", [False, True])
@pytest.mark.parametrize("show_outliers", [None, False, True])
def test_render_outliers_respects_own_option(
        boxplot, tmp_path, monkeypatch, show_points, show_outliers):
    from veusz import document
    from veusz.widgets import boxplot as boxplot_module

    boxplot.settings.showPoints = show_points
    if show_outliers is not None:
        boxplot.settings.showOutliers = show_outliers
    calls = []
    original = boxplot_module.utils.plotMarkers

    def record_markers(painter, x, y, marker, size, *args, **kwargs):
        calls.append((marker, N.asarray(x).copy(), N.asarray(y).copy()))
        return original(painter, x, y, marker, size, *args, **kwargs)

    monkeypatch.setattr(boxplot_module.utils, "plotMarkers", record_markers)
    output = tmp_path / "boxplot.selftest"
    document.CommandInterface(boxplot.document).Export(str(output))
    assert output.stat().st_size > 0
    outliers = [call for call in calls if call[0] == "diamond"]
    points = [call for call in calls if call[0] == "square"]
    assert len(outliers) == (show_outliers is not False)
    if outliers:
        assert len(outliers[0][1]) == 1
        assert N.isfinite(outliers[0][1]).all()
        assert N.isfinite(outliers[0][2]).all()
    assert len(points) == show_points
    if points:
        assert len(points[0][1]) == 5
