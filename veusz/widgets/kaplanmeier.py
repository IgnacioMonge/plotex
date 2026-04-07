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

"""Kaplan-Meier survival plot widget for Plotex.

Features:
 - Step-function survival curves
 - Censored observation tick marks
 - Optional 95% confidence interval bands (Greenwood's formula)
 - Multiple group stratification with automatic colors
 - Key/legend support for each group
"""

import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from ..helpers.qtloops import addNumpyToPolygonF, plotClippedPolyline

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='KaplanMeier'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


# ── Confidence band fill ─────────────────────────────────────────────

class _ConfFill(setting.PlotterFill):
    """Fill for confidence interval band with sensible defaults."""
    def __init__(self, name, **args):
        setting.PlotterFill.__init__(self, name, **args)
        self.get('color').newDefault('grey')
        self.get('hide').newDefault(False)
        self.get('transparency').newDefault(70)


# ── KM result container ──────────────────────────────────────────────

class _KMResult:
    """Store Kaplan-Meier estimate for one group."""
    __slots__ = (
        'times', 'survival', 'variance',
        'ci_lower', 'ci_upper',
        'censor_times', 'censor_surv',
        'label', 'n_at_risk_times', 'n_at_risk',
    )


# ── Widget ────────────────────────────────────────────────────────────

