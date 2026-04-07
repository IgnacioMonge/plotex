#    Copyright (C) 2026 M. Ignacio Monge García
#
#    This file is part of Plotex (fork of Veusz).
#
#    Plotex is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
##############################################################################

"""Bland-Altman (difference) plot widget.

Professional Bland-Altman plot following MedCalc/Prism standards:
  - X axis: mean of two methods = (method1 + method2) / 2
  - Y axis: difference = method1 - method2
  - Bias (mean difference) line with value annotation
  - Limits of agreement (±1.96 SD) with value annotations
  - Optional: zero reference line, 95% CI bands,
    regression line of differences (proportional bias detection)
"""

import numpy as N

from .. import qtall as qt
from .. import document
from .. import setting
from .. import utils

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='BlandAltman'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


class _ConfBandFill(setting.PlotterFill):
    """Fill for confidence interval bands with sensible defaults."""
    def __init__(self, name, **args):
        setting.PlotterFill.__init__(self, name, **args)
        self.get('color').newDefault('grey')
        self.get('transparency').newDefault(75)


class BlandAltman(GenericPlotter):
    """Plot a Bland-Altman (difference) plot comparing two measurement methods.

    Scatter points show (mean, difference) for each paired observation.
    Horizontal reference lines show the bias (mean difference) and
    limits of agreement (bias ± k·SD).  Optional confidence interval bands,
    regression line, and a zero-reference line can also be displayed.
    """

    typename = 'blandaltman'
    allowusercreation = True
    description = _('Plot Bland-Altman difference plot')

    def __init__(self, parent, **args):
        GenericPlotter.__init__(self, parent, **args)
        self._means = None
        self._diffs = None
        self._bias = None
        self._sd = None
        self._n = 0
        self._reg_slope = None
        self._reg_intercept = None
        self._reg_r2 = None
        self._changeset = -1

    def defaultAxisLabels(self):
        """Return default axis labels for this widget type."""
        return {
            'x': 'Mean of Method 1 and Method 2',
            'y': 'Method 1 \u2212 Method 2',
        }

    @classmethod
    def addSettings(klass, s):
        """Construct list of settings."""
        GenericPlotter.addSettings(s)

        # ── Data ──────────────────────────────────────────────────
        s.add(setting.DatasetExtended(
            'method1Data', '',
            descr=_('First method measurements'),
            usertext=_('Method 1 data')), 0)
        s.add(setting.DatasetExtended(
            'method2Data', '',
            descr=_('Second method measurements'),
            usertext=_('Method 2 data')), 1)

        # ── Appearance ────────────────────────────────────────────
        s.add(setting.Color(
            'color', 'auto',
            descr=_('Master color for markers'),
            usertext=_('Color'), formatting=True))
        s.add(setting.Marker(
            'marker', 'circle',
            descr=_('Type of scatter marker'),
            usertext=_('Marker'), formatting=True))
        s.add(setting.DistancePt(
            'markerSize', '3pt',
            descr=_('Size of scatter markers'),
            usertext=_('Marker size'), formatting=True))

        # ── Visibility toggles ────────────────────────────────────
        s.add(setting.Bool(
            'showBias', True,
            descr=_('Show mean difference (bias) line'),
            usertext=_('Show bias'), formatting=True))
        s.add(setting.Bool(
            'showLOA', True,
            descr=_('Show limits of agreement lines'),
            usertext=_('Show LOA'), formatting=True))
        s.add(setting.Bool(
            'showZero', False,
            descr=_('Show zero reference line (line of equality)'),
            usertext=_('Show zero line'), formatting=True))
        s.add(setting.Bool(
            'showConfBands', False,
            descr=_('Show 95% confidence interval bands for bias and LOA'),
            usertext=_('Show CI bands'), formatting=True))
        s.add(setting.Bool(
            'showRegression', False,
            descr=_('Show regression line of differences (proportional bias)'),
            usertext=_('Show regression'), formatting=True))

        # ── Line labels ───────────────────────────────────────────
        s.add(setting.Bool(
            'showLineLabels', True,
            descr=_('Show value annotations on bias and LOA lines'),
            usertext=_('Show line labels'), formatting=True))
        s.add(setting.Choice(
            'labelPosition',
            ['right', 'left'],
            'right',
            descr=_('Position of line value labels'),
            usertext=_('Label position'), formatting=True))
        s.add(setting.Int(
            'labelPrecision', 2,
            descr=_('Decimal places for line value labels'),
            usertext=_('Label precision'), formatting=True,
            minval=0, maxval=6))
        s.add(setting.Bool(
            'showRegressionEq', False,
            descr=_('Show regression equation and R²'),
            usertext=_('Show regression eq.'), formatting=True))

        # ── LOA multiplier ────────────────────────────────────────
        s.add(setting.Float(
            'loaMultiplier', 1.96,
            descr=_('SD multiplier for limits of agreement (1.96 = 95%)'),
            usertext=_('LOA multiplier'),
            minval=0.1, maxval=5.0))

        # ── Sub-settings (line styles, fills) ─────────────────────
        s.add(setting.Line(
            'BiasLine',
            descr=_('Bias line style'),
            usertext=_('Bias line')),
            pixmap='settings_meanline')
        s.BiasLine.get('color').newDefault('auto')
        s.BiasLine.get('width').newDefault('1.5pt')

        s.add(setting.Line(
            'LOALine',
            descr=_('Limits of agreement line style'),
            usertext=_('LOA line')),
            pixmap='settings_whisker')
        s.LOALine.get('style').newDefault('dashed')
        s.LOALine.get('color').newDefault('darkred')
        s.LOALine.get('width').newDefault('1.5pt')

        s.add(setting.Line(
            'ZeroLine',
            descr=_('Zero reference line style'),
            usertext=_('Zero line')),
            pixmap='settings_gridline')
        s.ZeroLine.get('style').newDefault('dotted')
        s.ZeroLine.get('color').newDefault('grey')

        s.add(setting.Line(
            'RegressionLine',
            descr=_('Regression line style'),
            usertext=_('Regression line')),
            pixmap='settings_ploterrorline')
        s.RegressionLine.get('style').newDefault('dash-dot')
        s.RegressionLine.get('color').newDefault('green')

        s.add(setting.Line(
            'MarkerLine',
            descr=_('Line around markers'),
            usertext=_('Marker border')),
            pixmap='settings_plotmarkerline')

        s.add(setting.BoxPlotMarkerFillBrush(
            'MarkerFill',
            descr=_('Marker fill'),
            usertext=_('Marker fill')),
            pixmap='settings_plotmarkerfill')
        s.MarkerFill.get('color').newDefault('background')

        s.add(_ConfBandFill(
            'ConfBandFill',
            descr=_('Confidence interval band fill'),
            usertext=_('CI band fill')),
            pixmap='settings_plotfillbelow')

        s.add(setting.Text(
            'Label',
            descr=_('Line annotation font'),
            usertext=_('Line labels')),
            pixmap='settings_axislabel')

    @property
    def userdescription(self):
        s = self.settings
        return "method1='%s', method2='%s'" % (s.method1Data, s.method2Data)

    # ── Computation (cached) ──────────────────────────────────────

    def _computeStats(self):
        """Compute means, diffs, bias, sd, and optional regression."""

        d = self.document
        if self._changeset == d.changeset:
            return
        self._changeset = d.changeset

        # reset
        self._means = self._diffs = self._bias = self._sd = None
        self._n = 0
        self._reg_slope = self._reg_intercept = self._reg_r2 = None

        s = self.settings
        ds1 = s.get('method1Data').getData(d)
        ds2 = s.get('method2Data').getData(d)
        if ds1 is None or ds2 is None:
            return

        m1 = ds1.data
        m2 = ds2.data
        if m1 is None or m2 is None:
            return

        try:
            m1 = N.asarray(m1, dtype=float)
            m2 = N.asarray(m2, dtype=float)
        except (ValueError, TypeError):
            return

        if m1.ndim != 1 or m2.ndim != 1:
            return

        minlen = min(len(m1), len(m2))
        if minlen < 2:
            return
        m1 = m1[:minlen]
        m2 = m2[:minlen]

        finite = N.isfinite(m1) & N.isfinite(m2)
        m1 = m1[finite]
        m2 = m2[finite]
        if len(m1) < 2:
            return

        means = (m1 + m2) / 2.0
        diffs = m1 - m2

        self._means = means
        self._diffs = diffs
        self._bias = float(N.mean(diffs))
        self._sd = float(N.std(diffs, ddof=1))
        self._n = len(diffs)

        # regression of differences on means (proportional bias)
        if len(means) >= 3:
            try:
                coeffs = N.polyfit(means, diffs, 1)
                self._reg_slope = float(coeffs[0])
                self._reg_intercept = float(coeffs[1])
                predicted = coeffs[0] * means + coeffs[1]
                ss_res = N.sum((diffs - predicted) ** 2)
                ss_tot = N.sum((diffs - self._bias) ** 2)
                self._reg_r2 = float(
                    1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
            except (N.linalg.LinAlgError, ValueError):
                pass

    # ── Axis range ────────────────────────────────────────────────

    def affectsAxisRange(self):
        s = self.settings
        return ((s.xAxis, 'sx'), (s.yAxis, 'sy'))

    def getRange(self, axis, depname, axrange):
        self._computeStats()
        if self._means is None:
            return

        s = self.settings
        mult = s.loaMultiplier

        if depname == 'sx':
            vals = self._means
            if len(vals) > 0:
                padding = (N.nanmax(vals) - N.nanmin(vals)) * 0.05
                if padding == 0:
                    padding = 1.0
                axrange[0] = min(axrange[0], N.nanmin(vals) - padding)
                axrange[1] = max(axrange[1], N.nanmax(vals) + padding)

        elif depname == 'sy':
            bias = self._bias
            sd = self._sd
            n = self._n
            loa_upper = bias + mult * sd
            loa_lower = bias - mult * sd

            if s.showConfBands and n > 0:
                se_loa = sd * N.sqrt(3.0 / n)
                y_min = loa_lower - 1.96 * se_loa
                y_max = loa_upper + 1.96 * se_loa
            else:
                y_min = min(float(N.nanmin(self._diffs)), loa_lower)
                y_max = max(float(N.nanmax(self._diffs)), loa_upper)

            padding = (y_max - y_min) * 0.08
            if padding == 0:
                padding = 1.0
            axrange[0] = min(axrange[0], y_min - padding)
            axrange[1] = max(axrange[1], y_max + padding)

    # ── Key ───────────────────────────────────────────────────────

    def drawKeySymbol(self, number, painter, x, y, width, height):
        s = self.settings
        xc = x + width / 2
        yc = y + height / 2
        markersize = s.get('markerSize').convert(painter)

        painter.setPen(s.MarkerLine.makeQPenWHide(painter))
        painter.setBrush(s.MarkerFill.makeQBrushWHide(painter))
        utils.plotMarkers(
            painter, N.array([xc]), N.array([yc]),
            s.marker, markersize)

        if s.showBias and not s.BiasLine.hide:
            pen = s.BiasLine.makeQPen(painter)
            painter.setPen(pen)
            painter.drawLine(
                qt.QPointF(x, yc), qt.QPointF(x + width, yc))

    # ── Drawing helpers ───────────────────────────────────────────

    def _drawHLine(self, painter, axes, posn, yval, cliprect, lineSettings):
        """Draw a horizontal line across the full plot width.

        Visibility is controlled by the caller (show* settings),
        so we use makeQPen (ignoring sub-setting hide flag).
        """
        pen = lineSettings.makeQPen(painter)
        yplt = axes[1].dataToPlotterCoords(posn, N.array([yval]))[0]
        painter.setPen(pen)
        painter.drawLine(
            qt.QPointF(posn[0], yplt), qt.QPointF(posn[2], yplt))

    def _drawConfBand(self, painter, axes, posn, y_center, y_halfwidth,
                      cliprect, fillSettings):
        """Draw a filled horizontal CI band.

        Visibility is controlled by showConfBands, not fillSettings.hide.
        """
        y_lo = axes[1].dataToPlotterCoords(
            posn, N.array([y_center - y_halfwidth]))[0]
        y_hi = axes[1].dataToPlotterCoords(
            posn, N.array([y_center + y_halfwidth]))[0]

        top = min(y_lo, y_hi)
        bottom = max(y_lo, y_hi)
        rect = qt.QRectF(
            qt.QPointF(posn[0], top), qt.QPointF(posn[2], bottom))

        path = qt.QPainterPath()
        path.addRect(rect)
        clippath = qt.QPainterPath()
        clippath.addRect(cliprect)
        path = path.intersected(clippath)

        utils.brushExtFillPath(painter, fillSettings, path, ignorehide=True)

    def _drawLineLabel(self, painter, axes, posn, yval,
                       top_text, bottom_text):
        """Draw two-line annotation next to a horizontal reference line.

        top_text: e.g. "+1.96 SD" or "Mean"
        bottom_text: e.g. "73.86" or "-2.12"
        """
        s = self.settings
        if not s.showLineLabels or s.Label.hide:
            return

        font = s.Label.makeQFont(painter)
        painter.setFont(font)
        painter.setPen(s.Label.makeQPen(painter))
        fm = qt.QFontMetricsF(font)

        yplt = axes[1].dataToPlotterCoords(posn, N.array([yval]))[0]
        x1, y1, x2, y2 = posn
        margin = 6
        line_h = fm.height()

        if s.labelPosition == 'right':
            # top_text right-aligned, above the line
            tw_top = fm.horizontalAdvance(top_text)
            tw_bot = fm.horizontalAdvance(bottom_text)
            tx_top = x2 - tw_top - margin
            tx_bot = x2 - tw_bot - margin
        else:
            tx_top = x1 + margin
            tx_bot = x1 + margin

        # top_text above line, bottom_text below line
        painter.drawText(qt.QPointF(tx_top, yplt - 3), top_text)
        painter.drawText(qt.QPointF(tx_bot, yplt + line_h), bottom_text)

    def _drawRegressionLine(self, painter, axes, posn, cliprect):
        """Draw regression line of differences."""
        s = self.settings
        if self._reg_slope is None:
            return

        pen = s.RegressionLine.makeQPen(painter)

        slope = self._reg_slope
        intercept = self._reg_intercept

        x_min = float(N.nanmin(self._means))
        x_max = float(N.nanmax(self._means))
        x_arr = N.array([x_min, x_max])
        y_arr = slope * x_arr + intercept

        xplt = axes[0].dataToPlotterCoords(posn, x_arr)
        yplt = axes[1].dataToPlotterCoords(posn, y_arr)

        painter.setPen(pen)
        painter.setBrush(qt.QBrush())
        pts = qt.QPolygonF()
        pts.append(qt.QPointF(xplt[0], yplt[0]))
        pts.append(qt.QPointF(xplt[1], yplt[1]))
        utils.plotClippedPolyline(painter, cliprect, pts)

    def _drawRegressionEq(self, painter, posn):
        """Draw regression equation text."""
        s = self.settings
        if self._reg_slope is None or s.Label.hide:
            return

        prec = s.labelPrecision
        slope = self._reg_slope
        intercept = self._reg_intercept
        r2 = self._reg_r2 if self._reg_r2 is not None else 0.0

        eq = 'y = %.*f\u00b7x %+.*f  (R\u00b2 = %.3f)' % (
            prec, slope, prec, intercept, r2)

        font = s.Label.makeQFont(painter)
        painter.setFont(font)
        painter.setPen(s.Label.makeQPen(painter))
        fm = qt.QFontMetricsF(font)

        x1, y1, x2, y2 = posn
        margin = 8
        tx = x1 + margin
        ty = y1 + fm.height() + margin
        painter.drawText(qt.QPointF(tx, ty), eq)

    # ── Main draw ─────────────────────────────────────────────────

    def dataDraw(self, painter, axes, posn, cliprect):
        """Plot the Bland-Altman data."""
        s = self.settings
        self._computeStats()

        if self._means is None:
            return

        means = self._means
        diffs = self._diffs
        bias = self._bias
        sd = self._sd
        n = self._n
        mult = s.loaMultiplier
        prec = s.labelPrecision

        loa_upper = bias + mult * sd
        loa_lower = bias - mult * sd

        xplt = axes[0].dataToPlotterCoords(posn, means)
        yplt = axes[1].dataToPlotterCoords(posn, diffs)

        # 1. Confidence bands (behind everything)
        if s.showConfBands and n > 0:
            se_bias = sd / N.sqrt(n)
            ci_bias_hw = 1.96 * se_bias
            se_loa = sd * N.sqrt(3.0 / n)
            ci_loa_hw = 1.96 * se_loa

            self._drawConfBand(
                painter, axes, posn, bias, ci_bias_hw,
                cliprect, s.ConfBandFill)
            self._drawConfBand(
                painter, axes, posn, loa_upper, ci_loa_hw,
                cliprect, s.ConfBandFill)
            self._drawConfBand(
                painter, axes, posn, loa_lower, ci_loa_hw,
                cliprect, s.ConfBandFill)

        # 2. Zero reference line
        if s.showZero:
            self._drawHLine(painter, axes, posn, 0.0, cliprect, s.ZeroLine)

        # 3. Regression line
        if s.showRegression:
            self._drawRegressionLine(painter, axes, posn, cliprect)

        # 4. LOA lines + labels
        if s.showLOA:
            self._drawHLine(
                painter, axes, posn, loa_upper, cliprect, s.LOALine)
            self._drawHLine(
                painter, axes, posn, loa_lower, cliprect, s.LOALine)

            # format multiplier: "1.96" or "2" etc.
            if mult == int(mult):
                mstr = '%d' % int(mult)
            else:
                mstr = '%.2f' % mult

            self._drawLineLabel(
                painter, axes, posn, loa_upper,
                '+%s SD' % mstr, '%.*f' % (prec, loa_upper))
            self._drawLineLabel(
                painter, axes, posn, loa_lower,
                '\u2212%s SD' % mstr, '%.*f' % (prec, loa_lower))

        # 5. Bias line + label
        if s.showBias:
            self._drawHLine(
                painter, axes, posn, bias, cliprect, s.BiasLine)
            self._drawLineLabel(
                painter, axes, posn, bias,
                'Mean', '%.*f' % (prec, bias))

        # 6. Scatter markers
        markersize = s.get('markerSize').convert(painter)
        painter.setPen(s.MarkerLine.makeQPenWHide(painter))
        painter.setBrush(s.MarkerFill.makeQBrushWHide(painter))
        utils.plotMarkers(
            painter, xplt, yplt, s.marker, markersize, clip=cliprect)

        # 7. Regression equation (on top)
        if s.showRegression and s.showRegressionEq:
            self._drawRegressionEq(painter, posn)


document.thefactory.register(BlandAltman)
