#    Copyright (C) 2026 M. Ignacio Monge Garcia
#
#    This file is part of Plotex (fork of Veusz).
#
#    Plotex is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
##############################################################################

"""Polar Trending Plot widget (Critchley 2011 method).

A specialized method comparison plot for trending analysis used in
clinical hemodynamic monitoring.  Each data point represents a pair
of changes (delta_test, delta_ref) plotted in polar coordinates:

  - Distance from center = mean magnitude = (|dTest| + |dRef|) / 2
  - Angle from 12 o'clock = agreement angle =
        atan2(dTest - dRef, dTest + dRef)
  - Perfect agreement = 0 degrees (straight up)

Statistics:
  - Angular bias (mean angle)
  - Radial limits of agreement (mean angle +/- 1.96 * SD)
  - Angular concordance rate: percentage of points within +/-30 deg

Visual elements:
  - Circular grid (concentric circles at regular intervals)
  - Radial grid lines at key angles (0, +/-30, +/-60, +/-90, 180)
  - Data points plotted in polar coordinates
  - Concordance boundary lines at +/-30 degrees (configurable)
  - Angular bias line
  - Radial LOA lines (dashed)
  - Statistics text annotation

Reference:
  Critchley LA, Lee A, Ho AM-H. A critical review of the ability of
  continuous cardiac output monitors to measure trends in cardiac
  output. Anesth Analg 2010;111(5):1180-92.
"""

import math
import numpy as N

from .. import qtall as qt
from .. import document
from .. import setting
from .. import utils

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='PolarTrending'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


# =====================================================================
# Custom sub-settings
# =====================================================================

class _GridLine(setting.Line):
    """Circular grid line style with sensible defaults."""
    def __init__(self, name, **args):
        setting.Line.__init__(self, name, **args)
        self.get('color').newDefault('grey')
        self.get('style').newDefault('dotted')
        self.get('width').newDefault('0.5pt')


class _ConcordanceLine(setting.Line):
    """Concordance boundary line style (solid, coloured)."""
    def __init__(self, name, **args):
        setting.Line.__init__(self, name, **args)
        self.get('color').newDefault('#2196F3')
        self.get('style').newDefault('solid')
        self.get('width').newDefault('1pt')


class _BiasLine(setting.Line):
    """Angular bias line style."""
    def __init__(self, name, **args):
        setting.Line.__init__(self, name, **args)
        self.get('color').newDefault('#E91E63')
        self.get('style').newDefault('solid')
        self.get('width').newDefault('1.5pt')


class _LOALine(setting.Line):
    """Radial limits of agreement line style (dashed)."""
    def __init__(self, name, **args):
        setting.Line.__init__(self, name, **args)
        self.get('color').newDefault('#E91E63')
        self.get('style').newDefault('dashed')
        self.get('width').newDefault('1pt')


class _ConcordanceFill(setting.Brush):
    """Fill brush for concordance zone with high transparency."""
    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)
        self.get('color').newDefault('#2196F3')
        self.get('transparency').newDefault(90)
        self.get('hide').newDefault(True)


# =====================================================================
# Widget
# =====================================================================