class KaplanMeier(GenericPlotter):
    """Plot Kaplan-Meier survival curves."""

    typename = 'kaplanmeier'
    allowusercreation = True
    description = _('Plot Kaplan-Meier survival curves')

    def defaultAxisLabels(self):
        """Return default axis labels for this widget type."""
        return {
            'x': 'Time',
            'y': 'Survival Probability (%)',
        }

    @classmethod
    def addSettings(klass, s):
        """Construct list of settings."""
        GenericPlotter.addSettings(s)

        # ── Data settings ────────────────────────────────────────
        s.add(setting.DatasetExtended(
            'timeData', '',
            descr=_('Dataset of times to event or censoring'),
            usertext=_('Time data')), 0)
        s.add(setting.DatasetExtended(
            'eventData', '',
            descr=_('Dataset of event indicators (1=event, 0=censored)'),
            usertext=_('Event data')), 1)
        s.add(setting.DatasetOrStr(
            'groupData', '',
            descr=_('Dataset or string for group stratification (optional)'),
            usertext=_('Group data')), 2)

        # ── Appearance ───────────────────────────────────────────
        s.add(setting.Color(
            'color', 'auto',
            descr=_('Master color for the survival curve'),
            usertext=_('Color'), formatting=True))

        s.add(setting.Bool(
            'showCensored', True,
            descr=_('Show tick marks at censored observations'),
            usertext=_('Show censored'), formatting=True))

        s.add(setting.Marker(
            'censorMarker', 'plus',
            descr=_('Marker for censored observations'),
            usertext=_('Censor marker'), formatting=True))

        s.add(setting.DistancePt(
            'censorSize', '4pt',
            descr=_('Size of censored observation markers'),
            usertext=_('Censor size'), formatting=True))

        # ── Sub-settings (formatting tabs) ───────────────────────
        s.add(setting.Line(
            'PlotLine',
            descr=_('Survival step line style'),
            usertext=_('Plot line')),
            pixmap='settings_plotline')

        s.add(_ConfFill(
            'ConfFill',
            descr=_('Confidence interval band fill'),
            usertext=_('CI band fill')),
            pixmap='settings_plotfillbelow')

        s.add(setting.Line(
            'MarkerLine',
            descr=_('Censored marker border line'),
            usertext=_('Marker line')),
            pixmap='settings_plotmarkerline')

    @property
    def userdescription(self):
        """Friendly description for user."""
        s = self.settings
        return "time='%s', event='%s'" % (s.timeData, s.eventData)

    # ── Axis range ────────────────────────────────────────────────

    def affectsAxisRange(self):
        """This widget provides range information about these axes."""
        s = self.settings
        return ((s.xAxis, 'sx'), (s.yAxis, 'sy'))

    def getRange(self, axis, depname, axrange):
        """Update axis range from data."""
        s = self.settings
        doc = self.document

        if depname == 'sy':
            # Y axis: survival probability 0 to 100%
            axrange[0] = min(axrange[0], 0.0)
            axrange[1] = max(axrange[1], 100.0)
        elif depname == 'sx':
            # X axis: range from time data
            timedata = s.get('timeData').getData(doc)
            if timedata is not None and len(timedata.data) > 0:
                tvals = timedata.data
                finite = tvals[N.isfinite(tvals)]
                if len(finite) > 0:
                    axrange[0] = min(axrange[0], 0.0)
                    axrange[1] = max(axrange[1], float(N.max(finite)))

    # ── Key support ──────────────────────────────────────────────

    def getNumberKeys(self):
        """Return number of key entries."""
        if not self.settings.key:
            return 0
        groups = self._getGroups()
        if groups is None:
            return 0
        return len(groups)

    def getKeyText(self, number):
        """Get key entry for group number."""
        s = self.settings
        groups = self._getGroups()
        if groups is None or number >= len(groups):
            return s.key
        label = groups[number][0]
        if len(groups) == 1:
            return s.key
        return '%s: %s' % (s.key, label) if s.key else str(label)

    def drawKeySymbol(self, number, painter, x, y, width, height):
        """Draw the key symbol (a short horizontal line)."""
        s = self.settings
        yp = y + height / 2

        # determine color for this group
        color = self._groupColor(painter, number)

        pen = s.PlotLine.makeQPen(painter)
        pen.setColor(color)
        painter.setPen(pen)
        painter.setBrush(qt.QBrush())
        painter.drawLine(qt.QPointF(x, yp), qt.QPointF(x + width, yp))

    # ── KM computation ───────────────────────────────────────────

    @staticmethod
    def _computeKM(times, events):
        """Compute Kaplan-Meier survival estimate.

        Parameters
        ----------
        times : 1D array
            Time to event or censoring for each subject.
        events : 1D array
            Event indicator (1 = event, 0 = censored).

        Returns
        -------
        _KMResult with fields populated.
        """
        result = _KMResult()

        # clean data
        mask = N.isfinite(times) & N.isfinite(events)
        t = times[mask]
        e = events[mask].astype(N.int32)

        if len(t) == 0:
            result.times = N.array([0.0])
            result.survival = N.array([1.0])
            result.variance = N.array([0.0])
            result.ci_lower = N.array([1.0])
            result.ci_upper = N.array([1.0])
            result.censor_times = N.array([])
            result.censor_surv = N.array([])
            result.n_at_risk_times = N.array([])
            result.n_at_risk = N.array([])
            return result

        # sort by time
        order = N.argsort(t, kind='stable')
        t = t[order]
        e = e[order]

        # unique event times (where at least one event occurred)
        event_times = N.unique(t[e == 1])

        km_times = [0.0]
        km_surv = [1.0]
        km_greenwood_sum = [0.0]  # cumulative sum for Greenwood

        censor_t = []
        censor_s = []

        at_risk_times = []
        at_risk_n = []

        survival = 1.0
        greenwood_sum = 0.0

        for ti in event_times:
            # number at risk just before ti
            n = int(N.sum(t >= ti))
            # number of events at ti
            d = int(N.sum((t == ti) & (e == 1)))

            if n <= 0:
                continue

            # record at-risk count
            at_risk_times.append(ti)
            at_risk_n.append(n)

            # KM estimate
            survival *= (1.0 - d / n)

            # Greenwood variance accumulation
            if n > d and n > 0:
                greenwood_sum += d / (n * (n - d))

            km_times.append(float(ti))
            km_surv.append(survival)
            km_greenwood_sum.append(greenwood_sum)

        # find censored observations and their survival at censoring time
        censor_mask = (e == 0)
        if N.any(censor_mask):
            ct = t[censor_mask]
            # for each censored time, find survival at that time
            km_t_arr = N.array(km_times)
            km_s_arr = N.array(km_surv)
            for ci in ct:
                # survival is the last KM value at or before this time
                idx = N.searchsorted(km_t_arr, ci, side='right') - 1
                idx = max(0, min(idx, len(km_s_arr) - 1))
                censor_t.append(float(ci))
                censor_s.append(float(km_s_arr[idx]))

        result.times = N.array(km_times, dtype=N.float64)
        result.survival = N.array(km_surv, dtype=N.float64)

        # variance and CI
        gw = N.array(km_greenwood_sum, dtype=N.float64)
        surv = result.survival
        variance = surv * surv * gw
        variance = N.maximum(variance, 0.0)
        se = N.sqrt(variance)
        result.variance = variance
        result.ci_lower = N.clip(surv - 1.96 * se, 0.0, 1.0)
        result.ci_upper = N.clip(surv + 1.96 * se, 0.0, 1.0)

        result.censor_times = N.array(censor_t, dtype=N.float64)
        result.censor_surv = N.array(censor_s, dtype=N.float64)

        result.n_at_risk_times = N.array(at_risk_times, dtype=N.float64)
        result.n_at_risk = N.array(at_risk_n, dtype=N.int32)

        return result

    # ── Group handling ───────────────────────────────────────────

    def _getGroups(self):
        """Split data into groups.

        Returns list of (label, time_array, event_array) or None.
        """
        s = self.settings
        doc = self.document

        timedata = s.get('timeData').getData(doc)
        eventdata = s.get('eventData').getData(doc)

        if timedata is None or eventdata is None:
            return None

        times = timedata.data
        events = eventdata.data

        if len(times) == 0 or len(events) == 0:
            return None

        # check for group data
        groupdata = s.get('groupData').getData(doc, checknull=True)

        # ensure same length across all arrays
        n = min(len(times), len(events))
        if groupdata is not None:
            gvals = groupdata.data if hasattr(groupdata, 'data') else groupdata
            n = min(n, len(gvals))
        times = times[:n]
        events = events[:n]

        if groupdata is not None:
            glabels = gvals[:n]

            # find unique groups preserving order
            seen = {}
            unique_labels = []
            for g in glabels:
                gstr = str(g)
                if gstr not in seen:
                    seen[gstr] = True
                    unique_labels.append(gstr)

            groups = []
            for label in unique_labels:
                mask = N.array([str(g) == label for g in glabels])
                groups.append((label, times[mask], events[mask]))
            return groups
        else:
            # single group
            return [('', times, events)]

    def _groupColor(self, painter, groupindex):
        """Get QColor for a specific group index."""
        s = self.settings
        colorval = s.get('color').val
        if colorval == 'auto':
            return painter.docColor(
                painter.docColorAuto(
                    painter.helper.autoColorIndex((self, groupindex))))
        else:
            return s.get('color').color(painter)

    # ── Step coordinates ─────────────────────────────────────────

    @staticmethod
    def _stepCoords(km_times, km_surv):
        """Convert KM curve to step-function coordinates.

        For each segment [t_i, t_{i+1}], draw horizontal at surv[i],
        then vertical drop at t_{i+1} to surv[i+1].
        """
        n = len(km_times)
        if n < 2:
            return km_times.copy(), km_surv.copy()

        step_x = N.empty(2 * (n - 1) + 1, dtype=N.float64)
        step_y = N.empty(2 * (n - 1) + 1, dtype=N.float64)

        for i in range(n - 1):
            step_x[2 * i] = km_times[i]
            step_y[2 * i] = km_surv[i]
            step_x[2 * i + 1] = km_times[i + 1]
            step_y[2 * i + 1] = km_surv[i]
        step_x[-1] = km_times[-1]
        step_y[-1] = km_surv[-1]

        return step_x, step_y

    # ── Drawing ──────────────────────────────────────────────────

    def dataDraw(self, painter, axes, widgetposn, clip):
        """Plot the Kaplan-Meier curves."""
        s = self.settings

        groups = self._getGroups()
        if groups is None:
            return

        # get axes widgets
        axes = self.parent.getAxes((s.xAxis, s.yAxis))
        if (axes[0] is None or axes[1] is None or
                axes[0].settings.direction != 'horizontal' or
                axes[1].settings.direction != 'vertical'):
            return

        for gi, (label, gtimes, gevents) in enumerate(groups):
            km = self._computeKM(gtimes, gevents)
            color = self._groupColor(painter, gi)
            self._drawOneGroup(
                painter, axes, widgetposn, clip, km, color, gi)

    def _drawOneGroup(self, painter, axes, posn, clip, km, color, gi):
        """Draw a single KM curve with optional CI band and censor marks."""
        s = self.settings

        # extend KM curve to last observation (event or censored)
        km_times = km.times
        km_surv = km.survival * 100.0
        if len(km.censor_times) > 0 and len(km_times) > 0:
            max_censor = float(N.max(km.censor_times))
            if max_censor > km_times[-1]:
                km_times = N.append(km_times, max_censor)
                km_surv = N.append(km_surv, km_surv[-1])

        # compute step coordinates for survival curve (scaled to %)
        step_x, step_y = self._stepCoords(km_times, km_surv)

        # convert to plotter coords
        px = axes[0].dataToPlotterCoords(posn, step_x)
        py = axes[1].dataToPlotterCoords(posn, step_y)

        # ── Confidence band ──────────────────────────────────────
        if not s.ConfFill.hide:
            self._drawConfBand(painter, axes, posn, clip, km, color)

        # ── Step line ────────────────────────────────────────────
        if not s.PlotLine.hide:
            pen = s.PlotLine.makeQPen(painter)
            pen.setColor(color)
            painter.setPen(pen)
            painter.setBrush(qt.QBrush())

            pts = qt.QPolygonF()
            addNumpyToPolygonF(pts, px, py)
            plotClippedPolyline(painter, clip, pts)

        # ── Censored tick marks ──────────────────────────────────
        if s.showCensored and len(km.censor_times) > 0:
            self._drawCensorMarks(
                painter, axes, posn, clip, km, color)

    def _drawConfBand(self, painter, axes, posn, clip, km, color):
        """Draw the confidence interval band as a filled polygon."""
        s = self.settings

        # step coordinates for upper and lower CI (scaled to %)
        upper_x, upper_y = self._stepCoords(km.times, km.ci_upper * 100.0)
        lower_x, lower_y = self._stepCoords(km.times, km.ci_lower * 100.0)

        # convert to plotter coordinates
        ux = axes[0].dataToPlotterCoords(posn, upper_x)
        uy = axes[1].dataToPlotterCoords(posn, upper_y)
        lx = axes[0].dataToPlotterCoords(posn, lower_x)
        ly = axes[1].dataToPlotterCoords(posn, lower_y)

        # build polygon: upper path forward, lower path backward
        poly = qt.QPolygonF()
        addNumpyToPolygonF(poly, ux, uy)
        addNumpyToPolygonF(poly, lx[::-1], ly[::-1])

        # fill using ConfFill settings but override color to match group
        # use direct QPainter filling with transparency
        fillcolor = qt.QColor(color)
        trans = s.ConfFill.transparency if hasattr(s.ConfFill, 'transparency') else 70
        fillcolor.setAlphaF((100 - trans) / 100.0)

        painter.save()
        painter.setPen(qt.QPen(qt.Qt.PenStyle.NoPen))
        painter.setBrush(qt.QBrush(fillcolor))

        # clip the polygon
        clipped = qt.QPolygonF()
        utils.polygonClip(poly, clip, clipped)
        path = qt.QPainterPath()
        path.addPolygon(clipped)
        painter.drawPath(path)
        painter.restore()

    def _drawCensorMarks(self, painter, axes, posn, clip, km, color):
        """Draw censored observation markers on the survival curve."""
        s = self.settings

        cx = axes[0].dataToPlotterCoords(posn, km.censor_times)
        cy = axes[1].dataToPlotterCoords(posn, km.censor_surv * 100.0)

        markersize = s.get('censorSize').convert(painter)

        # set pen for marker
        if not s.MarkerLine.hide:
            pen = s.MarkerLine.makeQPen(painter)
            pen.setColor(color)
        else:
            pen = qt.QPen(color)
            pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(qt.QBrush())

        utils.plotMarkers(
            painter, cx, cy, s.censorMarker, markersize, clip=clip)


# allow the factory to instantiate a KaplanMeier
document.thefactory.register(KaplanMeier)
