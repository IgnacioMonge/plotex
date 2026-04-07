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

"""Pie and donut chart widget."""

import math
import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from .widget import Widget
from . import controlgraph

def _(text, disambiguation=None, context='PieChart'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

class _SliceFill(setting.Brush):
    """Fill for pie slices."""
    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)

class PieChart(Widget):
    """Pie and donut chart widget."""

    typename = 'piechart'
    allowusercreation = True
    description = _('Pie or donut chart')

    @classmethod
    def addSettings(klass, s):
        Widget.addSettings(s)

        # data
        s.add(setting.DatasetExtended(
            'values', '',
            descr=_('Dataset or list of values for slices'),
            usertext=_('Values')), 0)
        s.add(setting.DatasetOrStr(
            'labels', '',
            descr=_('Dataset or string for slice labels'),
            usertext=_('Labels')), 1)

        # layout
        s.add(setting.Distance(
            'leftMargin', '0.5cm',
            descr=_('Left margin'),
            usertext=_('Left margin'), formatting=True))
        s.add(setting.Distance(
            'rightMargin', '0.5cm',
            descr=_('Right margin'),
            usertext=_('Right margin'), formatting=True))
        s.add(setting.Distance(
            'topMargin', '0.5cm',
            descr=_('Top margin'),
            usertext=_('Top margin'), formatting=True))
        s.add(setting.Distance(
            'bottomMargin', '0.5cm',
            descr=_('Bottom margin'),
            usertext=_('Bottom margin'), formatting=True))

        # pie options
        s.add(setting.Float(
            'innerRadius', 0.0,
            minval=0.0, maxval=0.95,
            descr=_('Inner radius fraction (0 = pie, >0 = donut)'),
            usertext=_('Inner radius'), formatting=True))
        s.add(setting.Float(
            'startAngle', 90.0,
            descr=_('Start angle in degrees (0 = right, 90 = top)'),
            usertext=_('Start angle'), formatting=True))
        s.add(setting.Bool(
            'clockwise', True,
            descr=_('Draw slices clockwise'),
            usertext=_('Clockwise'), formatting=True))
        s.add(setting.Float(
            'explode', 0.0,
            minval=0.0, maxval=0.5,
            descr=_('Explode slices outward (fraction of radius)'),
            usertext=_('Explode'), formatting=True))

        # grouping
        s.add(setting.Int(
            'maxSlices', 12,
            minval=2, maxval=100,
            descr=_('Maximum slices before grouping smallest into "Other"'),
            usertext=_('Max slices'), formatting=True))
        s.add(setting.Float(
            'minPercent', 2.0,
            minval=0.0, maxval=50.0,
            descr=_('Slices below this percentage are grouped into "Other"'),
            usertext=_('Min percent'), formatting=True))

        # labels
        s.add(setting.Bool(
            'showLabels', True,
            descr=_('Show slice labels'),
            usertext=_('Show labels'), formatting=True))
        s.add(setting.Bool(
            'showPercent', True,
            descr=_('Show percentage on each slice'),
            usertext=_('Show percent'), formatting=True))
        s.add(setting.Bool(
            'showValues', False,
            descr=_('Show actual values on each slice'),
            usertext=_('Show values'), formatting=True))
        s.add(setting.Str(
            'valueFormat', '%.1f',
            descr=_('Format string for values (e.g. %.1f, %.0f)'),
            usertext=_('Value format'), formatting=True))
        s.add(setting.Choice(
            'labelPosition',
            ('outside', 'inside'), 'outside',
            descr=_('Position of labels'),
            usertext=_('Label position'), formatting=True))

        # palette
        s.add(setting.ChoiceOrMore(
            'fillPalette',
            ['cb-set1', 'cb-set2', 'cb-dark2', 'cb-paired',
             'npg', 'nejm', 'lancet', 'jama', 'aaas', 'okabe-ito',
             'single color'],
            'cb-set1',
            descr=_('Color palette for slices'),
            usertext=_('Fill palette'), formatting=True))

        # style
        s.add(_SliceFill(
            'Fill',
            descr=_('Slice fill (used with single color)'),
            usertext=_('Slice fill')),
            pixmap='settings_bgfill')
        s.add(setting.Line(
            'Border',
            descr=_('Slice border line'),
            usertext=_('Slice border')),
            pixmap='settings_border')
        s.add(setting.GraphBrush(
            'Background',
            descr=_('Background fill'),
            usertext=_('Background')),
            pixmap='settings_bgfill')
        s.add(setting.Text(
            'Label',
            descr=_('Label font'),
            usertext=_('Label')),
            pixmap='settings_axislabel')

    @classmethod
    def allowedParentTypes(klass):
        from . import page, grid
        return (page.Page, grid.Grid)

    @property
    def userdescription(self):
        s = self.settings
        return "values='%s'" % s.values

    def getMargins(self, painthelper):
        s = self.settings
        return (
            s.get('leftMargin').convert(painthelper),
            s.get('topMargin').convert(painthelper),
            s.get('rightMargin').convert(painthelper),
            s.get('bottomMargin').convert(painthelper),
        )

    def _getSliceColor(self, painter, index, nslices):
        """Get color for slice at given index."""
        s = self.settings
        palette = s.fillPalette
        if palette != 'single color':
            from ..utils.colormap import getColormapArray
            cmap = self.document.evaluate.colormaps.get(palette)
            if cmap is not None:
                arr = N.array(cmap)
                is_step = len(arr) > 0 and arr[0][0] < 0
                ncolors = (len(arr) - 1) if is_step else max(len(arr), 1)
                rgba = getColormapArray(cmap, ncolors)
                ci = index % ncolors
                color = qt.QColor(
                    int(rgba[ci][0]), int(rgba[ci][1]),
                    int(rgba[ci][2]), int(rgba[ci][3]))
            else:
                color = s.Fill.makeQBrush(painter).color()
        else:
            color = s.Fill.makeQBrush(painter).color()

        if s.Fill.transparency > 0:
            color.setAlphaF((100 - s.Fill.transparency) / 100.)
        return color

    def draw(self, parentposn, phelper, outerbounds=None):
        """Draw the pie/donut chart."""

        s = self.settings
        bounds = self.computeBounds(parentposn, phelper)
        maxbounds = self.computeBounds(parentposn, phelper, withmargin=False)

        if s.hide:
            return bounds

        painter = phelper.painter(self, bounds)
        with painter:
            # background
            bgpath = qt.QPainterPath()
            bgpath.addRect(qt.QRectF(
                qt.QPointF(bounds[0], bounds[1]),
                qt.QPointF(bounds[2], bounds[3])))
            utils.brushExtFillPath(
                painter, s.Background, bgpath)

            # get data
            doc = self.document
            valdata = s.get('values').getData(doc)
            if valdata is None:
                return bounds
            raw_values = valdata.data
            valid = N.isfinite(raw_values) & (raw_values > 0)
            raw_values = raw_values[valid]
            if len(raw_values) == 0:
                return bounds

            # get labels — filter with same mask as values
            labeldata = s.get('labels').getData(doc, checknull=True)
            if labeldata is not None:
                all_labels = list(labeldata)
                # trim to value length and apply same validity mask
                n = min(len(all_labels), len(valid))
                raw_labels = [all_labels[i] for i in range(n) if valid[i]]
            else:
                raw_labels = None

            # group small slices into "Other"
            total = N.sum(raw_values)
            fracs = raw_values / total * 100
            max_slices = s.maxSlices
            min_pct = s.minPercent

            # sort by value descending for grouping
            order = N.argsort(-raw_values)
            values = []
            labels = []
            other_val = 0.0
            for idx in order:
                if (len(values) < max_slices - 1 and
                        fracs[idx] >= min_pct):
                    values.append(raw_values[idx])
                    if raw_labels and idx < len(raw_labels):
                        labels.append(str(raw_labels[idx]))
                    else:
                        labels.append('')
                else:
                    other_val += raw_values[idx]

            if other_val > 0:
                values.append(other_val)
                labels.append(_('Other'))

            values = N.array(values)

            # compute pie geometry
            cx = (bounds[0] + bounds[2]) / 2
            cy = (bounds[1] + bounds[3]) / 2
            w = bounds[2] - bounds[0]
            h = bounds[3] - bounds[1]

            # leave room for outside labels
            if (s.showLabels or s.showPercent) and s.labelPosition == 'outside':
                margin = min(w, h) * 0.18
            else:
                margin = min(w, h) * 0.02
            radius = min(w, h) / 2 - margin
            if radius <= 0:
                return bounds
            inner_r = radius * s.innerRadius

            total = N.sum(values)
            fractions = values / total

            # Qt angles are in 1/16th degree, measured counterclockwise from 3 o'clock
            start_angle_deg = s.startAngle
            direction = -1 if s.clockwise else 1

            borderpen = s.Border.makeQPenWHide(painter)

            # font for labels
            font = s.get('Label').makeQFont(painter)
            painter.setFont(font)
            fm = qt.QFontMetricsF(font)
            labelcolor = s.get('Label').makeQPen(painter).color()

            nslices = len(values)
            current_angle = start_angle_deg

            for i in range(nslices):
                span = fractions[i] * 360.0
                if span < 0.01:
                    current_angle += direction * span
                    continue

                # explode offset
                if s.explode > 0:
                    mid_angle = current_angle + direction * span / 2
                    mid_rad = math.radians(mid_angle)
                    ex = s.explode * radius * math.cos(mid_rad)
                    ey = -s.explode * radius * math.sin(mid_rad)
                else:
                    ex, ey = 0, 0

                # build slice path
                slice_cx = cx + ex
                slice_cy = cy + ey

                path = qt.QPainterPath()
                outer_rect = qt.QRectF(
                    slice_cx - radius, slice_cy - radius,
                    2 * radius, 2 * radius)

                if inner_r > 0:
                    # donut: outer arc + inner arc (reverse)
                    inner_rect = qt.QRectF(
                        slice_cx - inner_r, slice_cy - inner_r,
                        2 * inner_r, 2 * inner_r)
                    # Qt uses 1/16 degree, counterclockwise
                    qt_start = int(current_angle * 16)
                    qt_span = int(direction * span * 16)
                    path.arcMoveTo(outer_rect, current_angle)
                    path.arcTo(outer_rect, current_angle, direction * span)
                    # reverse arc on inner
                    end_angle = current_angle + direction * span
                    path.arcTo(inner_rect, end_angle, -direction * span)
                    path.closeSubpath()
                else:
                    # pie: move to center, arc, back to center
                    path.moveTo(slice_cx, slice_cy)
                    path.arcTo(outer_rect, current_angle, direction * span)
                    path.closeSubpath()

                # fill slice
                color = self._getSliceColor(painter, i, nslices)
                painter.setBrush(qt.QBrush(color))
                painter.setPen(borderpen)
                painter.drawPath(path)

                # draw labels
                if s.showLabels or s.showPercent or s.showValues:
                    mid_angle = current_angle + direction * span / 2
                    mid_rad = math.radians(mid_angle)

                    parts = []
                    if s.showLabels and labels and i < len(labels):
                        parts.append(str(labels[i]))
                    if s.showPercent:
                        parts.append('%.1f%%' % (fractions[i] * 100))
                    if s.showValues:
                        parts.append(s.valueFormat % values[i])
                    text = '\n'.join(parts)

                    if s.labelPosition == 'outside':
                        lr = radius + margin * 0.4
                        lx = slice_cx + lr * math.cos(mid_rad)
                        ly = slice_cy - lr * math.sin(mid_rad)

                        # alignment based on which side
                        if math.cos(mid_rad) >= 0:
                            align = qt.Qt.AlignmentFlag.AlignLeft
                        else:
                            align = qt.Qt.AlignmentFlag.AlignRight
                        align |= qt.Qt.AlignmentFlag.AlignVCenter

                        tr = fm.boundingRect(
                            qt.QRectF(-500, -500, 1000, 1000),
                            int(align), text)
                        tr.moveCenter(qt.QPointF(lx, ly))
                        if math.cos(mid_rad) >= 0:
                            tr.moveLeft(lx)
                        else:
                            tr.moveRight(lx)

                        painter.setPen(qt.QPen(labelcolor))
                        painter.drawText(tr, int(align), text)
                    else:
                        # inside: place at midpoint of slice
                        if inner_r > 0:
                            lr = (radius + inner_r) / 2
                        else:
                            lr = radius * 0.6
                        lx = slice_cx + lr * math.cos(mid_rad)
                        ly = slice_cy - lr * math.sin(mid_rad)

                        align = (qt.Qt.AlignmentFlag.AlignCenter)
                        tr = fm.boundingRect(
                            qt.QRectF(-500, -500, 1000, 1000),
                            int(align), text)
                        tr.moveCenter(qt.QPointF(lx, ly))

                        # auto-contrast text color
                        lum = color.redF()*0.299 + color.greenF()*0.587 + color.blueF()*0.114
                        tcolor = qt.QColor(255, 255, 255) if lum < 0.5 else qt.QColor(0, 0, 0)
                        painter.setPen(qt.QPen(tcolor))
                        painter.drawText(tr, int(align), text)

                current_angle += direction * span

        # controls for adjusting margins
        phelper.setControlGraph(self, [
            controlgraph.ControlMarginBox(self, bounds, maxbounds, phelper)])

        return bounds

    def updateControlItem(self, cgi):
        """Graph resized or moved."""
        cgi.setWidgetMargins()

document.thefactory.register(PieChart)
