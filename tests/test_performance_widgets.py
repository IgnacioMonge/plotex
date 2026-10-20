"""Numerical and render equivalence for the bounded performance changes."""

import threading
import types

import numpy as N
import pytest


@pytest.fixture
def make_widget():
    from veusz import datasets, document

    def make(typename, dataset_values, **settings):
        doc = document.Document()
        page = doc.applyOperation(document.OperationWidgetAdd(doc.basewidget, "page"))
        graph = doc.applyOperation(document.OperationWidgetAdd(page, "graph"))
        result = doc.applyOperation(document.OperationWidgetAdd(graph, typename))
        values = N.asarray(dataset_values, dtype=float)
        dataset = datasets.Dataset2D(values) if values.ndim == 2 else datasets.Dataset(values)
        doc.setData("sample", dataset)
        for name, value in settings.items():
            result.settings.get(name).set(value)
        return result

    return make


def _legacy_kde(data, grid, bw, gaussian):
    if len(data) == 0 or bw <= 0:
        return N.zeros_like(grid)
    u = (grid[:, None] - data[None, :]) / bw
    if gaussian:
        return N.exp(-.5 * u * u).sum(axis=1) / (len(data) * bw * N.sqrt(2 * N.pi))
    return N.where(N.abs(u) <= 1, .75 * (1 - u * u), 0.).sum(axis=1) / (len(data) * bw)


@pytest.mark.parametrize("gaussian", [False, True])
@pytest.mark.parametrize("n", [0, 1, 8, 4095, 4096, 4103])
def test_kde_preserves_dense_formula_across_block_boundary(gaussian, n):
    from veusz.widgets import violin

    data = N.random.default_rng(21).normal(size=n)
    grid = N.linspace(-4, 4, 11)
    function = violin._kde_gaussian if gaussian else violin._kde_epanechnikov
    N.testing.assert_allclose(function(data, grid, bw=.31),
                             _legacy_kde(data, grid, .31, gaussian),
                             rtol=5e-13, atol=1e-15)
    N.testing.assert_array_equal(function(data, grid, bw=0), N.zeros_like(grid))


@pytest.mark.parametrize("kernel", ["gaussian", "epanechnikov"])
@pytest.mark.parametrize("span", ["soft", "hard"])
@pytest.mark.parametrize("scaling", ["area", "count", "width"])
@pytest.mark.parametrize("common", [False, True])
def test_violin_preserves_grids_bandwidth_and_normalization(
        make_widget, monkeypatch, kernel, span, scaling, common):
    from veusz.widgets import violin

    plot = make_widget("violin", [1., 2.], values=("sample",), kernel=kernel,
                       spanMode=span, scaling=scaling, commonNorm=common)
    stats = []
    for data in (N.array([1., 1., 1.]), N.random.default_rng(7).normal(size=31)):
        item = violin._ViolinStats()
        item.calculate(data)
        stats.append(item)
    actual = [plot._computeKDE(item, plot.settings) for item in stats]
    actual_scales = plot._scaleViolins([d for _, d in actual], stats,
                                      [g for g, _ in actual], plot.settings)
    monkeypatch.setitem(violin._KDE_FUNCS, kernel,
                        lambda data, grid, bw: _legacy_kde(data, grid, bw,
                                                          kernel == "gaussian"))
    expected = [plot._computeKDE(item, plot.settings) for item in stats]
    expected_scales = plot._scaleViolins([d for _, d in expected], stats,
                                        [g for g, _ in expected], plot.settings)
    for (grid, density), (old_grid, old_density) in zip(actual, expected):
        N.testing.assert_array_equal(grid, old_grid)
        N.testing.assert_allclose(density, old_density, rtol=5e-13, atol=1e-15)
    N.testing.assert_allclose(actual_scales, expected_scales, rtol=5e-13, atol=1e-15)