class PolarTrending(GenericPlotter):
    """Plot a Polar Trending (Critchley method) chart for trending analysis.

    Each data point represents a pair of changes (delta_test, delta_ref).
    Points are plotted in polar coordinates where distance from center
    is the mean magnitude and angle from 12 o'clock is the agreement
    angle.  The concordance zone, angular bias, and radial limits of
    agreement provide a comprehensive assessment of trending ability.
    """

    typename = 'polartrending'
    allowusercreation = True
    description = _('Polar trending plot (Critchley method)')

    def __init__(self, parent, **args):
        GenericPlotter.__init__(self, parent, **args)

        # Cached computed values
        self._mean_mag = None
        self._agreement_angle = None
        self._angular_bias = None
        self._angular_sd = None
        self._loa_upper = None
        self._loa_lower = None
        self._concordance_rate = None
        self._n = 0
        self._changeset = -1

    @classmethod
    def addSettings(klass, s):
        """Construct list of settings."""
        GenericPlotter.addSettings(s)

        # ---- Data settings ----
        s.add(setting.DatasetExtended(
            'deltaTestData', '',
            descr=_('Changes in test method (delta CO test)'),
            usertext=_('Delta test data')), 0)
        s.add(setting.DatasetExtended(
            'deltaRefData', '',
            descr=_('Changes in reference method (delta CO ref)'),
            usertext=_('Delta ref data')), 1)

        # ---- Marker settings ----
        s.add(setting.Color(
            'color', 'auto',
            descr=_('Master color for markers'),
            usertext=_('Color'), formatting=True), 0)
        s.add(setting.DistancePt(
            'markerSize', '3pt',
            descr=_('Size of scatter markers'),
            usertext=_('Marker size'), formatting=True), 0)
        s.add(setting.Marker(
            'marker', 'circle',
            descr=_('Type of marker to plot'),
            usertext=_('Marker'), formatting=True), 0)

        # ---- Analysis parameters ----
        s.add(setting.Float(
            'concordanceLimit', 30.0,
            minval=1.0, maxval=90.0,
            descr=_('Angular concordance limit in degrees'),
            usertext=_('Concordance limit')))
        s.add(setting.Float(
            'exclusionZone', 0.0,
            minval=0.0,
            descr=_(
                'Exclude points with mean change below this value '
                '(small changes are noisy)'),
            usertext=_('Exclusion zone')))

        # ---- Visibility toggles ----
        s.add(setting.Bool(
            'showGrid', True,
            descr=_('Show circular grid and radial lines'),
            usertext=_('Show grid'), formatting=True))
        s.add(setting.Bool(
            'showConcordanceZone', True,
            descr=_('Show concordance boundary lines'),
            usertext=_('Show concordance zone'), formatting=True))
        s.add(setting.Bool(
            'showConcordanceFill', False,
            descr=_('Fill the concordance zone'),
            usertext=_('Fill concordance zone'), formatting=True))
        s.add(setting.Bool(
            'showBias', True,
            descr=_('Show angular bias line'),
            usertext=_('Show bias'), formatting=True))
        s.add(setting.Bool(
            'showLOA', True,
            descr=_('Show radial limits of agreement'),
            usertext=_('Show LOA'), formatting=True))
        s.add(setting.Bool(
            'showStats', True,
            descr=_('Show statistics text annotation'),
            usertext=_('Show stats'), formatting=True))
        s.add(setting.Bool(
            'showExclusionZone', True,
            descr=_('Show exclusion zone circle'),
            usertext=_('Show exclusion zone'), formatting=True))
        s.add(setting.Bool(
            'showGridLabels', True,
            descr=_('Show numeric labels on the grid circles'),
            usertext=_('Show grid labels'), formatting=True))

        # ---- Stats text position ----
        s.add(setting.Choice(
            'statsPosition',
            ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
            'top-left',
            descr=_('Position of statistics text'),
            usertext=_('Stats position'), formatting=True))

        # ---- Sub-setting groups (line styles, fills) ----
        s.add(_GridLine(
            'GridLine',
            descr=_('Circular grid line style'),
            usertext=_('Grid line')),
            pixmap='settings_plotline')

        s.add(_ConcordanceLine(
            'ConcordanceLine',
            descr=_('Concordance boundary line style'),
            usertext=_('Concordance line')),
            pixmap='settings_plotline')

        s.add(_ConcordanceFill(
            'ConcordanceFill',
            descr=_('Concordance zone fill'),
            usertext=_('Concordance fill')),
            pixmap='settings_bgfill')

        s.add(_BiasLine(
            'BiasLine',
            descr=_('Angular bias line style'),
            usertext=_('Bias line')),
            pixmap='settings_plotline')

        s.add(_LOALine(
            'LOALine',
            descr=_('Radial limits of agreement line style'),
            usertext=_('LOA line')),
            pixmap='settings_plotline')

        s.add(setting.Line(
            'ExclusionLine',
            descr=_('Exclusion zone circle line style'),
            usertext=_('Exclusion line')),
            pixmap='settings_plotline')
        s.ExclusionLine.get('color').newDefault('grey')
        s.ExclusionLine.get('style').newDefault('dashed')
        s.ExclusionLine.get('width').newDefault('0.5pt')

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
        s.MarkerFill.get('color').newDefault(setting.Reference('../color'))

        s.add(setting.Text(
            'Label',
            descr=_('Statistics text font'),
            usertext=_('Stats label')),
            pixmap='settings_axislabel')

    @property
    def userdescription(self):
        """User-friendly description."""
        s = self.settings
        return "dTest='%s', dRef='%s'" % (s.deltaTestData, s.deltaRefData)

    # ==================================================================
    # Data computation (cached)
    # ==================================================================

    def _computePolar(self):
        """Compute polar trending statistics from datasets.

        Results are cached until the document changeset changes.
        """
        d = self.document
        if self._changeset == d.changeset:
            return

        self._changeset = d.changeset
        self._mean_mag = None
        self._agreement_angle = None
        self._angular_bias = None
        self._angular_sd = None
        self._loa_upper = None
        self._loa_lower = None
        self._concordance_rate = None
        self._n = 0

        s = self.settings
        ds_test = s.get('deltaTestData').getData(d)
        ds_ref = s.get('deltaRefData').getData(d)
        if ds_test is None or ds_ref is None:
            return

        delta_test = ds_test.data
        delta_ref = ds_ref.data
        if delta_test is None or delta_ref is None:
            return

        # Truncate to common length
        minlen = min(len(delta_test), len(delta_ref))
        if minlen < 2:
            return
        delta_test = delta_test[:minlen]
        delta_ref = delta_ref[:minlen]

        # Filter NaN / Inf
        finite = N.isfinite(delta_test) & N.isfinite(delta_ref)
        delta_test = delta_test[finite]
        delta_ref = delta_ref[finite]

        if len(delta_test) < 2:
            return

        # Mean magnitude (distance from center)
        mean_mag = (N.abs(delta_test) + N.abs(delta_ref)) / 2.0

        # Agreement angle (0 degrees = perfect agreement, from 12 o'clock)
        # atan2 gives angle from X axis; we rotate so 0 is from Y axis
        agreement_angle = N.degrees(N.arctan2(
            delta_test - delta_ref,
            delta_test + delta_ref))

        # Apply exclusion zone (small changes are noisy)
        exclusion = s.exclusionZone
        if exclusion > 0:
            mask = mean_mag >= exclusion
            mean_mag = mean_mag[mask]
            agreement_angle = agreement_angle[mask]

        if len(mean_mag) < 2:
            return

        # Statistics
        angular_bias = float(N.mean(agreement_angle))
        angular_sd = float(N.std(agreement_angle, ddof=1))
        loa_upper = angular_bias + 1.96 * angular_sd
        loa_lower = angular_bias - 1.96 * angular_sd

        # Angular concordance rate
        conc_limit = s.concordanceLimit
        concordance_rate = (
            float(N.sum(N.abs(agreement_angle) <= conc_limit))
            / len(agreement_angle) * 100.0)

        self._mean_mag = mean_mag
        self._agreement_angle = agreement_angle
        self._angular_bias = angular_bias
        self._angular_sd = angular_sd
        self._loa_upper = loa_upper
        self._loa_lower = loa_lower
        self._concordance_rate = concordance_rate
        self._n = len(mean_mag)

    # ==================================================================
    # Axis range
    # ==================================================================

    def affectsAxisRange(self):
        """This widget provides range information about axes."""
        s = self.settings
        return ((s.xAxis, 'sx'), (s.yAxis, 'sy'))

    def getRange(self, axis, depname, axrange):
        """Provide axis range.

        Both axes need a symmetric range around 0 so the polar circle
        is centred.  We use the maximum mean magnitude as the radius.
        """
        self._computePolar()
        if self._mean_mag is None or len(self._mean_mag) == 0:
            return

        max_mag = float(N.max(self._mean_mag))
        if max_mag <= 0:
            max_mag = 1.0

        # Add some padding (15%) so the circle does not touch the axes
        limit = max_mag * 1.15

        axrange[0] = min(axrange[0], -limit)
        axrange[1] = max(axrange[1], limit)

    # ==================================================================
    # Drawing helpers
    # ==================================================================

    @staticmethod
    def _angleToXY(cx, cy, radius, angle_deg):
        """Convert polar angle (degrees from 12 o'clock, CW positive)
        and radius to screen coordinates.

        Angle 0 = straight up (12 o'clock).
        Positive angles = clockwise.
        """
        rad = math.radians(angle_deg)
        x = cx + radius * math.sin(rad)
        y = cy - radius * math.cos(rad)
        return x, y

    def _drawCircularGrid(self, painter, s, cx, cy, radius, max_mag):
        """Draw concentric circles and radial lines."""

        pen = s.GridLine.makeQPenWHide(painter)
        if pen.style() == qt.Qt.PenStyle.NoPen:
            return
        painter.setPen(pen)
        painter.setBrush(qt.QBrush())

        # Determine nice grid intervals
        n_circles = 4
        if max_mag > 0:
            raw_step = max_mag / n_circles
            if raw_step > 0:
                magnitude = 10 ** math.floor(math.log10(raw_step))
                nice_steps = [1, 2, 2.5, 5, 10]
                step = magnitude
                for ns in nice_steps:
                    candidate = ns * magnitude
                    if candidate >= raw_step:
                        step = candidate
                        break
            else:
                step = max_mag / n_circles
        else:
            step = 0.25

        # Draw concentric circles
        r_val = step
        while r_val <= max_mag * 1.01:
            r_px = r_val / max_mag * radius if max_mag > 0 else 0
            if r_px > 0:
                painter.drawEllipse(qt.QPointF(cx, cy), r_px, r_px)

                # Draw grid label at the top of each circle
                if s.showGridLabels and not s.Label.hide:
                    label_x = cx
                    label_y = cy - r_px - 2
                    font = s.Label.makeQFont(painter)
                    # Use a smaller font for grid labels
                    font.setPointSizeF(font.pointSizeF() * 0.75)
                    painter.setFont(font)
                    textpen = s.Label.makeQPen(painter)
                    painter.setPen(textpen)
                    fm = qt.QFontMetricsF(font)

                    # Format the label value
                    if step >= 1:
                        label_text = '%g' % r_val
                    else:
                        label_text = '%.2g' % r_val
                    tw = fm.horizontalAdvance(label_text)
                    painter.drawText(
                        qt.QPointF(label_x - tw / 2, label_y),
                        label_text)

                    # Restore grid pen for subsequent circles
                    painter.setPen(pen)
            r_val += step

        # Draw radial lines at key angles
        key_angles = [0, 30, -30, 60, -60, 90, -90, 180]
        painter.setPen(pen)
        for angle_deg in key_angles:
            x2, y2 = self._angleToXY(cx, cy, radius, angle_deg)
            painter.drawLine(qt.QPointF(cx, cy), qt.QPointF(x2, y2))

        # Draw angle labels at the rim
        if s.showGridLabels and not s.Label.hide:
            font = s.Label.makeQFont(painter)
            font.setPointSizeF(font.pointSizeF() * 0.7)
            painter.setFont(font)
            textpen = s.Label.makeQPen(painter)
            painter.setPen(textpen)
            fm = qt.QFontMetricsF(font)
            label_radius = radius + 4  # small offset beyond the rim

            for angle_deg in key_angles:
                label_text = '%+d' % angle_deg if angle_deg != 0 else '0'
                label_text += '\u00B0'
                tw = fm.horizontalAdvance(label_text)
                th = fm.height()

                lx, ly = self._angleToXY(cx, cy, label_radius, angle_deg)

                # Adjust alignment based on position
                if angle_deg == 0:
                    lx -= tw / 2
                    ly -= 2
                elif angle_deg == 180:
                    lx -= tw / 2
                    ly += th
                elif angle_deg > 0:
                    # Right side
                    lx += 2
                    ly += th / 3
                else:
                    # Left side
                    lx -= tw + 2
                    ly += th / 3

                painter.drawText(qt.QPointF(lx, ly), label_text)

    def _drawConcordanceZone(self, painter, s, cx, cy, radius):
        """Draw concordance boundary lines at +/- concordanceLimit."""

        conc_limit = s.concordanceLimit

        # Draw fill first (behind lines)
        if s.showConcordanceFill and not s.ConcordanceFill.hide:
            brush = s.ConcordanceFill.makeQBrushWHide(painter)
            if brush.style() != qt.Qt.BrushStyle.NoBrush:
                path = qt.QPainterPath()
                path.moveTo(cx, cy)

                # Arc from -conc_limit to +conc_limit
                # We need to build a wedge shape
                n_segments = 60
                for i in range(n_segments + 1):
                    angle = -conc_limit + (2 * conc_limit) * i / n_segments
                    x, y = self._angleToXY(cx, cy, radius, angle)
                    path.lineTo(x, y)
                path.lineTo(cx, cy)
                path.closeSubpath()

                painter.setPen(qt.QPen(qt.Qt.PenStyle.NoPen))
                painter.setBrush(brush)
                painter.drawPath(path)

        # Draw boundary lines
        pen = s.ConcordanceLine.makeQPenWHide(painter)
        if pen.style() == qt.Qt.PenStyle.NoPen:
            return
        painter.setPen(pen)
        painter.setBrush(qt.QBrush())

        # +limit line
        x2, y2 = self._angleToXY(cx, cy, radius, conc_limit)
        painter.drawLine(qt.QPointF(cx, cy), qt.QPointF(x2, y2))

        # -limit line
        x2, y2 = self._angleToXY(cx, cy, radius, -conc_limit)
        painter.drawLine(qt.QPointF(cx, cy), qt.QPointF(x2, y2))

    def _drawRadialLine(self, painter, cx, cy, radius, angle_deg, lineSettings):
        """Draw a single radial line from center to rim at given angle."""
        pen = lineSettings.makeQPenWHide(painter)
        if pen.style() == qt.Qt.PenStyle.NoPen:
            return
        painter.setPen(pen)
        painter.setBrush(qt.QBrush())
        x2, y2 = self._angleToXY(cx, cy, radius, angle_deg)
        painter.drawLine(qt.QPointF(cx, cy), qt.QPointF(x2, y2))

    def _drawExclusionZone(self, painter, s, cx, cy, radius, max_mag):
        """Draw exclusion zone circle."""
        exclusion = s.exclusionZone
        if exclusion <= 0 or max_mag <= 0:
            return

        pen = s.ExclusionLine.makeQPenWHide(painter)
        if pen.style() == qt.Qt.PenStyle.NoPen:
            return

        r_px = exclusion / max_mag * radius
        if r_px > 0 and r_px < radius:
            painter.setPen(pen)
            painter.setBrush(qt.QBrush())
            painter.drawEllipse(qt.QPointF(cx, cy), r_px, r_px)

    def _drawStats(self, painter, s, posn):
        """Draw statistics text annotation."""
        if s.Label.hide:
            return

        font = s.Label.makeQFont(painter)
        painter.setFont(font)
        textpen = s.Label.makeQPen(painter)
        painter.setPen(textpen)
        fm = qt.QFontMetricsF(font)

        conc_limit = s.concordanceLimit

        lines = []
        lines.append(
            'Angular bias: %.1f\u00B0' % self._angular_bias)
        lines.append(
            'Radial LOA: %.1f\u00B0 to %.1f\u00B0'
            % (self._loa_lower, self._loa_upper))
        lines.append(
            'Concordance (\u00B1%.0f\u00B0): %.1f%%'
            % (conc_limit, self._concordance_rate))
        lines.append('n = %d' % self._n)

        # Measure text block size
        line_height = fm.height()
        max_width = 0
        for line in lines:
            w = fm.horizontalAdvance(line)
            if w > max_width:
                max_width = w

        block_height = line_height * len(lines)
        margin = 8.0

        x1, y1, x2, y2 = posn

        pos = s.statsPosition
        if pos == 'top-left':
            tx = x1 + margin
            ty = y1 + margin + line_height
        elif pos == 'top-right':
            tx = x2 - max_width - margin
            ty = y1 + margin + line_height
        elif pos == 'bottom-left':
            tx = x1 + margin
            ty = y2 - block_height - margin + line_height
        else:
            # bottom-right
            tx = x2 - max_width - margin
            ty = y2 - block_height - margin + line_height

        for i, line in enumerate(lines):
            painter.drawText(
                qt.QPointF(tx, ty + i * line_height),
                line)

    # ==================================================================
    # Main drawing
    # ==================================================================

    def draw(self, parentposn, painthelper, outerbounds=None):
        """Draw the polar trending plot.

        We override draw() instead of dataDraw() because we need to
        draw our own coordinate system (circular grid) that is
        independent of the graph axes.  We still fetch axes so that
        the widget sits properly inside a Graph, but we do NOT use
        axis coordinate transforms for the actual polar plotting.
        """
        posn = self.computeBounds(parentposn, painthelper)

        if self.settings.hide:
            return

        # Fetch axes (required by GenericPlotter contract)
        axes = self.fetchAxes()
        if not axes:
            return

        # Use the plot area for our circular coordinate system
        cliprect = self.clipAxesBounds(axes, posn)

        painter = painthelper.painter(self, posn, clip=cliprect)
        with painter:
            self._drawPolar(painter, posn)

        for c in self.children:
            c.draw(posn, painthelper, outerbounds)

        return posn

    def _drawPolar(self, painter, posn):
        """Core drawing routine for the polar trending plot."""

        s = self.settings

        self._computePolar()
        if self._mean_mag is None:
            return

        mean_mag = self._mean_mag
        agreement_angle = self._agreement_angle

        # Determine plot geometry
        x1, y1, x2, y2 = posn
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        half_w = (x2 - x1) / 2.0
        half_h = (y2 - y1) / 2.0
        radius = min(half_w, half_h) * 0.85  # leave room for labels

        # Maximum magnitude determines the scale
        max_mag = float(N.max(mean_mag)) if len(mean_mag) > 0 else 1.0
        if max_mag <= 0:
            max_mag = 1.0

        # ── 1. Draw circular grid ─────────────────────────────────────
        if s.showGrid:
            self._drawCircularGrid(painter, s, cx, cy, radius, max_mag)

        # ── 2. Draw outer boundary circle ─────────────────────────────
        gridpen = s.GridLine.makeQPenWHide(painter)
        if gridpen.style() != qt.Qt.PenStyle.NoPen:
            # Draw a solid outer circle
            outer_pen = qt.QPen(gridpen)
            outer_pen.setStyle(qt.Qt.PenStyle.SolidLine)
            painter.setPen(outer_pen)
            painter.setBrush(qt.QBrush())
            painter.drawEllipse(qt.QPointF(cx, cy), radius, radius)

        # ── 3. Draw exclusion zone ────────────────────────────────────
        if s.showExclusionZone:
            self._drawExclusionZone(painter, s, cx, cy, radius, max_mag)

        # ── 4. Draw concordance zone ──────────────────────────────────
        if s.showConcordanceZone:
            self._drawConcordanceZone(painter, s, cx, cy, radius)

        # ── 5. Draw angular bias line ─────────────────────────────────
        if s.showBias:
            self._drawRadialLine(
                painter, cx, cy, radius,
                self._angular_bias, s.BiasLine)

        # ── 6. Draw radial LOA lines ──────────────────────────────────
        if s.showLOA:
            self._drawRadialLine(
                painter, cx, cy, radius,
                self._loa_upper, s.LOALine)
            self._drawRadialLine(
                painter, cx, cy, radius,
                self._loa_lower, s.LOALine)

        # ── 7. Draw data points ───────────────────────────────────────
        markersize = s.get('markerSize').convert(painter)

        # Resolve marker color
        painter.setPen(s.MarkerLine.makeQPenWHide(painter))
        painter.setBrush(s.MarkerFill.makeQBrushWHide(painter))

        # Convert polar coords to screen coords
        if len(mean_mag) > 0:
            r_px = mean_mag / max_mag * radius
            angle_rad = N.radians(agreement_angle)
            px_x = cx + r_px * N.sin(angle_rad)
            px_y = cy - r_px * N.cos(angle_rad)

            # Clip to the circular region
            circle_clip = qt.QRectF(
                cx - radius, cy - radius,
                2 * radius, 2 * radius)

            utils.plotMarkers(
                painter, px_x, px_y,
                s.marker, markersize,
                clip=circle_clip)

        # ── 8. Draw statistics text ───────────────────────────────────
        if s.showStats:
            self._drawStats(painter, s, posn)

    # ==================================================================
    # dataDraw (unused, we override draw() directly)
    # ==================================================================

    def dataDraw(self, painter, axes, posn, cliprect):
        """Not used; drawing is handled in draw() override."""
        pass

    # ==================================================================
    # Key symbol
    # ==================================================================

    def drawKeySymbol(self, number, painter, x, y, width, height):
        """Draw the plot symbol in the key/legend."""
        s = self.settings

        xc = x + width / 2
        yc = y + height / 2
        markersize = s.get('markerSize').convert(painter)

        painter.setPen(s.MarkerLine.makeQPenWHide(painter))
        painter.setBrush(s.MarkerFill.makeQBrushWHide(painter))
        utils.plotMarkers(
            painter, N.array([xc]), N.array([yc]),
            s.marker, markersize)


document.thefactory.register(PolarTrending)
