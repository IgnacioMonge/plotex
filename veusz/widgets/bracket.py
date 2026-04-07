##############################################################################
"""Bracket connector widget for statistical annotations.

Draws a bracket between two group positions with end caps and a
centered text label. Common in scientific publications for p-values.

The bracket automatically discovers sibling plotters (boxplot, bar,
violin) and snaps to their group positions. The user specifies
group indices (1-based), not pixel coordinates.

Design follows geom_bracket (ggpubr/R) and statannotations (Python):
 - Group indices for X (auto-centers on each group)
 - Y position in data coordinates or Auto (above the data)
 - Tip length as fraction of y-axis range
 - Step increase for stacking multiple brackets
"""

import numpy as N

from .. import document
from .. import setting
from .. import utils
from .. import qtall as qt

from . import widget
from . import controlgraph

def _(text, disambiguation=None, context='Bracket'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

class BracketConnector(widget.Widget):
    """Draw a bracket between two group positions with a label."""

    typename = 'bracket'
    description = _('Bracket connector for annotations')
    allowusercreation = True
    isaxis = False
    isplotter = True  # participate in axis range system

    @classmethod
    def allowedParentTypes(klass):
        from . import page, graph
        return (graph.Graph, page.Page)

    @classmethod
    def addSettings(klass, s):
        """Construct list of settings."""
        widget.Widget.addSettings(s)

        # ── Position ──────────────────────────────────────────
        s.add( setting.Int(
            'groupLeft', 1,
            minval=1, maxval=100,
            descr=_('Left group index (1-based)'),
            usertext=_('Left group')), 0 )
        s.add( setting.Int(
            'groupRight', 2,
            minval=1, maxval=100,
            descr=_('Right group index (1-based)'),
            usertext=_('Right group')), 1 )
        s.add( setting.FloatOrAuto(
            'yPosition', 'Auto',
            descr=_(
                'Y position in data coordinates. '
                'Auto = above the tallest data point'),
            usertext=_('Y position')), 2 )
        s.add( setting.Axis(
            'xAxis', 'x', 'horizontal',
            descr=_('Name of X-axis to use'),
            usertext=_('X axis')) )
        s.add( setting.Axis(
            'yAxis', 'y', 'vertical',
            descr=_('Name of Y-axis to use'),
            usertext=_('Y axis')) )

        # ── Label ─────────────────────────────────────────────
        s.add( setting.Str(
            'label', '***',
            descr=_('Label (e.g. ***, p = 0.003, ns)'),
            usertext=_('Label')), 3 )

        # ── Bracket geometry ──────────────────────────────────
        s.add( setting.Choice(
            'capDirection',
            ('down', 'up', 'both', 'none'), 'down',
            descr=_('Direction of end caps'),
            usertext=_('Caps'),
            formatting=True) )
        s.add( setting.Float(
            'tipLength', 3,
            descr=_(
                'Cap height as % of Y-axis range'),
            usertext=_('Tip length %'),
            formatting=True) )
        s.add( setting.Float(
            'stepIncrease', 0,
            descr=_(
                'Shift bracket upward by % of Y range '
                '(for stacking multiple brackets)'),
            usertext=_('Step increase %'),
            formatting=True) )
        s.add( setting.Float(
            'bracketShorten', 0,
            descr=_(
                'Shorten bracket width from each end (%)'),
            usertext=_('Shorten %'),
            formatting=True) )
        s.add( setting.DistancePt(
            'labelGap', '2pt',
            descr=_('Gap between bracket and label'),
            usertext=_('Label gap'),
            formatting=True) )

        s.add( setting.Float(
            'labelOffset', 0,
            descr=_('Vertical offset of label from bracket line '
                     '(% of Y range, negative = above)'),
            usertext=_('Label offset %'),
            formatting=True) )
        s.add( setting.Color(
            'labelBackground', 'white',
            descr=_('Background color behind label (use "transparent" for none)'),
            usertext=_('Label background'),
            formatting=True) )

        # ── Style ─────────────────────────────────────────────
        s.add( setting.Line(
            'Line',
            descr=_('Bracket line'),
            usertext=_('Line')),
            pixmap='settings_plotline' )
        s.add( setting.Text(
            'Text',
            descr=_('Label text'),
            usertext=_('Text')),
            pixmap='settings_axislabel' )

    @property
    def userdescription(self):
        s = self.settings
        return "groups %d-%d, '%s'" % (s.groupLeft, s.groupRight, s.label)

    def _findGroupPositions(self):
        """Find X positions of data groups from sibling plotters.

        Scans sibling widgets (boxplot, violin, bar) that share
        the same X axis for their group positions and returns a
        sorted array of unique positions in data coordinates.
        """
        parent = self.parent
        if parent is None:
            return None

        s = self.settings
        my_xaxis = s.xAxis
        all_posns = []
        for child in parent.children:
            if child is self:
                continue
            # only consider siblings on the same X axis
            child_xaxis = getattr(getattr(child, 'settings', None),
                                  'xAxis', None)
            if child_xaxis is not None and child_xaxis != my_xaxis:
                continue
            if hasattr(child, 'getPosns'):
                try:
                    posns = child.getPosns()
                    if posns is not None and len(posns) > 0:
                        all_posns.extend(posns.tolist())
                except Exception:
                    pass

        if not all_posns:
            return None

        return N.array(sorted(set(all_posns)))

    def _getDataYRange(self):
        """Get Y data range from sibling plotters that share the same Y axis."""
        parent = self.parent
        if parent is None:
            return None, None

        ymin = N.inf
        ymax = -N.inf
        s = self.settings
        my_yaxis = s.yAxis

        for child in parent.children:
            if child is self or not hasattr(child, 'getRange'):
                continue
            # only consider siblings on the same Y axis
            child_yaxis = getattr(getattr(child, 'settings', None),
                                  'yAxis', None)
            if child_yaxis is not None and child_yaxis != my_yaxis:
                continue
            try:
                r = [N.inf, -N.inf]
                child.getRange(None, 'sy', r)
                if N.isfinite(r[0]):
                    ymin = min(ymin, r[0])
                if N.isfinite(r[1]):
                    ymax = max(ymax, r[1])
            except Exception:
                pass

        if not N.isfinite(ymin) or not N.isfinite(ymax):
            return None, None
        return ymin, ymax

    def _computeBracketY(self):
        """Compute the Y data value the bracket needs (top of bracket + label).

        Used both by getRange (to extend axis) and draw (to position).
        """
        s = self.settings
        ydata_min, ydata_max = self._getDataYRange()
        if ydata_min is None:
            return None

        yrange_data = abs(ydata_max - ydata_min)
        if yrange_data < 1e-15:
            yrange_data = abs(ydata_max) * 0.1 if ydata_max != 0 else 1.0

        tip_frac = s.tipLength / 100.0
        margin_frac = 0.02

        # bracket bar position: above data + tip clearance + margin
        if isinstance(s.yPosition, str) and s.yPosition.lower() == 'auto':
            y_bar = ydata_max + (tip_frac + margin_frac) * yrange_data
        else:
            y_bar = float(s.yPosition)

        # step increase
        y_bar += (s.stepIncrease / 100.0) * yrange_data

        # top of bracket = bar + label space (~5% for text)
        y_top = y_bar + yrange_data * 0.05

        return y_top

    # ── Axis range integration ───────────────────────────────

    def getAxesNames(self):
        """Return axis names this widget uses."""
        s = self.settings
        return (s.xAxis, s.yAxis)

    def lookupAxis(self, axname):
        """Resolve axis name to axis widget."""
        s = self.settings
        if not hasattr(self.parent, 'getAxes'):
            return None
        axes = self.parent.getAxes((s.xAxis, s.yAxis))
        if axname == s.xAxis:
            return axes[0]
        if axname == s.yAxis:
            return axes[1]
        return None

    def affectsAxisRange(self):
        """Report that we affect the Y axis range."""
        s = self.settings
        return ((s.yAxis, 'bracket_y'),)

    def requiresAxisRange(self):
        """We don't require axis range info."""
        return ()

    # bracket can extend fixed-max axes
    canExtendFixedAxis = True

    def getRange(self, axis, depname, axrange):
        """Extend Y axis range to include bracket + label.
        Only updates axrange — never mutates axis settings."""
        if depname == 'bracket_y':
            y_top = self._computeBracketY()
            if y_top is not None:
                axrange[1] = max(axrange[1], y_top)

    def setupAutoColor(self, painter):
        """No-op: brackets don't use auto colors."""
        pass

    def getAxisLabels(self, direction):
        """Brackets have no axis labels."""
        return (None, None)

    def draw(self, posn, phelper, outerbounds=None):
        """Draw the bracket."""

        if phelper is None:
            return

        s = self.settings
        d = self.document

        if s.hide:
            return

        # get axes
        if not hasattr(self.parent, 'getAxes'):
            return
        axes = self.parent.getAxes((s.xAxis, s.yAxis))
        if axes[0] is None or axes[1] is None:
            return

        xaxis = axes[0]
        yaxis = axes[1]

        # find group positions from sibling plotters
        group_posns = self._findGroupPositions()
        if group_posns is None or len(group_posns) == 0:
            # fallback: use group index as data coordinate
            group_posns = N.arange(1, max(s.groupLeft, s.groupRight) + 1,
                                   dtype=N.float64)

        # get X positions for left and right groups (1-based index)
        il = s.groupLeft - 1
        ir = s.groupRight - 1
        if il < 0 or il >= len(group_posns):
            il = 0
        if ir < 0 or ir >= len(group_posns):
            ir = min(1, len(group_posns) - 1)

        x_left_data = group_posns[il]
        x_right_data = group_posns[ir]

        # try to get plotter-coord bar centres from a sibling bar widget
        x1 = x2 = None
        for child in self.parent.children:
            if hasattr(child, 'getBarPlotterEdges'):
                edges_l = child.getBarPlotterEdges(il, axes, posn)
                edges_r = child.getBarPlotterEdges(ir, axes, posn)
                if edges_l is not None and edges_r is not None:
                    x1 = float((edges_l[0] + edges_l[1]) / 2)  # centre
                    x2 = float((edges_r[0] + edges_r[1]) / 2)  # centre
                break

        # fallback: convert data coords to plotter coords
        if x1 is None:
            xplt = xaxis.dataToPlotterCoords(
                posn, N.array([x_left_data, x_right_data]))
            x1 = float(xplt[0])
            x2 = float(xplt[1])

        # Y axis range (data coords)
        ydata_min, ydata_max = self._getDataYRange()
        if ydata_min is not None and ydata_max is not None:
            yrange_data = abs(ydata_max - ydata_min)
        else:
            pr = yaxis.plottedrange
            if pr is not None and len(pr) >= 2:
                yrange_data = abs(pr[1] - pr[0])
            else:
                yrange_data = 1.0

        # determine Y position
        tip_frac = s.tipLength / 100.0
        margin_frac = 0.02
        if isinstance(s.yPosition, str) and s.yPosition.lower() == 'auto':
            # auto: bar is above data + tip clearance + margin
            # so that tips point down but don't overlap with data
            if ydata_max is not None:
                y_data = ydata_max + (tip_frac + margin_frac) * yrange_data
            elif pr is not None:
                y_data = pr[1]
            else:
                y_data = 1.0
        else:
            y_data = float(s.yPosition)

        # apply step increase (percentage of data range)
        y_data += (s.stepIncrease / 100.0) * yrange_data

        # convert Y to plotter coords
        yplt = yaxis.dataToPlotterCoords(posn, N.array([y_data]))
        ybar = float(yplt[0])

        # tip height: percentage of range → plotter pixels
        y_tip_data = y_data + (s.tipLength / 100.0) * yrange_data
        y_tip_plt = float(yaxis.dataToPlotterCoords(
            posn, N.array([y_tip_data]))[0])
        tip_px = abs(y_tip_plt - ybar)

        # apply bracket shorten (percentage → fraction)
        shorten = max(min(s.bracketShorten / 100.0, 0.4), 0.0)
        if shorten > 0:
            dx = (x2 - x1) * shorten
            x1 += dx
            x2 -= dx

        # expand bounds for click detection
        margin = max(tip_px, 10) + 5
        expanded = (
            min(posn[0], x1 - 5),
            min(posn[1], ybar - margin - 20),
            max(posn[2], x2 + 5),
            max(posn[3], ybar + margin + 20))

        hit_h = max(tip_px, 6) + 4

        painter = phelper.painter(self, expanded)
        with painter:
            # invisible hit area for click detection
            painter.setPen(qt.Qt.PenStyle.NoPen)
            painter.setBrush(qt.QBrush(qt.QColor(0, 0, 0, 1)))
            painter.drawRect(qt.QRectF(
                qt.QPointF(x1, ybar - hit_h),
                qt.QPointF(x2, ybar + hit_h)))

            pen = s.Line.makeQPenWHide(painter)
            pen.setCapStyle(qt.Qt.PenCapStyle.SquareCap)
            pen.setJoinStyle(qt.Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(qt.Qt.BrushStyle.NoBrush)

            labelgap = s.get('labelGap').convert(painter)
            capdir = s.capDirection

            # draw bracket as a single continuous path so joins are clean
            path = qt.QPainterPath()
            if capdir == 'down':
                path.moveTo(x1, ybar + tip_px)
                path.lineTo(x1, ybar)
                path.lineTo(x2, ybar)
                path.lineTo(x2, ybar + tip_px)
            elif capdir == 'up':
                path.moveTo(x1, ybar - tip_px)
                path.lineTo(x1, ybar)
                path.lineTo(x2, ybar)
                path.lineTo(x2, ybar - tip_px)
            elif capdir == 'both':
                # left cap (up + down)
                path.moveTo(x1, ybar - tip_px)
                path.lineTo(x1, ybar + tip_px)
                path.moveTo(x1, ybar)
                path.lineTo(x2, ybar)
                # right cap (up + down)
                path.moveTo(x2, ybar - tip_px)
                path.lineTo(x2, ybar + tip_px)
            else:
                # no caps
                path.moveTo(x1, ybar)
                path.lineTo(x2, ybar)
            painter.drawPath(path)

            # label centered ON the bracket line with background
            text = s.label
            if text:
                font = s.get('Text').makeQFont(painter)
                textpen = s.get('Text').makeQPen(painter)

                lx = (x1 + x2) / 2
                # apply label offset (% of Y axis range → pixels)
                offset_px = 0
                if s.labelOffset != 0 and axes[1] is not None:
                    pr = axes[1].plottedrange
                    if pr is not None and len(pr) >= 2:
                        yrange = abs(pr[1] - pr[0])
                        offset_data = s.labelOffset / 100.0 * yrange
                        # convert data offset to pixel offset
                        y0 = axes[1].dataToPlotterCoords(
                            posn, N.array([0.]))[0]
                        y1 = axes[1].dataToPlotterCoords(
                            posn, N.array([offset_data]))[0]
                        offset_px = y1 - y0
                ly = ybar + offset_px

                r = utils.Renderer(
                    painter, font, lx, ly, text,
                    0, 0, 0, doc=d)

                tbounds = r.getBounds()

                # draw background rectangle behind text
                pad = labelgap
                bgrect = qt.QRectF(
                    qt.QPointF(tbounds[0] - pad, tbounds[1] - pad),
                    qt.QPointF(tbounds[2] + pad, tbounds[3] + pad))
                bgcol = s.labelBackground
                if bgcol != 'transparent':
                    painter.setPen(qt.Qt.PenStyle.NoPen)
                    qcol = d.evaluate.colors.get(bgcol)
                    painter.setBrush(qt.QBrush(qcol))
                    painter.drawRect(bgrect)

                # draw the text
                painter.setPen(textpen)
                r.render()

                # expand state bounds
                state = phelper.states[(self, 0)]
                sb = state.bounds
                state.bounds = (
                    min(sb[0], tbounds[0] - pad),
                    min(sb[1], tbounds[1] - pad),
                    max(sb[2], tbounds[2] + pad),
                    max(sb[3], tbounds[3] + pad))

        # selection feedback: dashed rectangle around the bracket
        cgi = controlgraph.ControlMovableBox(
            self,
            [min(x1, x2) - 2, ybar - hit_h,
             max(x1, x2) + 2, ybar + hit_h],
            phelper,
            crosspos=((x1 + x2) / 2, ybar))
        cgi.labelpt = ((x1 + x2) / 2, ybar)
        cgi.widgetposn = posn
        cgi.index = 0
        phelper.setControlGraph(self, [cgi])

    def updateControlItem(self, cgi):
        """Update bracket Y position when dragged (X stays on groups)."""
        s = self.settings

        if not hasattr(self.parent, 'getAxes'):
            return
        axes = self.parent.getAxes((s.xAxis, s.yAxis))
        if axes[1] is None:
            return

        # convert new plotter Y position to data coords
        new_yplt = cgi.deltacrosspos[1] + cgi.posn[1]
        try:
            ydata = axes[1].plotterToGraphCoords(
                cgi.widgetposn, N.array([new_yplt]))
            newy = float(ydata[0])
        except (ValueError, ZeroDivisionError, ArithmeticError):
            return

        # subtract any step increase to store the base y
        ydata_min, ydata_max = self._getDataYRange()
        pr = axes[1].plottedrange
        if pr is not None and len(pr) >= 2:
            yrange_data = abs(pr[1] - pr[0])
        else:
            yrange_data = 1.0
        newy -= (s.stepIncrease / 100.0) * yrange_data

        newy = utils.round2delt(newy, newy + 0.001)

        op = document.OperationSettingSet(s.get('yPosition'), newy)
        self.document.applyOperation(op)

# Register widget
document.thefactory.register(BracketConnector)