@pytest.mark.parametrize("data", [[], [1.], [2.] * 8, [0., 1., 2., N.nan, N.inf]])
@pytest.mark.parametrize("bandwidth", [0., .7])
def test_ridgeline_preserves_bandwidth_and_per_sample_formula(data, bandwidth):
    from veusz.widgets.ridgeline import _kde

    grid = N.linspace(-3, 4, 13)
    source = N.asarray(data)
    cleaned = source[N.isfinite(source)]
    expected = N.zeros_like(grid)
    if len(cleaned) >= 2:
        h = bandwidth
        if h <= 0:
            std = N.std(cleaned, ddof=1)
            iqr = N.percentile(cleaned, 75) - N.percentile(cleaned, 25)
            h = .9 * min(std, iqr / 1.34) * len(cleaned) ** (-.2)
            if h < 1e-15:
                h = std if std > 1e-15 else 1.
        for value in cleaned:
            expected += N.exp(-.5 * ((grid - value) / h) ** 2)
        expected /= len(cleaned) * h * N.sqrt(2 * N.pi)
    N.testing.assert_allclose(_kde(source, grid, bandwidth), expected,
                             rtol=5e-13, atol=1e-15)


def _legacy_km(times, events):
    mask = N.isfinite(times) & N.isfinite(events)
    t, e = times[mask], events[mask].astype(N.int32)
    order = N.argsort(t, kind="stable")
    t, e = t[order], e[order]
    km_times, km_surv, greenwood = [0.], [1.], [0.]
    risk_times, risk = [], []
    survival, total = 1., 0.
    for time in N.unique(t[e == 1]):
        n = int(N.sum(t >= time))
        d = int(N.sum((t == time) & (e == 1)))
        if n <= 0:
            continue
        risk_times.append(time)
        risk.append(n)
        survival *= 1. - d / n
        if n > d:
            total += d / (n * (n - d))
        km_times.append(float(time))
        km_surv.append(survival)
        greenwood.append(total)
    times = N.array(km_times)
    surv = N.array(km_surv)
    variance = N.maximum(surv * surv * N.array(greenwood), 0.)
    censored = t[e == 0]
    censor_surv = []
    for time in censored:
        index = N.searchsorted(times, time, side="right") - 1
        index = max(0, min(index, len(surv) - 1))
        censor_surv.append(float(surv[index]))
    return dict(times=times, survival=surv, variance=variance,
                ci_lower=N.clip(surv - 1.96 * N.sqrt(variance), 0., 1.),
                ci_upper=N.clip(surv + 1.96 * N.sqrt(variance), 0., 1.),
                censor_times=censored, censor_surv=N.array(censor_surv),
                n_at_risk_times=N.array(risk_times),
                n_at_risk=N.array(risk, dtype=N.int32 if len(t) else float))


@pytest.mark.parametrize("times,events", [
    ([], []), ([1., 2., 3.], [0., 0., 0.]), ([2., 2.], [1., 1.]),
    ([0., 1., 1., 2., 3.], [1., 1., 0., 1., 0.]),
    ([-3., -2., -1., 1.], [1., 0., 1., 0.]),
    ([1., N.nan, 2., 2., N.inf, 3.], [0., 1., 1., 0., 1., 2.7]),
    (N.random.default_rng(91).integers(0, 12, 64),
     N.random.default_rng(18).integers(0, 2, 64)),
])
def test_kaplan_meier_preserves_every_result_field(times, events):
    from veusz.widgets.kaplanmeier import KaplanMeier

    times, events = N.asarray(times, dtype=float), N.asarray(events, dtype=float)
    expected = _legacy_km(times, events)
    actual = KaplanMeier._computeKM(times, events)
    for name, values in expected.items():
        N.testing.assert_array_equal(getattr(actual, name), values, err_msg=name)
        assert getattr(actual, name).dtype == values.dtype
    assert not hasattr(actual, "label")


