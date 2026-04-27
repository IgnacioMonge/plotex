#    Copyright (C) 2026
#
#    This file is part of Veusz.
#
#    Veusz is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
#    Veusz is distributed in the hope that it will be useful, but
#    WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#    General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Veusz. If not, see <https://www.gnu.org/licenses/>.
#
##############################################################################

"""Violin plot widget for Veusz/Plotex.

Features:
 - Gaussian and Epanechnikov kernels
 - Scott, Silverman, or custom bandwidth
 - Soft/hard span mode
 - Inner annotations: box, quartile, stick, points, none
 - Side: both (symmetric), low (half), high (half)
 - Scaling: area, count, width with optional common normalization
 - Custom quantile lines
 - Configurable jitter for point display
"""

import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='ViolinPlot'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

# ── KDE helpers ──────────────────────────────────────────────────────

def _kde_gaussian(data, grid, bw):
    """Gaussian kernel density estimation."""
    n = len(data)
    if n == 0 or bw <= 0:
        return N.zeros_like(grid)
    u = (grid[:, None] - data[None, :]) / bw
    kernel = N.exp(-0.5 * u * u)
    return kernel.sum(axis=1) / (n * bw * N.sqrt(2 * N.pi))

def _kde_epanechnikov(data, grid, bw):
    """Epanechnikov kernel density estimation."""
    n = len(data)
    if n == 0 or bw <= 0:
        return N.zeros_like(grid)
    u = (grid[:, None] - data[None, :]) / bw
    kernel = N.where(N.abs(u) <= 1, 0.75 * (1 - u * u), 0.0)
    return kernel.sum(axis=1) / (n * bw)

_KDE_FUNCS = {
    'gaussian': _kde_gaussian,
    'epanechnikov': _kde_epanechnikov,
}

def _calc_bandwidth(data, method='scott', adjust=1.0, custom=None):
    """Calculate KDE bandwidth.

    data: cleaned 1D array (finite values only)
    method: 'scott', 'silverman', or 'custom'
    adjust: multiplier applied after calculation
    custom: direct bandwidth value (used when method='custom')
    """
    if method == 'custom' and custom is not None and custom > 0:
        return max(custom * adjust, 1e-10)

    n = len(data)
    if n < 2:
        return 1.0

    std = N.std(data, ddof=1)
    iqr = N.percentile(data, 75) - N.percentile(data, 25)
    a = min(std, iqr / 1.349) if iqr > 0 else std
    if a <= 0:
        a = 1.0

    if method == 'silverman':
        bw = a * (4.0 / (3.0 * n)) ** 0.2
    else:
        bw = a * n ** (-0.2)

    return max(bw * adjust, 1e-10)

# ── Drawing helpers ──────────────────────────────────────────────────

def _swapline(painter, x1, y1, x2, y2, swap):
    """Draw line, swapping x and y coordinates if swap is True."""
    if swap:
        painter.drawLine(qt.QPointF(y1, x1), qt.QPointF(y2, x2))
    else:
        painter.drawLine(qt.QPointF(x1, y1), qt.QPointF(x2, y2))

def _swappt(x, y, swap):
    """Return QPointF, swapping coordinates if swap is True."""
    if swap:
        return qt.QPointF(y, x)
    else:
        return qt.QPointF(x, y)

# ── Statistics ───────────────────────────────────────────────────────

class _ViolinStats:
    """Statistics for a single violin."""

    def calculate(self, data):
        """Calculate statistics from data array."""
        fdata = data[N.isfinite(data)]
        if len(fdata) == 0:
            self.valid = False
            return

        self.valid = True
        self.data = fdata
        self.n = len(fdata)
        self.mean = float(N.mean(fdata))
        self.median = float(N.median(fdata))
        self.min = float(N.min(fdata))
        self.max = float(N.max(fdata))
        self.q1 = float(N.percentile(fdata, 25))
        self.q3 = float(N.percentile(fdata, 75))
        self.iqr = self.q3 - self.q1
        self.std = float(N.std(fdata, ddof=1)) if self.n > 1 else 0.0

# ── Widget ───────────────────────────────────────────────────────────

class _ViolinFill(setting.Brush):
    """Fill for violin."""
    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)

