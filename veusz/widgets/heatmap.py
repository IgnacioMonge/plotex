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

"""Annotated heatmap widget — a 2D dataset displayed as colored cells
with optional numeric annotations and row/column labels."""

import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='Heatmap'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

class Heatmap(GenericPlotter):
    """Plot a 2D dataset as an annotated heatmap."""

    typename = 'heatmap'
    allowusercreation = True
    description = _('Annotated heatmap')

    @classmethod
    def addSettings(klass, s):
        GenericPlotter.addSettings(s)

        s.remove('key')

        # data
        s.add(setting.DatasetExtended(
            'data', '',
            dimensions=2,
            descr=_('2D dataset to plot'),
            usertext=_('Dataset')), 0)
        s.add(setting.DatasetOrStr(
            'xlabels', '',
            descr=_('Labels for columns (X axis)'),
            usertext=_('Column labels')), 1)
        s.add(setting.DatasetOrStr(
            'ylabels', '',
            descr=_('Labels for rows (Y axis)'),
            usertext=_('Row labels')), 2)

        # colormap
        s.add(setting.Colormap(
            'colorMap', 'cb-rdbu',
            descr=_('Colormap for cells'),
            usertext=_('Colormap'),
            formatting=True))
        s.add(setting.Bool(
            'colorInvert', False,
            descr=_('Invert colormap'),
            usertext=_('Invert colormap'),
            formatting=True))
        s.add(setting.FloatOrAuto(
            'min', 'Auto',
            descr=_('Minimum value for color scale'),
            usertext=_('Min value')))
        s.add(setting.FloatOrAuto(
            'max', 'Auto',
            descr=_('Maximum value for color scale'),
            usertext=_('Max value')))

        # annotations
        s.add(setting.Bool(
            'showValues', True,
            descr=_('Show numeric values inside cells'),
            usertext=_('Show values'), formatting=True))
        s.add(setting.Str(
            'valueFormat', '%.2f',
            descr=_('Format string for cell values (e.g. %.2f, %.0f, %g)'),
            usertext=_('Value format'), formatting=True))

        # style
        s.add(setting.Int(
            'transparency', 0,
            descr=_('Transparency percentage'),
            usertext=_('Transparency'),
            minval=0, maxval=100,
            formatting=True))
        s.add(setting.Line(
            'CellBorder',
            descr=_('Cell border line'),
            usertext=_('Cell border')),
            pixmap='settings_border')
        s.add(setting.Text(
            'ValueLabel',
            descr=_('Value label font'),
            usertext=_('Value label')),
            pixmap='settings_axislabel')

    @property
    def userdescription(self):
        return "data='%s'" % self.settings.data

    def affectsAxisRange(self):
        s = self.settings
        return ((s.xAxis, 'sx'), (s.yAxis, 'sy'))

    def getRange(self, axis, depname, axrange):
        """Update axis range from data."""
        s = self.settings
        data2d = s.get('data').getData(self.document)
        if data2d is None:
            return

        if depname == 'sx':
            ncols = data2d.data.shape[1]
            axrange[0] = min(axrange[0], 0)
            axrange[1] = max(axrange[1], ncols)
        elif depname == 'sy':
            nrows = data2d.data.shape[0]
            axrange[0] = min(axrange[0], 0)
            axrange[1] = max(axrange[1], nrows)

    def getAxisLabels(self, direction):
        """Provide tick labels for axes."""
        s = self.settings
        doc = self.document
        data2d = s.get('data').getData(doc)
        if data2d is None:
            return (None, None)

        if direction == 'horizontal':
            labeldata = s.get('xlabels').getData(doc, checknull=True)
            if labeldata is None:
                return (None, None)
            ncols = data2d.data.shape[1]
            positions = N.arange(ncols) + 0.5
            return (labeldata, positions)
        else:
            labeldata = s.get('ylabels').getData(doc, checknull=True)
            if labeldata is None:
                return (None, None)
            nrows = data2d.data.shape[0]
            positions = N.arange(nrows) + 0.5
            return (labeldata, positions)

    def dataDraw(self, painter, axes, widgetposn, clip):
        """Draw the heatmap."""
        s = self.settings
        doc = self.document

        data2d = s.get('data').getData(doc)
        if data2d is None:
            return

        data = data2d.data
        nrows, ncols = data.shape

        # axes
        xaxis = axes[0]
        yaxis = axes[1]

        # determine color range
        finite = data[N.isfinite(data)]
        if len(finite) == 0:
            return
        if s.min == 'Auto':
            vmin = float(N.nanmin(finite))
        else:
            vmin = s.min
        if s.max == 'Auto':
            vmax = float(N.nanmax(finite))
        else:
            vmax = s.max
        if vmin == vmax:
            vmax = vmin + 1

        # get colormap (same method as image.py)
        cmap = doc.evaluate.getColormap(s.colorMap, s.colorInvert)

        from ..utils.colormap import getColormapArray
        ncolors = 256
        rgba = getColormapArray(cmap, ncolors)

        borderpen = s.CellBorder.makeQPenWHide(painter)

        # font for values
        font = s.get('ValueLabel').makeQFont(painter)
        painter.setFont(font)
        fm = qt.QFontMetricsF(font)

        alpha_factor = (100 - s.transparency) / 100.0

        for row in range(nrows):
            for col in range(ncols):
                val = data[row, col]
                if not N.isfinite(val):
                    continue

                # cell bounds in data coords: col->col+1, row->row+1
                x0 = xaxis.dataToPlotterCoords(widgetposn, N.array([float(col)]))[0]
                x1 = xaxis.dataToPlotterCoords(widgetposn, N.array([float(col + 1)]))[0]
                y0 = yaxis.dataToPlotterCoords(widgetposn, N.array([float(row)]))[0]
                y1 = yaxis.dataToPlotterCoords(widgetposn, N.array([float(row + 1)]))[0]

                # normalize value to colormap index
                norm = max(0.0, min(1.0, (val - vmin) / (vmax - vmin)))
                ci = int(norm * (ncolors - 1))
                color = qt.QColor(
                    int(rgba[ci][0]), int(rgba[ci][1]),
                    int(rgba[ci][2]), int(rgba[ci][3] * alpha_factor))

                rect = qt.QRectF(
                    qt.QPointF(min(x0, x1), min(y0, y1)),
                    qt.QPointF(max(x0, x1), max(y0, y1)))

                painter.setBrush(qt.QBrush(color))
                painter.setPen(borderpen)
                painter.drawRect(rect)

                # draw value annotation
                if s.showValues:
                    try:
                        text = s.valueFormat % val
                    except (TypeError, ValueError):
                        text = str(val)

                    # auto-contrast text color
                    lum = (color.redF() * 0.299 +
                           color.greenF() * 0.587 +
                           color.blueF() * 0.114)
                    tcolor = qt.QColor(255, 255, 255) if lum < 0.5 else qt.QColor(0, 0, 0)
                    painter.setPen(qt.QPen(tcolor))
                    painter.drawText(
                        rect, int(qt.Qt.AlignmentFlag.AlignCenter), text)

document.thefactory.register(Heatmap)
