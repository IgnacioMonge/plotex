"""Ridgeline plot widget — stacked KDE density distributions."""

import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from .plotters import GenericPlotter


def _(text, disambiguation=None, context="Ridgeline"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


def _kde(data, grid, bandwidth):
    """Simple Gaussian KDE evaluation on a grid."""
    data = data[N.isfinite(data)]
    if len(data) < 2:
        return N.zeros_like(grid)
    if bandwidth <= 0:
        # Silverman's rule
        std = N.std(data, ddof=1)
        iqr = N.percentile(data, 75) - N.percentile(data, 25)
        h = 0.9 * min(std, iqr / 1.34) * len(data) ** (-0.2)
        if h < 1e-15:
            h = std if std > 1e-15 else 1.0
    else:
        h = bandwidth
    result = N.zeros_like(grid, dtype=float)
    for x in data:
        result += N.exp(-0.5 * ((grid - x) / h) ** 2)
    result /= len(data) * h * N.sqrt(2 * N.pi)
    return result


class _RidgeFill(setting.Brush):
    """Fill for ridgeline areas."""

    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)
        self.get("transparency").newDefault(30)


class Ridgeline(GenericPlotter):
    """Ridgeline plot: stacked KDE distributions with partial overlap."""

    typename = "ridgeline"
    allowusercreation = True
    description = _("Ridgeline plot (stacked densities)")

    @classmethod
    def addSettings(klass, s):
        GenericPlotter.addSettings(s)
        s.remove("key")

        s.add(
            setting.Datasets(
                "data",
                ("data",),
                descr=_("Datasets to plot (one ridge per dataset)"),
                usertext=_("Data"),
            ),
            0,
        )

        s.add(
            setting.Int(
                "gridPoints",
                128,
                minval=32,
                maxval=1024,
                descr=_("Number of evaluation points for KDE"),
                usertext=_("Grid points"),
            ),
            1,
        )
        s.add(
            setting.Float(
                "bandwidth",
                0.0,
                minval=0.0,
                descr=_("KDE bandwidth (0 = auto Silverman)"),
                usertext=_("Bandwidth"),
            ),
            2,
        )
        s.add(
            setting.Float(
                "overlap",
                0.6,
                minval=0.0,
                maxval=2.0,
                descr=_("Vertical overlap between ridges (0=none, 1=full)"),
                usertext=_("Overlap"),
            ),
            3,
        )
        s.add(
            setting.Bool(
                "filled", True, descr=_("Fill the ridge areas"), usertext=_("Filled")
            ),
            4,
        )
        s.add(
            setting.Bool(
                "autoColor",
                True,
                descr=_("Automatically vary colors per ridge"),
                usertext=_("Auto color"),
            ),
            5,
        )

        s.add(
            _RidgeFill("Fill", descr=_("Ridge fill"), usertext=_("Fill")),
            pixmap="settings_bgfill",
        )
        s.add(
            setting.Line("Line", descr=_("Ridge outline"), usertext=_("Line")),
            pixmap="settings_plotline",
        )

    @property
    def userdescription(self):
        s = self.settings
        dnames = s.get("data").getData(self.document)
        if dnames:
            return "%d ridges" % len(dnames)
        return "no data"

    def _getDatasets(self):
        """Return list of numpy arrays, one per ridge."""
        s = self.settings
        doc = self.document
        datasets = s.get("data").getData(doc)
        if not datasets:
            return []
        result = []
        for ds in datasets:
            if ds is not None and hasattr(ds, "data"):
                arr = N.array(ds.data, dtype=float)
                arr = arr[N.isfinite(arr)]
                if len(arr) >= 2:
                    result.append(arr)
        return result

    def affectsAxisRange(self):
        s = self.settings
        return ((s.xAxis, "sx"), (s.yAxis, "sy"))

    def getRange(self, axis, depname, axrange):
        datasets = self._getDatasets()
        if not datasets:
            return
        s = self.settings

        if depname == "sx":
            # x range: data range of all datasets
            alldata = N.concatenate(datasets)
            axrange[0] = min(axrange[0], N.nanmin(alldata))
            axrange[1] = max(axrange[1], N.nanmax(alldata))
        elif depname == "sy":
            # y range: 0 to number of ridges
            n = len(datasets)
            axrange[0] = min(axrange[0], -0.5)
            axrange[1] = max(axrange[1], n - 0.5 + 1.0)

    def dataDraw(self, painter, axes, widgetposn, clip):
        s = self.settings
        datasets = self._getDatasets()
        if not datasets:
            return

        n = len(datasets)
        xaxis, yaxis = axes
        ngrid = s.gridPoints
        overlap = s.overlap

        # compute global x range for the grid
        alldata = N.concatenate(datasets)
        xmin, xmax = N.nanmin(alldata), N.nanmax(alldata)
        margin = (xmax - xmin) * 0.1
        grid = N.linspace(xmin - margin, xmax + margin, ngrid)

        # compute all KDEs
        kdes = []
        max_density = 0
        for arr in datasets:
            kde_vals = _kde(arr, grid, s.bandwidth)
            kdes.append(kde_vals)
            peak = N.nanmax(kde_vals)
            if peak > max_density:
                max_density = peak
        if max_density < 1e-15:
            return

        # scale factor: each ridge occupies ~1 unit on y-axis
        scale = 1.0 / max_density

        cliprect = clip
        with utils.painter_state(painter):
            painter.setClipRect(cliprect)

            xplt = xaxis.dataToPlotterCoords(widgetposn, grid)

            # draw from back to front (last dataset at bottom)
            coloridx = 0
            for ridx in range(n - 1, -1, -1):
                kde_vals = kdes[ridx]
                # baseline y position for this ridge
                baseline_y = float(ridx)
                # the density curve offset above baseline
                curve_y = baseline_y + kde_vals * scale * (1.0 + overlap)

                baseline_plt = yaxis.dataToPlotterCoords(
                    widgetposn, N.full(ngrid, baseline_y)
                )
                curve_plt = yaxis.dataToPlotterCoords(widgetposn, curve_y)

                valid = (
                    N.isfinite(xplt) & N.isfinite(baseline_plt) & N.isfinite(curve_plt)
                )
                if not N.any(valid):
                    continue

                # build fill path
                path = qt.QPainterPath()
                started = False
                for i in range(ngrid):
                    if valid[i]:
                        if not started:
                            path.moveTo(xplt[i], baseline_plt[i])
                            started = True
                for i in range(ngrid):
                    if valid[i]:
                        path.lineTo(xplt[i], curve_plt[i])
                for i in range(ngrid - 1, -1, -1):
                    if valid[i]:
                        path.lineTo(xplt[i], baseline_plt[i])
                path.closeSubpath()

                # color: use document auto-color system per ridge
                if s.autoColor:
                    c = qt.QColor(self.autoColor(painter, dataindex=ridx))
                    pen = s.Line.makeQPenWHide(painter)
                    pen.setColor(c)
                    trans = s.Fill.transparency
                    c.setAlphaF(1.0 - trans / 100.0)
                    brush = qt.QBrush(c)
                else:
                    pen = s.Line.makeQPenWHide(painter)
                    brush = s.Fill.makeQBrushWHide(painter)

                if s.filled:
                    painter.setBrush(brush)
                else:
                    painter.setBrush(qt.Qt.BrushStyle.NoBrush)
                painter.setPen(pen)
                painter.drawPath(path)

                coloridx += 1


document.thefactory.register(Ridgeline)