def test_qq_reuses_result_for_ranges_and_drawing(make_widget, monkeypatch):
    plot = make_widget("qqplot", [1., 3., 2., N.nan], data="sample")
    original = plot._computeQuantiles
    calls = []
    def compute():
        calls.append(1)
        return original()
    monkeypatch.setattr(plot, "_computeQuantiles", compute)
    plot.getRange(None, "sx", [N.inf, -N.inf])
    plot.getRange(None, "sy", [N.inf, -N.inf])
    actual = plot._compute()
    assert len(calls) == 1
    expected = original()
    for value, old_value in zip(actual, expected):
        N.testing.assert_array_equal(value, old_value)
    assert plot._compute() is actual


@pytest.mark.parametrize("setting,value", [("data", [9., 7., 5.]),
                                           ("distribution", "t"), ("dfparam", 2.)])
def test_qq_invalidates_on_configuration_without_changeset(make_widget, setting, value):
    plot = make_widget("qqplot", [1., 2., 3.], data="sample")
    previous = plot._compute()
    plot.settings.get(setting).set(value)
    actual = plot._compute()
    assert actual is not previous
    for result, expected in zip(actual, plot._computeQuantiles()):
        N.testing.assert_array_equal(result, expected)


def test_qq_invalidates_cached_missing_dataset(make_widget):
    from veusz import datasets

    plot = make_widget("qqplot", [1., 2.], data="future")
    assert plot._compute() == (None, None)
    plot.document.setData("future", datasets.Dataset([7., 8., 9.]))
    N.testing.assert_array_equal(plot._compute()[1], [7., 8., 9.])


def test_qq_publishes_only_complete_cache_after_data_change(make_widget, monkeypatch):
    from veusz import datasets, qtall as qt

    plot = make_widget("qqplot", [1., 2., 3.], data="sample")
    plot._compute()
    previous = plot._quantile_cache
    plot.document.setData("sample", datasets.Dataset([7., 8., 9.]))
    entered, release = threading.Event(), threading.Event()
    original = plot._computeQuantiles
    results = []
    def delayed():
        entered.set()
        assert release.wait(5)
        return original()
    monkeypatch.setattr(plot, "_computeQuantiles", delayed)
    def reader():
        locker = qt.QReadLocker(plot.document._render_lock)
        try:
            results.append(plot._compute())
        finally:
            del locker
    thread = threading.Thread(target=reader)
    thread.start()
    try:
        assert entered.wait(5)
        assert plot._quantile_cache is previous
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(results) == 1
    assert plot._quantile_cache[0][0] == plot.document.changeset
    assert plot._quantile_cache[1] is results[0]
    N.testing.assert_array_equal(results[0][1], [7., 8., 9.])


def _legacy_heatmap_draw(self, painter, axes, posn, clip):
    """Original per-cell renderer, kept as the pixel-equivalence reference."""
    from veusz import qtall as qt
    from veusz.utils.colormap import getColormapArray

    s = self.settings
    data = s.get('data').getData(self.document).data
    finite = data[N.isfinite(data)]
    if len(finite) == 0:
        return
    vmin = float(N.min(finite)) if s.min == 'Auto' else s.min
    vmax = float(N.max(finite)) if s.max == 'Auto' else s.max
    if vmin == vmax:
        vmax = vmin + 1
    rgba = getColormapArray(self.document.evaluate.getColormap(s.colorMap, s.colorInvert), 256)
    borderpen = s.CellBorder.makeQPenWHide(painter)
    painter.setFont(s.get('ValueLabel').makeQFont(painter))
    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            value = data[row, col]
            if not N.isfinite(value):
                continue
            x0 = axes[0].dataToPlotterCoords(posn, N.array([float(col)]))[0]
            x1 = axes[0].dataToPlotterCoords(posn, N.array([float(col + 1)]))[0]
            y0 = axes[1].dataToPlotterCoords(posn, N.array([float(row)]))[0]
            y1 = axes[1].dataToPlotterCoords(posn, N.array([float(row + 1)]))[0]
            ci = int(max(0., min(1., (value - vmin) / (vmax - vmin))) * 255)
            color = qt.QColor(int(rgba[ci][0]), int(rgba[ci][1]), int(rgba[ci][2]),
                              int(rgba[ci][3] * (100 - s.transparency) / 100.))
            rect = qt.QRectF(qt.QPointF(min(x0, x1), min(y0, y1)),
                             qt.QPointF(max(x0, x1), max(y0, y1)))
            painter.setBrush(qt.QBrush(color))
            painter.setPen(borderpen)
            painter.drawRect(rect)
            if s.showValues:
                try:
                    text = s.valueFormat % value
                except (TypeError, ValueError):
                    text = str(value)
                lum = color.redF() * .299 + color.greenF() * .587 + color.blueF() * .114
                painter.setPen(qt.QPen(qt.QColor(255, 255, 255) if lum < .5 else qt.QColor(0, 0, 0)))
                painter.drawText(rect, int(qt.Qt.AlignmentFlag.AlignCenter), text)