class ViolinPlot(GenericPlotter):
    """Plot violin plots."""

    typename = 'violin'
    allowusercreation = True
    description = _('Plot violin plots')

    # ChoiceSwitch callbacks

    @staticmethod
    def _showBW(val):
        if val == 'custom':
            return (('bwCustom',), ())
        else:
            return ((), ('bwCustom',))

    @staticmethod
    def _showSpan(val):
        if val == 'soft':
            return (('cut',), ())
        else:
            return ((), ('cut',))

    @staticmethod
    def _showSide(val):
        if val == 'split':
            return (('splitValues',), ())
        else:
            return ((), ('splitValues',))

    @staticmethod
    def _showInner(val):
        box_s = ('InnerBoxFill', 'InnerBoxLine')
        pts_s = ('innerMarker', 'markerSize', 'jitter',
                 'MarkersLine', 'MarkersFill')
        if val == 'box':
            return (box_s, pts_s)
        elif val == 'points':
            return (pts_s, box_s)
        elif val == 'raincloud':
            return (box_s + pts_s, ())
        else:
            return ((), box_s + pts_s)

    @classmethod
    def addSettings(klass, s):
        """Construct list of settings."""
        GenericPlotter.addSettings(s)
        s.remove('key')

        # ── Data ─────────────────────────────────────────────────
        s.add( setting.Choice(
            'direction',
            ('horizontal', 'vertical'), 'vertical',
            descr=_('Horizontal or vertical violins'),
            usertext=_('Direction')), 0 )
        s.add( setting.DatasetOrStr(
            'labels', '',
            descr=_('Dataset or string to label violins'),
            usertext=_('Labels')), 0 )
        s.add( setting.DatasetExtended(
            'posn', '',
            descr=_('Positions of violins (optional)'),
            usertext=_('Positions')), 0 )
        s.add( setting.Datasets(
            'values', ('data',),
            descr=_('Datasets to plot violins for'),
            usertext=_('Datasets')), 0 )

        # ── KDE ──────────────────────────────────────────────────
        s.add( setting.Choice(
            'kernel',
            ('gaussian', 'epanechnikov'), 'gaussian',
            descr=_('KDE kernel function'),
            usertext=_('Kernel')) )
        s.add( setting.ChoiceSwitch(
            'bwMethod',
            ('scott', 'silverman', 'custom'), 'scott',
            showfn=klass._showBW,
            descr=_('Bandwidth method'),
            usertext=_('Bandwidth')) )
        s.add( setting.Float(
            'bwCustom', 0.5,
            descr=_('Custom bandwidth value'),
            usertext=_('BW value')) )
        s.add( setting.Float(
            'bwAdjust', 1.0,
            descr=_('Bandwidth multiplier (>1 smoother, <1 sharper)'),
            usertext=_('BW adjust')) )
        s.add( setting.Int(
            'gridPoints', 100,
            minval=20, maxval=1000,
            descr=_('Grid resolution for KDE'),
            usertext=_('Grid points')) )
        s.add( setting.ChoiceSwitch(
            'spanMode',
            ('soft', 'hard'), 'soft',
            showfn=klass._showSpan,
            descr=_(
                'Soft: extend KDE beyond data by cut units. '
                'Hard: clip at data extremes'),
            usertext=_('Span')) )
        s.add( setting.Float(
            'cut', 2.0,
            descr=_('BW units to extend beyond data range'),
            usertext=_('Cut')) )

        # ── Display ─────────────────────────────────────────────
        s.add( setting.ChoiceSwitch(
            'side',
            ('both', 'low', 'high', 'split'), 'both',
            showfn=klass._showSide,
            descr=_(
                'Both = symmetric, Low/High = half, '
                'Split = paired datasets on opposite sides'),
            usertext=_('Side')) )
        s.add( setting.Datasets(
            'splitValues', (),
            descr=_(
                'Second set of datasets for split mode '
                '(drawn on the high side)'),
            usertext=_('Split datasets')) )
        s.add( setting.ChoiceSwitch(
            'inner',
            ('box', 'quartile', 'stick', 'points',
             'raincloud', 'none'), 'box',
            showfn=klass._showInner,
            descr=_(
                'Inner style: box, quartile, stick, points, '
                'raincloud (half-violin + box + strip), none'),
            usertext=_('Inner')) )
        s.add( setting.Choice(
            'scaling',
            ('area', 'count', 'width'), 'area',
            descr=_(
                'Area: equal area, Count: proportional to N, '
                'Width: equal max width'),
            usertext=_('Scaling')) )
        s.add( setting.Bool(
            'commonNorm', False,
            descr=_('Normalize density across all violins together'),
            usertext=_('Common norm')) )
        s.add( setting.Float(
            'fillfraction', 0.75,
            descr=_('Max violin width as fraction of spacing'),
            usertext=_('Fill fraction'),
            formatting=True) )
        s.add( setting.ChoiceOrMore(
            'fillPalette',
            ['single color',
             'cb-set1', 'cb-set2', 'cb-dark2', 'cb-paired',
             'npg', 'nejm', 'lancet', 'jama', 'aaas', 'okabe-ito'],
            'cb-set1',
            descr=_('Color palette for violins (type any colormap name or choose from list)'),
            usertext=_('Fill palette'), formatting=True) )

        # ── Statistics ──────────────────────────────────────────
        s.add( setting.Bool(
            'showMean', False,
            descr=_('Show line at mean'),
            usertext=_('Show mean')) )
        s.add( setting.Bool(
            'showMedian', True,
            descr=_('Show line at median'),
            usertext=_('Show median')) )
        s.add( setting.Bool(
            'showExtrema', False,
            descr=_('Show cap lines at min/max'),
            usertext=_('Show extrema')) )
        s.add( setting.FloatList(
            'quantiles', [],
            descr=_(
                'Custom quantile lines (values 0-1, '
                'e.g. 0.05, 0.95)'),
            usertext=_('Quantiles')) )

        # ── Points mode ─────────────────────────────────────────
        s.add( setting.Marker(
            'innerMarker', 'circle',
            descr=_('Marker for data points'),
            usertext=_('Marker'),
            formatting=True) )
        s.add( setting.DistancePt(
            'markerSize', '2pt',
            descr=_('Size of data point markers'),
            usertext=_('Marker size'),
            formatting=True) )
        s.add( setting.Float(
            'jitter', 0.8,
            descr=_(
                'Jitter spread for points '
                '(0 = centered, 1 = full violin width)'),
            usertext=_('Jitter'),
            formatting=True) )

        # ── Style groups ────────────────────────────────────────
        s.add( _ViolinFill(
            'Fill',
            descr=_('Violin fill'),
            usertext=_('Violin fill')),
            pixmap='settings_bgfill' )
        s.add( setting.Line(
            'Border',
            descr=_('Violin border'),
            usertext=_('Violin border')),
            pixmap='settings_border' )
        s.add( setting.Line(
            'MedianLine',
            descr=_('Median line'),
            usertext=_('Median line')),
            pixmap='settings_medianline' )
        s.add( setting.Line(
            'MeanLine',
            descr=_('Mean line'),
            usertext=_('Mean line')),
            pixmap='settings_meanline' )
        s.add( setting.Line(
            'InnerLine',
            descr=_('Inner annotation lines (quartiles, sticks, extrema)'),
            usertext=_('Inner line')),
            pixmap='settings_innerline' )
        s.add( setting.Line(
            'QuantileLine',
            descr=_('Custom quantile lines'),
            usertext=_('Quantile line')),
            pixmap='settings_quantileline' )
        s.add( setting.GraphBrush(
            'InnerBoxFill',
            descr=_('Inner box fill'),
            usertext=_('Inner box fill')),
            pixmap='settings_innerbox' )
        s.add( setting.Line(
            'InnerBoxLine',
            descr=_('Inner box border'),
            usertext=_('Inner box border')),
            pixmap='settings_innerboxline' )
        s.add( setting.Line(
            'MarkersLine',
            descr=_('Marker border'),
            usertext=_('Markers border')),
            pixmap='settings_plotmarkerline' )
        s.add( setting.BoxPlotMarkerFillBrush(
            'MarkersFill',
            descr=_('Marker fill'),
            usertext=_('Markers fill')),
            pixmap='settings_plotmarkerfill' )

    # ── Properties ───────────────────────────────────────────────

    @property
    def userdescription(self):
        s = self.settings
        return "values='%s', position='%s'" % (
            ', '.join(s.values), s.posn)

    def affectsAxisRange(self):
        s = self.settings
        return ( (s.xAxis, 'sx'), (s.yAxis, 'sy') )

    def getPosns(self):
        s = self.settings
        doc = self.document
        posns = s.get('posn').getData(doc)
        if posns is not None:
            return posns.data
        vals = s.get('values').getData(doc)
        if vals is None:
            return N.array([])
        return N.arange(1, len(vals) + 1, dtype=N.float64)

    def getRange(self, axis, depname, axrange):
        s = self.settings
        doc = self.document
        if ( (depname == 'sx' and s.direction == 'horizontal') or
             (depname == 'sy' and s.direction == 'vertical') ):
            all_vals = []
            values = s.get('values').getData(doc)
            if values:
                all_vals.extend(values)
            if s.side == 'split':
                split_vals = s.get('splitValues').getData(doc)
                if split_vals:
                    all_vals.extend(split_vals)
            for v in all_vals:
                fdata = v.data[N.isfinite(v.data)]
                if len(fdata) > 0:
                    bw = _calc_bandwidth(
                        fdata, s.bwMethod, s.bwAdjust, s.bwCustom)
                    if s.spanMode == 'soft':
                        extend = max(s.cut, 0) * bw
                    else:
                        extend = 0
                    axrange[0] = min(axrange[0], N.min(fdata) - extend)
                    axrange[1] = max(axrange[1], N.max(fdata) + extend)
        else:
            posns = self.getPosns()
            if len(posns) > 0:
                axrange[0] = min(axrange[0], N.nanmin(posns) - 0.5)
                axrange[1] = max(axrange[1], N.nanmax(posns) + 0.5)

    def getAxisLabels(self, direction):
        s = self.settings
        doc = self.document
        text = s.get('labels').getData(doc, checknull=True)
        values = s.get('values').getData(doc)
        if text is None or values is None:
            return (None, None)
        return (text, self.getPosns())

    # ── KDE computation ─────────────────────────────────────────

    def _computeKDE(self, stats, s):
        """Compute KDE for a single dataset."""
        bw = _calc_bandwidth(
            stats.data, s.bwMethod, s.bwAdjust, s.bwCustom)

        if s.spanMode == 'soft':
            extend = max(s.cut, 0) * bw
        else:
            extend = 0

        grid = N.linspace(
            stats.min - extend, stats.max + extend,
            max(int(s.gridPoints), 20))

        kde_func = _KDE_FUNCS.get(s.kernel, _kde_gaussian)
        density = kde_func(stats.data, grid, bw)

        # Hard span: zero out density outside data range
        if s.spanMode == 'hard':
            density[grid < stats.min] = 0
            density[grid > stats.max] = 0

        return grid, density

    def _scaleViolins(self, densities, stats_list, grids, s):
        """Compute per-violin scale factors."""
        scaling = s.scaling
        common = s.commonNorm

        if scaling == 'width':
            scales = []
            for d in densities:
                mx = d.max()
                scales.append(1.0 / mx if mx > 0 else 1.0)
            if common:
                # common width: use global max
                global_max = max(
                    d.max() for d in densities) if densities else 1
                scales = [1.0 / global_max if global_max > 0
                          else 1.0] * len(densities)
            return scales

        elif scaling == 'count':
            max_n = max(st.n for st in stats_list) if stats_list else 1
            scales = []
            for d, st in zip(densities, stats_list):
                mx = d.max()
                cf = st.n / max_n if max_n > 0 else 1.0
                scales.append(cf / mx if mx > 0 else 1.0)
            return scales

        else:  # 'area'
            scales = []
            for d, grid in zip(densities, grids):
                if len(grid) > 1:
                    sp = (grid[-1] - grid[0]) / (len(grid) - 1)
                    area = N.sum(d) * sp
                else:
                    area = 1.0
                scales.append(1.0 / area if area > 0 else 1.0)

            # normalize so the widest violin has unit scale;
            # common/non-common produced identical results here
            if densities:
                max_sd = max(
                    sc * d.max() for sc, d in zip(scales, densities))
                if max_sd > 0:
                    scales = [sc / max_sd for sc in scales]
            return scales

    # ── Inner line helper ────────────────────────────────────────

    def _drawInnerLine(self, painter, value, grid, density,
                       half_width, posnplt, dataaxis, widgetposn,
                       pen, side, horz):
        """Draw a line spanning the violin at a data value."""
        painter.setPen(pen)
        valplt = dataaxis.dataToPlotterCoords(
            widgetposn, N.array([value]))[0]
        w = float(N.interp(value, grid, density)) * half_width

        if side == 'both':
            _swapline(painter,
                      posnplt - w, valplt, posnplt + w, valplt, horz)
        elif side == 'low':
            _swapline(painter,
                      posnplt - w, valplt, posnplt, valplt, horz)
        else:
            _swapline(painter,
                      posnplt, valplt, posnplt + w, valplt, horz)

    # ── Draw single violin ──────────────────────────────────────

    def plotViolin(self, painter, axes, posn, width, widgetposn,
                   clip, grid, density, stats, s, horz,
                   side_override=None, violinindex=0):
        """Draw a single violin with all annotations."""

        side = side_override if side_override else s.side
        dataaxis = axes[not horz]

        gridplt = dataaxis.dataToPlotterCoords(widgetposn, grid)
        posnplt = float(axes[horz].dataToPlotterCoords(
            widgetposn, N.array([posn]))[0])

        half_width = width / 2.0

        # ── Build polygon ────────────────────────────────────────
        pts = qt.QPolygonF()

        if side in ('both', 'low'):
            for i in range(len(grid)):
                w = density[i] * half_width
                pts.append(_swappt(posnplt - w, gridplt[i], horz))

        if side == 'both':
            for i in range(len(grid) - 1, -1, -1):
                w = density[i] * half_width
                pts.append(_swappt(posnplt + w, gridplt[i], horz))
        elif side == 'low':
            for i in range(len(grid) - 1, -1, -1):
                pts.append(_swappt(posnplt, gridplt[i], horz))
        elif side == 'high':
            for i in range(len(grid)):
                w = density[i] * half_width
                pts.append(_swappt(posnplt + w, gridplt[i], horz))
            for i in range(len(grid) - 1, -1, -1):
                pts.append(_swappt(posnplt, gridplt[i], horz))

        path = qt.QPainterPath()
        path.addPolygon(pts)
        path.closeSubpath()
        # draw violin fill
        border_pen = s.Border.makeQPenWHide(painter)
        if not s.Fill.hide:
            palette = s.fillPalette
            if palette != 'single color':
                from ..utils.colormap import getColormapArray
                cmap = self.document.evaluate.colormaps.get(palette)
                if cmap is not None:
                    arr = N.array(cmap)
                    is_step = len(arr) > 0 and arr[0][0] < 0
                    ncolors = (len(arr) - 1) if is_step else max(len(arr), 1)
                    rgba = getColormapArray(cmap, ncolors)
                    ci = violinindex % ncolors
                    color = qt.QColor(
                        int(rgba[ci][0]), int(rgba[ci][1]),
                        int(rgba[ci][2]), int(rgba[ci][3]))
                else:
                    color = s.Fill.makeQBrush(painter).color()
            else:
                color = s.Fill.makeQBrush(painter).color()
            if s.Fill.transparency > 0:
                color.setAlphaF((100 - s.Fill.transparency) / 100.)
            style = s.get('Fill').get('style').qtStyle()
            painter.setBrush(qt.QBrush(color, style))
            painter.setPen(border_pen)
            painter.drawPath(path)
        else:
            painter.setBrush(qt.QBrush())
            painter.setPen(border_pen)
            painter.drawPath(path)

        # ── Statistics in plotter coords ─────────────────────────
        statvals = N.array([
            stats.median, stats.q1, stats.q3,
            stats.mean, stats.min, stats.max])
        sp = dataaxis.dataToPlotterCoords(widgetposn, statvals)
        medplt, q1plt, q3plt, meanplt, minplt, maxplt = sp

        # ── Inner: box ───────────────────────────────────────────
        inner = s.inner

        if inner == 'box':
            boxw = width * 0.15

            whi = min(stats.q3 + 1.5 * stats.iqr, stats.max)
            wlo = max(stats.q1 - 1.5 * stats.iqr, stats.min)
            whiplt = dataaxis.dataToPlotterCoords(
                widgetposn, N.array([wlo, whi]))

            painter.setPen(s.InnerBoxLine.makeQPenWHide(painter))
            _swapline(painter,
                      posnplt, whiplt[0], posnplt, whiplt[1], horz)

            if horz:
                br = qt.QRectF(
                    qt.QPointF(q1plt, posnplt - boxw / 2),
                    qt.QPointF(q3plt, posnplt + boxw / 2))
            else:
                br = qt.QRectF(
                    qt.QPointF(posnplt - boxw / 2, q3plt),
                    qt.QPointF(posnplt + boxw / 2, q1plt))

            bp = qt.QPainterPath()
            bp.addRect(br)
            utils.brushExtFillPath(
                painter, s.InnerBoxFill, bp,
                stroke=s.InnerBoxLine.makeQPenWHide(painter))

            # Median dot
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QBrush(
                s.MedianLine.makeQPen(painter).color()))
            r = boxw * 0.25
            if horz:
                painter.drawEllipse(qt.QPointF(medplt, posnplt), r, r)
            else:
                painter.drawEllipse(qt.QPointF(posnplt, medplt), r, r)

        # ── Inner: quartile ──────────────────────────────────────
        elif inner == 'quartile':
            pen_q = s.InnerLine.makeQPenWHide(painter)
            self._drawInnerLine(
                painter, stats.q1, grid, density,
                half_width, posnplt, dataaxis, widgetposn,
                pen_q, side, horz)
            self._drawInnerLine(
                painter, stats.q3, grid, density,
                half_width, posnplt, dataaxis, widgetposn,
                pen_q, side, horz)
            self._drawInnerLine(
                painter, stats.median, grid, density,
                half_width, posnplt, dataaxis, widgetposn,
                s.MedianLine.makeQPenWHide(painter), side, horz)

        # ── Inner: stick ─────────────────────────────────────────
        elif inner == 'stick':
            painter.setPen(s.InnerLine.makeQPenWHide(painter))
            dataplt = dataaxis.dataToPlotterCoords(
                widgetposn, stats.data)
            stick_hw = width * 0.06

            for d, dp in zip(stats.data, dataplt):
                w = float(N.interp(d, grid, density)) * half_width
                sw = min(w, stick_hw)
                if side == 'both':
                    _swapline(painter,
                              posnplt - sw, dp, posnplt + sw, dp, horz)
                elif side == 'low':
                    _swapline(painter,
                              posnplt - sw, dp, posnplt, dp, horz)
                else:
                    _swapline(painter,
                              posnplt, dp, posnplt + sw, dp, horz)

        # ── Inner: points ────────────────────────────────────────
        elif inner == 'points':
            painter.setBrush(s.MarkersFill.makeQBrushWHide(painter))
            painter.setPen(s.MarkersLine.makeQPenWHide(painter))
            markersize = s.get('markerSize').convert(painter)
            dataplt = dataaxis.dataToPlotterCoords(
                widgetposn, stats.data)

            jitter_factor = max(min(s.jitter, 1.0), 0.0)
            rng = N.random.RandomState(42)
            jitters = N.zeros(len(stats.data))
            for j, d in enumerate(stats.data):
                w = float(N.interp(d, grid, density)) * half_width
                w *= jitter_factor
                if side == 'both':
                    jitters[j] = (rng.random() - 0.5) * 2 * w
                elif side == 'low':
                    jitters[j] = -rng.random() * w
                else:
                    jitters[j] = rng.random() * w

            posnvals = N.full_like(dataplt, posnplt) + jitters
            if horz:
                xpts, ypts = dataplt, posnvals
            else:
                xpts, ypts = posnvals, dataplt

            utils.plotMarkers(
                painter, xpts, ypts, s.innerMarker, markersize,
                clip=clip)

        # ── Inner: raincloud ─────────────────────────────────────
        elif inner == 'raincloud':
            # Force half-violin: draw body was already drawn with
            # the current side setting. Now add box + strip on the
            # opposite side.
            if side == 'both':
                box_side = 'high'
                pts_side = 'high'
            elif side == 'low':
                box_side = 'high'
                pts_side = 'high'
            else:
                box_side = 'low'
                pts_side = 'low'

            # Mini boxplot offset to the opposite side
            boxw = width * 0.12
            box_offset = width * 0.18
            if box_side == 'low':
                box_center = posnplt - box_offset
            else:
                box_center = posnplt + box_offset

            whi = min(stats.q3 + 1.5 * stats.iqr, stats.max)
            wlo = max(stats.q1 - 1.5 * stats.iqr, stats.min)
            whiplt = dataaxis.dataToPlotterCoords(
                widgetposn, N.array([wlo, whi]))

            painter.setPen(s.InnerBoxLine.makeQPenWHide(painter))
            _swapline(painter,
                      box_center, whiplt[0], box_center, whiplt[1], horz)

            if horz:
                br = qt.QRectF(
                    qt.QPointF(q1plt, box_center - boxw / 2),
                    qt.QPointF(q3plt, box_center + boxw / 2))
            else:
                br = qt.QRectF(
                    qt.QPointF(box_center - boxw / 2, q3plt),
                    qt.QPointF(box_center + boxw / 2, q1plt))

            bp = qt.QPainterPath()
            bp.addRect(br)
            utils.brushExtFillPath(
                painter, s.InnerBoxFill, bp,
                stroke=s.InnerBoxLine.makeQPenWHide(painter))

            # Median dot on box
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QBrush(
                s.MedianLine.makeQPen(painter).color()))
            r = boxw * 0.25
            if horz:
                painter.drawEllipse(
                    qt.QPointF(medplt, box_center), r, r)
            else:
                painter.drawEllipse(
                    qt.QPointF(box_center, medplt), r, r)

            # Jittered strip further out
            painter.setBrush(s.MarkersFill.makeQBrushWHide(painter))
            painter.setPen(s.MarkersLine.makeQPenWHide(painter))
            markersize = s.get('markerSize').convert(painter)
            dataplt = dataaxis.dataToPlotterCoords(
                widgetposn, stats.data)

            strip_offset = width * 0.32
            if pts_side == 'low':
                strip_center = posnplt - strip_offset
            else:
                strip_center = posnplt + strip_offset

            jitter_factor = max(min(s.jitter, 1.0), 0.0)
            rng = N.random.RandomState(42)
            jitter_hw = width * 0.08 * jitter_factor
            jitters = (rng.random(len(stats.data)) - 0.5) * 2 * jitter_hw

            posnvals = N.full_like(dataplt, strip_center) + jitters
            if horz:
                xpts, ypts = dataplt, posnvals
            else:
                xpts, ypts = posnvals, dataplt

            utils.plotMarkers(
                painter, xpts, ypts, s.innerMarker, markersize,
                clip=clip)

        # ── Statistics lines ─────────────────────────────────────
        if s.showMean and not s.MeanLine.hide:
            self._drawInnerLine(
                painter, stats.mean, grid, density,
                half_width, posnplt, dataaxis, widgetposn,
                s.MeanLine.makeQPenWHide(painter), side, horz)

        if s.showMedian and inner not in ('box', 'quartile'):
            if not s.MedianLine.hide:
                self._drawInnerLine(
                    painter, stats.median, grid, density,
                    half_width, posnplt, dataaxis, widgetposn,
                    s.MedianLine.makeQPenWHide(painter), side, horz)

        if s.showExtrema and not s.InnerLine.hide:
            painter.setPen(s.InnerLine.makeQPenWHide(painter))
            capw = width * 0.06
            _swapline(painter,
                      posnplt - capw, minplt, posnplt + capw, minplt,
                      horz)
            _swapline(painter,
                      posnplt - capw, maxplt, posnplt + capw, maxplt,
                      horz)

        # ── Custom quantile lines ────────────────────────────────
        qvals = s.quantiles
        if qvals and not s.QuantileLine.hide:
            pen_q = s.QuantileLine.makeQPenWHide(painter)
            for q in qvals:
                if 0 < q < 1:
                    v = float(N.percentile(stats.data, q * 100))
                    if stats.min <= v <= stats.max:
                        self._drawInnerLine(
                            painter, v, grid, density,
                            half_width, posnplt, dataaxis, widgetposn,
                            pen_q, side, horz)

    # ── Main draw ────────────────────────────────────────────────

    def dataDraw(self, painter, axes, widgetposn, clip):
        """Plot the violin plots."""

        s = self.settings
        doc = self.document

        values = s.get('values').getData(doc)
        if values is None:
            return

        positions = self.getPosns()
        if len(positions) == 0:
            return

        axes = self.parent.getAxes( (s.xAxis, s.yAxis) )
        if ( axes[0] is None or axes[1] is None or
             axes[0].settings.direction != 'horizontal' or
             axes[1].settings.direction != 'vertical' ):
            return

        horz = (s.direction == 'horizontal')

        # Compute statistics and KDE
        all_stats = []
        all_grids = []
        all_densities = []

        for vals in values:
            stats = _ViolinStats()
            stats.calculate(vals.data)
            all_stats.append(stats)
            if stats.valid:
                grid, density = self._computeKDE(stats, s)
                all_grids.append(grid)
                all_densities.append(density)
            else:
                all_grids.append(N.array([]))
                all_densities.append(N.array([]))

        valid_idx = [i for i, st in enumerate(all_stats) if st.valid]
        if not valid_idx:
            return

        valid_d = [all_densities[i] for i in valid_idx]
        valid_s = [all_stats[i] for i in valid_idx]
        valid_g = [all_grids[i] for i in valid_idx]

        scales = self._scaleViolins(valid_d, valid_s, valid_g, s)

        si = 0
        for i in range(len(all_densities)):
            if all_stats[i].valid:
                all_densities[i] = all_densities[i] * scales[si]
                si += 1

        # Width in plotter coords
        plotposns = axes[horz].dataToPlotterCoords(widgetposn, positions)

        if horz:
            inplot = (
                (plotposns > widgetposn[1]) & (plotposns < widgetposn[3]))
        else:
            inplot = (
                (plotposns > widgetposn[0]) & (plotposns < widgetposn[2]))
        inplotposn = plotposns[inplot]

        if inplotposn.shape[0] < 2:
            if horz:
                width = (widgetposn[3] - widgetposn[1]) * 0.5
            else:
                width = (widgetposn[2] - widgetposn[0]) * 0.5
        else:
            inplotposn.sort()
            width = N.nanmin(inplotposn[1:] - inplotposn[:-1])

        width = width * s.fillfraction

        # Split mode: compute KDE for second set of datasets
        split_stats = []
        split_grids = []
        split_densities = []
        is_split = (s.side == 'split')

        if is_split:
            split_values = s.get('splitValues').getData(doc)
            if split_values:
                for vals in split_values:
                    st = _ViolinStats()
                    st.calculate(vals.data)
                    split_stats.append(st)
                    if st.valid:
                        g, d = self._computeKDE(st, s)
                        split_grids.append(g)
                        split_densities.append(d)
                    else:
                        split_grids.append(N.array([]))
                        split_densities.append(N.array([]))

                # scale split violins independently (their own max density)
                sv_idx = [i for i, st in enumerate(split_stats)
                          if st.valid]
                if sv_idx:
                    sv_d = [split_densities[i] for i in sv_idx]
                    sv_s = [split_stats[i] for i in sv_idx]
                    sv_g = [split_grids[i] for i in sv_idx]
                    sv_scales = self._scaleViolins(
                        sv_d, sv_s, sv_g, s)
                    si2 = 0
                    for i in range(len(split_densities)):
                        if split_stats[i].valid:
                            split_densities[i] = (
                                split_densities[i] * sv_scales[si2])
                            si2 += 1

        # Draw each violin
        for i, plotpos in enumerate(plotposns):
            if i >= len(all_stats) or not all_stats[i].valid:
                continue

            if is_split:
                # Draw primary dataset on low side
                self.plotViolin(
                    painter, axes, positions[i], width, widgetposn,
                    clip, all_grids[i], all_densities[i],
                    all_stats[i], s, horz, side_override='low',
                    violinindex=i)
                # Draw split dataset on high side
                if i < len(split_stats) and split_stats[i].valid:
                    self.plotViolin(
                        painter, axes, positions[i], width, widgetposn,
                        clip, split_grids[i], split_densities[i],
                        split_stats[i], s, horz, side_override='high',
                        violinindex=i)
            else:
                self.plotViolin(
                    painter, axes, positions[i], width, widgetposn,
                    clip, all_grids[i], all_densities[i],
                    all_stats[i], s, horz, violinindex=i)

# Register widget
document.thefactory.register(ViolinPlot)
