"""Pareto chart widget — sorted bars + cumulative line."""

import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='Pareto'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


class _BarFill(setting.Brush):
    """Fill for Pareto bars."""
    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)

class _LineLine(setting.Line):
    """Line style for cumulative curve."""
    def __init__(self, name, **args):
        setting.Line.__init__(self, name, **args)
        self.get('color').newDefault('red')
        self.get('width').newDefault('1.5pt')


class Pareto(GenericPlotter):
    """Pareto chart: bars sorted by frequency + cumulative percentage line."""

    typename = 'pareto'
    allowusercreation = True
    description = _('Pareto chart (bars + cumulative line)')

    @classmethod
    def addSettings(klass, s):
        GenericPlotter.addSettings(s)
        s.remove('key')

        s.add(setting.DatasetOrStr(
            'labels', '',
            descr=_('Category labels (text dataset or list)'),
            usertext=_('Labels')), 0)
        s.add(setting.DatasetExtended(
            'values', '',
            descr=_('Values for each category'),
            usertext=_('Values')), 1)

        s.add(setting.Choice(
            'direction', ('vertical', 'horizontal'),
            'vertical',
            descr=_('Bar direction'),
            usertext=_('Direction')), 2)
        s.add(setting.Float(
            'barWidth', 0.7, minval=0.1, maxval=1.0,
            descr=_('Bar width (fraction of spacing)'),
            usertext=_('Bar width')), 3)
        s.add(setting.Bool(
            'showCumulative', True,
            descr=_('Show cumulative percentage line'),
            usertext=_('Cumulative line')), 4)
        s.add(setting.Bool(
            'showPercentAxis', True,
            descr=_('Mark 80% threshold on cumulative line'),
            usertext=_('80% threshold')), 5)

        s.add(_BarFill(
            'BarFill',
            descr=_('Bar fill'),
            usertext=_('Bar fill')),
            pixmap='settings_bgfill')
        s.add(setting.Line(
            'BarBorder',
            descr=_('Bar border'),
            usertext=_('Bar border')),
            pixmap='settings_border')
        s.add(_LineLine(
            'CumulativeLine',
            descr=_('Cumulative line style'),
            usertext=_('Cumul. line')),
            pixmap='settings_plotline')
        s.add(setting.Brush(
            'CumulativeMarkerFill',
            descr=_('Cumulative marker fill'),
            usertext=_('Cumul. marker')),
            pixmap='settings_plotmarkerfill')

    @property
    def userdescription(self):
        return "values='%s'" % self.settings.values

    def affectsAxisRange(self):
        s = self.settings
        return ((s.xAxis, 'sx'), (s.yAxis, 'sy'))

    def _getSorted(self):
        """Return (labels, values, cumulative_pct) sorted descending."""
        s = self.settings
        doc = self.document

        vdata = s.get('values').getData(doc)
        if vdata is None:
            return None, None, None
        vals = N.array(vdata.data, dtype=float)
        valid = N.isfinite(vals) & (vals >= 0)
        vals = vals[valid]
        n = len(vals)
        if n == 0:
            return None, None, None

        ldata = s.get('labels').getData(doc, checknull=True)
        if ldata is not None:
            # DatasetOrStr returns a list of strings
            if hasattr(ldata, 'data'):
                labs = list(ldata.data)
            else:
                labs = list(ldata)
            # trim/pad to match values
            labs = [labs[i] if i < len(labs) else str(i+1) for i in range(len(valid))]
            labs = [labs[i] for i in range(len(valid)) if valid[i]]
        else:
            labs = [str(i+1) for i in range(n)]

        # sort descending
        order = N.argsort(vals)[::-1]
        vals = vals[order]
        labs = [labs[i] for i in order]

        total = vals.sum()
        if total > 0:
            cum_pct = N.cumsum(vals) / total * 100.0
        else:
            cum_pct = N.zeros_like(vals)

        return labs, vals, cum_pct

    def getRange(self, axis, depname, axrange):
        labs, vals, cum_pct = self._getSorted()
        if vals is None or len(vals) == 0:
            return

        s = self.settings
        vertical = s.direction == 'vertical'
        n = len(vals)

        if depname == 'sx':
            if vertical:
                axrange[0] = min(axrange[0], -0.5)
                axrange[1] = max(axrange[1], n - 0.5)
            else:
                axrange[0] = min(axrange[0], 0)
                axrange[1] = max(axrange[1], N.nanmax(vals) * 1.05)
        elif depname == 'sy':
            if vertical:
                axrange[0] = min(axrange[0], 0)
                axrange[1] = max(axrange[1], N.nanmax(vals) * 1.05)
            else:
                axrange[0] = min(axrange[0], -0.5)
                axrange[1] = max(axrange[1], n - 0.5)

    def dataDraw(self, painter, axes, widgetposn, clip):
        s = self.settings
        labs, vals, cum_pct = self._getSorted()
        if vals is None or len(vals) == 0:
            return

        n = len(vals)
        vertical = s.direction == 'vertical'
        bw = s.barWidth

        xaxis, yaxis = axes
        positions = N.arange(n, dtype=float)
        zeros = N.zeros(n, dtype=float)

        painter.save()
        try:
            painter.setClipRect(clip)

            # draw bars
            barpen = s.BarBorder.makeQPenWHide(painter)
            barbrush = s.BarFill.makeQBrushWHide(painter)
            painter.setPen(barpen)
            painter.setBrush(barbrush)

            for i in range(n):
                if vertical:
                    x1 = xaxis.dataToPlotterCoords(widgetposn,
                        N.array([positions[i] - bw / 2]))[0]
                    x2 = xaxis.dataToPlotterCoords(widgetposn,
                        N.array([positions[i] + bw / 2]))[0]
                    y1 = yaxis.dataToPlotterCoords(widgetposn,
                        N.array([zeros[i]]))[0]
                    y2 = yaxis.dataToPlotterCoords(widgetposn,
                        N.array([vals[i]]))[0]
                else:
                    y1 = yaxis.dataToPlotterCoords(widgetposn,
                        N.array([positions[i] - bw / 2]))[0]
                    y2 = yaxis.dataToPlotterCoords(widgetposn,
                        N.array([positions[i] + bw / 2]))[0]
                    x1 = xaxis.dataToPlotterCoords(widgetposn,
                        N.array([zeros[i]]))[0]
                    x2 = xaxis.dataToPlotterCoords(widgetposn,
                        N.array([vals[i]]))[0]

                rect = qt.QRectF(
                    qt.QPointF(min(x1, x2), min(y1, y2)),
                    qt.QPointF(max(x1, x2), max(y1, y2)))
                painter.drawRect(rect)

            # draw cumulative line
            if s.showCumulative and n > 0:
                # scale cumulative to value axis (max val maps to 100%)
                max_val = vals[0] if len(vals) > 0 else 1
                total = vals.sum()
                if total <= 0:
                    total = 1.0  # avoid division by zero
                cum_vals = N.cumsum(vals)

                if vertical:
                    cx = xaxis.dataToPlotterCoords(widgetposn, positions)
                    cy = yaxis.dataToPlotterCoords(widgetposn,
                        cum_vals / total * N.nanmax(vals) * 1.05)
                else:
                    cy = yaxis.dataToPlotterCoords(widgetposn, positions)
                    cx = xaxis.dataToPlotterCoords(widgetposn,
                        cum_vals / total * N.nanmax(vals) * 1.05)

                cumpen = s.CumulativeLine.makeQPenWHide(painter)
                painter.setPen(cumpen)
                painter.setBrush(qt.Qt.BrushStyle.NoBrush)

                path = qt.QPainterPath()
                valid = N.isfinite(cx) & N.isfinite(cy)
                first = True
                for j in range(n):
                    if valid[j]:
                        if first:
                            path.moveTo(cx[j], cy[j])
                            first = False
                        else:
                            path.lineTo(cx[j], cy[j])
                painter.drawPath(path)

                # draw markers on cumulative line
                markerbrush = s.CumulativeMarkerFill.makeQBrushWHide(painter)
                painter.setBrush(markerbrush)
                for j in range(n):
                    if valid[j]:
                        painter.drawEllipse(qt.QPointF(cx[j], cy[j]), 3, 3)

                # 80% threshold line
                if s.showPercentAxis and total > 0:
                    threshold_val = 0.80 * total
                    thresh_y_data = threshold_val / total * N.nanmax(vals) * 1.05
                    dashpen = qt.QPen(qt.QColor(150, 150, 150))
                    dashpen.setStyle(qt.Qt.PenStyle.DashLine)
                    dashpen.setWidthF(1.0)
                    painter.setPen(dashpen)
                    if vertical:
                        ty = yaxis.dataToPlotterCoords(widgetposn,
                            N.array([thresh_y_data]))[0]
                        painter.drawLine(
                            qt.QPointF(widgetposn[0], ty),
                            qt.QPointF(widgetposn[2], ty))
                    else:
                        tx = xaxis.dataToPlotterCoords(widgetposn,
                            N.array([thresh_y_data]))[0]
                        painter.drawLine(
                            qt.QPointF(tx, widgetposn[1]),
                            qt.QPointF(tx, widgetposn[3]))
        finally:
            painter.restore()


document.thefactory.register(Pareto)