def _export_pixels(plot, filename):
    from veusz import document, qtall as qt

    document.CommandInterface(plot.document).Export(str(filename))
    image = qt.QImage(str(filename))
    return image.bits().asstring(image.sizeInBytes())


@pytest.mark.parametrize("show_values", [False, True])
@pytest.mark.parametrize("mode", ["linear", "zoom", "reverse", "log", "cosmetic"])
def test_heatmap_pixels_match_per_cell_renderer(make_widget, tmp_path, show_values, mode):
    data = N.arange(24, dtype=float).reshape(4, 6)
    data[0, 0], data[1, 1] = N.nan, N.inf
    plot = make_widget("heatmap", data, data="sample", showValues=show_values,
                       colorInvert=True, transparency=25)
    xaxis, yaxis = plot.parent.getAxes(("x", "y"))
    if mode == "zoom":
        xaxis.settings.min, xaxis.settings.max = 1.25, 2.75
        yaxis.settings.min, yaxis.settings.max = .75, 2.25
    elif mode == "reverse":
        xaxis.settings.min, xaxis.settings.max = 5.5, .5
        yaxis.settings.min, yaxis.settings.max = 3.5, .5
    elif mode == "log":
        xaxis.settings.log = True
        xaxis.settings.min, xaxis.settings.max = .25, 6.
    elif mode == "cosmetic":
        plot.settings.CellBorder.width = "0pt"
    actual = _export_pixels(plot, tmp_path / "new.png")
    plot.dataDraw = types.MethodType(_legacy_heatmap_draw, plot)
    expected = _export_pixels(plot, tmp_path / "old.png")
    assert actual == expected


def test_heatmap_zoom_converts_edges_once_and_skips_invisible_cells(make_widget, tmp_path):
    plot = make_widget("heatmap", N.arange(1600.).reshape(40, 40),
                       data="sample", showValues=False)
    for axis in plot.parent.getAxes(("x", "y")):
        axis.settings.min, axis.settings.max = 0., 2.
    original = plot.dataDraw
    counts = {"transforms": 0, "rectangles": 0}
    class Axis:
        def __init__(self, actual):
            self.actual = actual
        def dataToPlotterCoords(self, posn, data):
            counts["transforms"] += 1
            return self.actual.dataToPlotterCoords(posn, data)
    class Painter:
        def __init__(self, actual):
            self.actual = actual
        def __getattr__(self, name):
            return getattr(self.actual, name)
        def drawRect(self, rect):
            counts["rectangles"] += 1
            return self.actual.drawRect(rect)
    def draw(painter, axes, posn, clip):
        return original(Painter(painter), [Axis(axis) for axis in axes], posn, clip)
    plot.dataDraw = draw
    _export_pixels(plot, tmp_path / "zoom.png")
    assert counts["transforms"] == 2
    assert 0 < counts["rectangles"] < 20
