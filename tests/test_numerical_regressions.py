"""Regression cases for scientific calculations, using the real widgets."""

import io

import numpy as N
import pytest


@pytest.fixture
def make_widget():
    from veusz import datasets, document

    def make(typename, data, **settings):
        doc = document.Document()
        page = doc.applyOperation(document.OperationWidgetAdd(doc.basewidget, "page"))
        graph = doc.applyOperation(document.OperationWidgetAdd(page, "graph"))
        widget = doc.applyOperation(document.OperationWidgetAdd(graph, typename))
        for name, values in data.items():
            doc.setData(name, datasets.Dataset(values))
        for name, value in settings.items():
            widget.settings.get(name).set(value)
        return widget

    return make


@pytest.mark.parametrize("truth,scores,expected", [
    ([0, 1], [2., 1.], 0.),
    ([0, 1, 0, 1], [4., 3., 2., 1.], .25),
    ([1, 0], [1., 1.], .5),
    ([0, 1], [1., 1.], .5),
    ([0, 0, 1, 1], [.1, .2, .8, .9], 1.),
])
def test_roc_auc_at_actual_score_thresholds(truth, scores, expected):
    from veusz.widgets.roccurve import ROCCurve

    fpr, tpr, auc, _, _, _ = ROCCurve._computeROC(
        None, N.array(truth), N.array(scores))
    assert auc == pytest.approx(expected)
    assert (fpr[0], tpr[0]) == (0., 0.)
    assert (fpr[-1], tpr[-1]) == (1., 1.)


def test_roc_youden_point_matches_cutoff():
    from veusz.widgets.roccurve import ROCCurve

    fpr, tpr, _, _, index, cutoff = ROCCurve._computeROC(
        None, N.array([0, 0, 1, 1]), N.array([.1, .2, .8, .9]))
    assert cutoff == .8
    assert (fpr[index], tpr[index]) == (0., 1.)


@pytest.mark.parametrize("test,reference,angle,concordance", [
    ([1., 2.], [1., 2.], 0., 100.),
    ([-1., -2.], [-1., -2.], 0., 100.),
    ([1., 2.], [2., 4.], -18.434948822922, 100.),
    ([-1., -2.], [-2., -4.], -18.434948822922, 100.),
    ([-1., -2.], [1., 2.], -90., 0.),
    ([1., 2.], [-1., -2.], -90., 0.),
])
def test_polar_rises_and_falls_share_agreement_direction(
        make_widget, test, reference, angle, concordance):
    widget = make_widget(
        "polartrending", {"test": test, "reference": reference},
        deltaTestData="test", deltaRefData="reference", exclusionZone=0.)
    widget._computePolar()
    N.testing.assert_allclose(widget._agreement_angle, angle, atol=1e-10)
    assert widget._angular_bias == pytest.approx(angle, abs=1e-10)
    assert widget._concordance_rate == concordance


@pytest.fixture
def make_fit(make_widget, monkeypatch):
    from veusz.widgets import fit

    monkeypatch.setattr(fit, "minuit", None)

    def make(x, y, **settings):
        return make_widget("fit", {"xx": x, "yy": y},
                           xData="xx", yData="yy", **settings)

    return make


def test_relative_errors_weight_negative_values_by_magnitude(make_fit):
    widget = make_fit([0., 1., 2.], [-10., -20., 30.],
                      function="a", values={"a": 0.},
                      defErrType="relative", defErr=.1)
    widget.actionFit()
    assert widget.settings.dof == 2
    assert widget.settings.values["a"] == pytest.approx(-60. / 7.)


@pytest.mark.parametrize("chi2", [-1., 0., 1.])
def test_fit_draws_saved_parameters_without_bands(make_fit, monkeypatch, chi2):
    from veusz.widgets.function import FunctionPlotter

    widget = make_fit([0., 1.], [1., 3.], values={"a": 1., "b": 2.})
    widget.settings.chi2 = chi2
    drawn = []
    monkeypatch.setattr(FunctionPlotter, "dataDraw",
                        lambda self, *args: drawn.append(self.settings.values))
    widget.dataDraw(None, None, None, None)
    assert drawn == [{"a": 1., "b": 2.}]


@pytest.mark.parametrize("backend", ["_fitScipy", "_fitLMFallback"])
@pytest.mark.parametrize("npoints", [2, 3])
def test_fit_backends_return_actual_residual_degrees_of_freedom(backend, npoints):
    from veusz.utils import fitlm

    x = N.arange(npoints, dtype=float)
    kwargs = {"maxiters": 200, "log": io.StringIO()}
    if backend == "_fitLMFallback":
        kwargs.update(stopdeltalambda=1e-5, deltaderiv=1e-5, Lambda=1e-4)
    result = getattr(fitlm, backend)(
        lambda p, xv: p[0] + p[1] * xv, N.array([0., 1.]),
        x, 1. + 2. * x, N.ones(npoints), **kwargs)
    N.testing.assert_allclose(result[0], [1., 2.], atol=1e-4)
    assert result[2] == npoints - 2


def test_exactly_determined_fit_does_not_publish_residual_bands(make_fit):
    from veusz import document
    from veusz.document.loader import executeScript

    widget = make_fit([0., 1.], [1., 3.])
    for name in ("bandXData", "bandConfUpper", "bandConfLower",
                 "bandPredUpper", "bandPredLower"):
        widget.settings.get(name).set([1.])
    widget.actionFit()
    assert widget.settings.dof == 0
    buf = io.StringIO()
    widget.document.serializeToText(buf)
    restored_doc = document.Document()
    executeScript(restored_doc, "numerical-roundtrip", buf.getvalue())
    restored = restored_doc.resolveWidgetPath(None, widget.path)
    for fitted in (widget, restored):
        assert fitted.settings.bandResidVar == -1.
        for name in ("bandXData", "bandConfUpper", "bandConfLower",
                     "bandPredUpper", "bandPredLower"):
            assert fitted.settings.get(name).get() == []


def test_fit_rechecks_data_count_after_removing_nonfinite_values(make_fit, capsys):
    widget = make_fit([0., 1., 2.], [1., N.nan, N.nan])
    original = widget.settings.values.copy()
    widget.actionFit()
    assert widget.settings.values == original
    assert widget.settings.dof == -1
    assert "No degrees of freedom" in capsys.readouterr().err


@pytest.mark.parametrize("variable", ["x", "y"])
@pytest.mark.parametrize("range_source", ["limits", "axis"])
def test_fit_range_uses_independent_variable(make_fit, monkeypatch,
                                             variable, range_source):
    independent = [0., 1., 2., 3., 4.]
    dependent = [1., 3., 5., 100., 100.]
    x, y = ((independent, dependent) if variable == "x"
            else (dependent, independent))
    widget = make_fit(x, y, variable=variable, function="a+b*" + variable)
    if range_source == "limits":
        widget.settings.fitMin = 0.
        widget.settings.fitMax = 2.
    else:
        widget.settings.fitRange = True
        axis = widget.parent.getAxes((variable,))[0]
        monkeypatch.setattr(axis, "getPlottedRange", lambda: (0., 2.))
    widget.actionFit()
    assert widget.settings.dof == 1
    assert widget.settings.values == pytest.approx({"a": 1., "b": 2.})
