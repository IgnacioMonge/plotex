#    Copyright (C) 2010 Jeremy S. Sanders
#    Email: Jeremy Sanders <jeremy@jeremysanders.net>
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

"""Non orthogonal point plotting."""

import numpy as N

from .. import qtall as qt
from .. import document
from .. import datasets
from .. import setting
from .. import utils

from . import pickable

from .nonorthgraph import NonOrthGraph, FillBrush
from .widget import Widget
from .point import MarkerFillBrush

def _(text, disambiguation=None, context='NonOrthPoint'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

class NonOrthPoint(Widget):
    '''Widget for plotting points in a non-orthogonal plot.'''

    typename = 'nonorthpoint'
    allowusercreation = True
    description = _('Plot points on a graph with non-orthogonal axes')

    @classmethod
    def addSettings(klass, s):
        '''Settings for widget.'''
        Widget.addSettings(s)

        s.add( setting.DatasetExtended(
            'data1', 'x',
            descr=_(
                'Dataset containing 1st dataset, list of values '
                'or expression'),
            usertext=_('Dataset 1')) )
        s.add( setting.DatasetExtended(
            'data2', 'y',
            descr=_(
                'Dataset containing 2nd dataset, list of values '
                'or expression'),
            usertext=_('Dataset 2')) )
        s.add( setting.DatasetOrStr(
            'labels', '',
            descr=_('Dataset or string to label points'),
            usertext=_('Labels')) )
        s.add( setting.DatasetExtended(
            'scalePoints', '',
            descr = _(
                'Scale size of plotted markers by this dataset, '
                ' list of values or expression'),
            usertext=_('Scale markers')) )
        s.add( setting.DataColor('Color') )

        s.add( setting.Color(
            'color',
            'auto',
            descr=_('Master color'),
            usertext=_('Color'),
            formatting=True), 0 )
        s.add( setting.DistancePt(
            'markerSize',
            '3pt',
            descr=_('Size of marker to plot'),
            usertext=_('Marker size'), formatting=True), 0 )
        s.add( setting.Marker(
            'marker',
            'circle',
            descr=_('Type of marker to plot'),
            usertext=_('Marker'), formatting=True), 0 )
        s.add( setting.Line(
            'PlotLine',
            descr=_('Plot line settings'),
            usertext=_('Plot line')),
            pixmap='settings_plotline' )
        s.PlotLine.get('color').newDefault( setting.Reference('../color') )

        s.add( setting.MarkerLine(
            'MarkerLine',
            descr=_('Line around the marker settings'),
            usertext=_('Marker border')),
            pixmap='settings_plotmarkerline' )
        s.add( MarkerFillBrush(
            'MarkerFill',
            descr=_('Marker fill settings'),
            usertext=_('Marker fill')),
            pixmap='settings_plotmarkerfill' )
        s.add( FillBrush(
            'Fill1',
            descr=_('Fill settings (1)'),
            usertext=_('Area fill 1')),
            pixmap='settings_plotfillbelow' )
        s.add( FillBrush(
            'Fill2',
            descr=_('Fill settings (2)'),
            usertext=_('Area fill 2')),
            pixmap='settings_plotfillbelow' )
        s.add( setting.PointLabel(
            'Label',
            descr=_('Label settings'),
            usertext=_('Label')),
            pixmap='settings_axislabel' )

    @classmethod
    def allowedParentTypes(klass):
        return (NonOrthGraph,)

    @property
    def userdescription(self):
        return _("data1='%s', data2='%s'") % (
            self.settings.data1, self.settings.data2)

    def updateDataRanges(self, inrange):
        '''Extend inrange to range of data.'''

        d1 = self.settings.get('data1').getData(self.document)
        if d1:
            inrange[0] = min( N.nanmin(d1.data), inrange[0] )
            inrange[1] = max( N.nanmax(d1.data), inrange[1] )
        d2 = self.settings.get('data2').getData(self.document)
        if d2:
            inrange[2] = min( N.nanmin(d2.data), inrange[2] )
            inrange[3] = max( N.nanmax(d2.data), inrange[3] )

    def pickPoint(self, x0, y0, bounds, distance = 'radial'):
        p = pickable.DiscretePickable(self, 'data1', 'data2',
                lambda v1, v2: self.parent.graphToPlotCoords(v1, v2))
        return p.pickPoint(x0, y0, bounds, distance)

    def pickIndex(self, oldindex, direction, bounds):
        p = pickable.DiscretePickable(self, 'data1', 'data2',
                lambda v1, v2: self.parent.graphToPlotCoords(v1, v2))
        return p.pickIndex(oldindex, direction, bounds)

    def drawLabels(self, painter, xplotter, yplotter,
                   textvals, markersize):
        """Draw labels for the points.

        Uses automatic placement to reduce label overlap when enabled.
        """

        s = self.settings
        lab = s.get('Label')

        # make font and pen
        textpen = lab.makeQPen(painter)
        painter.setPen(textpen)
        font = lab.makeQFont(painter)
        angle = lab.angle

        avoid = lab.avoidOverlap

        if not avoid:
            # simple fixed placement (original behavior)
            deltax = markersize*1.5*{'left':-1, 'centre':0, 'right':1}[lab.posnHorz]
            deltay = markersize*1.5*{'top':-1, 'centre':0, 'bottom':1}[lab.posnVert]
            alignhorz = {'left':1, 'centre':0, 'right':-1}[lab.posnHorz]
            alignvert = {'top':-1, 'centre':0, 'bottom':1}[lab.posnVert]
            for x, y, t in zip(xplotter+deltax, yplotter+deltay, textvals):
                utils.Renderer(
                    painter, font, x, y, t,
                    alignhorz, alignvert, angle,
                    doc=self.document).render()
            return

        # auto-placement: try multiple positions, pick least overlap
        horz_factor = {'left': -1, 'centre': 0, 'right': 1}
        vert_factor = {'top': -1, 'centre': 0, 'bottom': 1}
        horz_align = {'left': 1, 'centre': 0, 'right': -1}
        vert_align = {'top': -1, 'centre': 0, 'bottom': 1}

        # candidate positions: preferred first, then alternatives
        candidates = [
            ('right', 'top'), ('right', 'bottom'), ('right', 'centre'),
            ('left', 'top'), ('left', 'bottom'), ('left', 'centre'),
            ('centre', 'top'), ('centre', 'bottom'),
        ]
        preferred = (lab.posnHorz, lab.posnVert)
        if preferred in candidates:
            candidates.remove(preferred)
        candidates.insert(0, preferred)

        # spatial grid for fast overlap queries (O(1) amortized vs O(n))
        grid = {}
        cell_size = max(markersize * 6, 40)

        def _grid_overlap(bounds):
            """Compute overlap area using spatial hash."""
            x0, y0, x2, y2 = bounds
            cx0 = int(x0 // cell_size)
            cy0 = int(y0 // cell_size)
            cx1 = int(x2 // cell_size)
            cy1 = int(y2 // cell_size)
            total = 0
            seen = set()
            for cx in range(cx0, cx1 + 1):
                for cy in range(cy0, cy1 + 1):
                    for pb in grid.get((cx, cy), ()):
                        pid = id(pb)
                        if pid in seen:
                            continue
                        seen.add(pid)
                        ox = max(0, min(x2, pb[2]) - max(x0, pb[0]))
                        oy = max(0, min(y2, pb[3]) - max(y0, pb[1]))
                        if ox > 0 and oy > 0:
                            total += ox * oy
                            return total
            return total

        def _grid_add(bounds):
            """Add bounds to spatial grid."""
            x0, y0, x2, y2 = bounds
            cx0 = int(x0 // cell_size)
            cy0 = int(y0 // cell_size)
            cx1 = int(x2 // cell_size)
            cy1 = int(y2 // cell_size)
            for cx in range(cx0, cx1 + 1):
                for cy in range(cy0, cy1 + 1):
                    key = (cx, cy)
                    if key not in grid:
                        grid[key] = []
                    grid[key].append(bounds)

        for x, y, t in zip(xplotter, yplotter, textvals):
            best_renderer = None
            best_overlap = float('inf')

            for h, v in candidates:
                dx = markersize * 1.5 * horz_factor[h]
                dy = markersize * 1.5 * vert_factor[v]
                ah = horz_align[h]
                av = vert_align[v]

                renderer = utils.Renderer(
                    painter, font, x + dx, y + dy, t,
                    ah, av, angle, doc=self.document)
                bounds = renderer.getBounds()

                overlap = _grid_overlap(bounds)
                if overlap == 0:
                    best_renderer = renderer
                    break
                if overlap < best_overlap:
                    best_overlap = overlap
                    best_renderer = renderer

            if best_renderer is not None:
                best_renderer.render()
                b = list(best_renderer.calcbounds)
                _grid_add(b)

    def getColorbarParameters(self):
        """Return parameters for colorbar."""
        s = self.settings
        c = s.Color
        return (
            c.min, c.max, c.scaling, s.MarkerFill.colorMap, 0,
            s.MarkerFill.colorMapInvert
        )

    def autoColor(self, painter, dataindex=0):
        """Automatic color for plotting."""
        return painter.docColorAuto(
            painter.helper.autoColorIndex((self, dataindex)))

    def draw(self, parentposn, phelper, outerbounds=None):
        '''Plot the data on a plotter.'''

        posn = self.computeBounds(parentposn, phelper)
        s = self.settings
        d = self.document

        # exit if hidden
        if s.hide:
            return

        d1 = s.get('data1').getData(d)
        d2 = s.get('data2').getData(d)
        dscale = s.get('scalePoints').getData(d)
        colorpoints = s.Color.get('points').getData(d)
        text = s.get('labels').getData(d, checknull=True)
        if not d1 or not d2:
            return

        x1, y1, x2, y2 = posn
        cliprect = qt.QRectF( qt.QPointF(x1, y1), qt.QPointF(x2, y2) )
        painter = phelper.painter(self, posn)
        with painter:
            self.parent.setClip(painter, posn)

            # split parts separated by NaNs
            for v1, v2, scalings, cvals, textitems in datasets.generateValidDatasetParts(
                [d1, d2, dscale, colorpoints, text]):
                # convert data (chopping down length)
                v1d, v2d = v1.data, v2.data
                minlen = min(v1d.shape[0], v2d.shape[0])
                v1d, v2d = v1d[:minlen], v2d[:minlen]
                px, py = self.parent.graphToPlotCoords(v1d, v2d)

                # do fill1 (if any)
                if not s.Fill1.hide:
                    self.parent.drawFillPts(painter, s.Fill1, cliprect, px, py)
                # do fill2
                if not s.Fill2.hide:
                    self.parent.drawFillPts(painter, s.Fill2, cliprect, px, py)

                # plot line
                if not s.PlotLine.hide:
                    painter.setBrush( qt.QBrush() )
                    painter.setPen(s.PlotLine.makeQPen(painter))
                    pts = qt.QPolygonF()
                    utils.addNumpyToPolygonF(pts, px, py)
                    utils.plotClippedPolyline(painter, cliprect, pts)

                # plot markers
                markersize = s.get('markerSize').convert(painter)
                if not s.MarkerLine.hide or not s.MarkerFill.hide:
                    pscale = colorvals = cmap = None

                    if scalings:
                        pscale = scalings.data

                    # color point individually
                    cmapname = s.MarkerFill.colorMap
                    if cvals and not s.MarkerFill.hide and cmapname != 'none':
                        colorvals = utils.applyScaling(
                            cvals.data, s.Color.scaling,
                            s.Color.min, s.Color.max)
                        cmap = self.document.evaluate.getColormap(
                            cmapname, s.MarkerFill.colorMapInvert)

                    painter.setBrush(s.MarkerFill.makeQBrushWHide(painter))
                    painter.setPen(s.MarkerLine.makeQPenWHide(painter))

                    utils.plotMarkers(
                        painter, px, py, s.marker, markersize,
                        scaling=pscale, clip=cliprect,
                        cmap=cmap, colorvals=colorvals,
                        scaleline=s.MarkerLine.scaleLine)

                # finally plot any labels
                if textitems and not s.Label.hide:
                    self.drawLabels(painter, px, py, textitems, markersize)

# allow the factory to instantiate plotter
document.thefactory.register(NonOrthPoint)
