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

"""For making box plots."""

import math
import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='BoxPlot'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

def percentile(sortedds, perc):
    """Given a sorted dataset, get the percentile perc.

    Interpolates between data points."""

    index = perc * 0.01 * (sortedds.shape[0]-1)

    # interpolate between indices
    frac, index = math.modf(index)
    index = int(index)
    indexplus1 = min(index+1, sortedds.shape[0]-1)
    interpol = (1-frac)*sortedds[index] + frac*sortedds[indexplus1]
    return interpol

def swapline(painter, x1, y1, x2, y2, swap):
    """Draw line, swapping x and y coordinates if swap is True."""
    if swap:
        painter.drawLine( qt.QPointF(y1, x1), qt.QPointF(y2, x2) )
    else:
        painter.drawLine( qt.QPointF(x1, y1), qt.QPointF(x2, y2) )

def swapbox(painter, x1, y1, x2, y2, swap):
    """Return box, swapping x and y coordinates if swap is True."""
    if swap:
        return qt.QRectF(qt.QPointF(y1, x1), qt.QPointF(y2, x2))
    else:
        return qt.QRectF(qt.QPointF(x1, y1), qt.QPointF(x2, y2))

class _BoxFill(setting.Brush):
    """Fill for box/violin."""
    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)

class _PointsFill(setting.Brush):
    """Fill brush for strip plot data points with 50% transparency default."""
    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)
        self.get('transparency').newDefault(50)

class _Stats:
    """Store statistics about box."""

    def calculate(self, data, whiskermode):
        """Calculate statistics for data."""
        cleaned = data[ N.isfinite(data) ]
        cleaned.sort()

        if len(cleaned) == 0:
            self.median = self.botquart = self.topquart = self.mean = \
                self.botwhisker = self.topwhisker = N.nan
            self.alldata = N.array([])
            self.outliers = N.array([])
            return

        self.median = percentile(cleaned, 50)
        self.botquart = percentile(cleaned, 25)
        self.topquart = percentile(cleaned, 75)
        self.mean = N.mean(cleaned)

        if whiskermode == 'min/max':
            self.botwhisker = cleaned.min()
            self.topwhisker = cleaned.max()
        elif whiskermode == '1.5IQR':
            iqr = self.topquart - self.botquart
            eltop = N.searchsorted(cleaned, self.topquart+1.5*iqr)-1
            self.topwhisker = cleaned[eltop]
            elbot = max(N.searchsorted(cleaned, self.botquart-1.5*iqr), 0)
            self.botwhisker = cleaned[elbot]
        elif whiskermode == '1 stddev':
            stddev = N.std(cleaned)
            self.topwhisker = self.mean+stddev
            self.botwhisker = self.mean-stddev
        elif whiskermode == '9/91 percentile':
            self.topwhisker = percentile(cleaned, 91)
            self.botwhisker = percentile(cleaned, 9)
        elif whiskermode == '2/98 percentile':
            self.topwhisker = percentile(cleaned, 98)
            self.botwhisker = percentile(cleaned, 2)
        else:
            raise RuntimeError("Invalid whisker mode")

        self.outliers = cleaned[ (cleaned < self.botwhisker) |
                                 (cleaned > self.topwhisker) ]
        self.alldata = cleaned

class BoxPlot(GenericPlotter):
    """Plot bar charts."""

    typename='boxplot'
    allowusercreation=True
    description=_('Plot box plots')

    @classmethod
    def addSettings(klass, s):
        """Construct list of settings."""
        GenericPlotter.addSettings(s)

        s.remove('key')
        s.add( setting.Choice(
            'whiskermode',
            (
                'min/max',
                '1.5IQR',
                '1 stddev',
                '9/91 percentile',
                '2/98 percentile'
            ),
            '1.5IQR',
            descr=_('Whisker mode'),
            usertext=_('Whisker mode')), 0 )

        s.add( setting.Choice(
            'direction',
            ('horizontal', 'vertical'), 'vertical',
            descr=_('Horizontal or vertical boxes'),
            usertext=_('Direction')), 0 )
        s.add( setting.DatasetOrStr(
            'labels', '',
            descr=_('Dataset or string to label bars'),
            usertext=_('Labels')), 0 )
        s.add( setting.DatasetExtended(
            'posn', '',
            descr=_(
                'Dataset or list of values giving positions of boxes (optional)'),
            usertext=_('Positions')), 0 )

        # calculate statistics from these datasets
        s.add( setting.Datasets(
            'values', ('data',),
            descr=_('Datasets containing values to calculate statistics for'),
            usertext=_('Datasets')), 0 )

        # alternate mode where data are provided for boxes
        s.add( setting.DatasetExtended(
            'whiskermax', '',
            descr=_('Dataset with whisker maxima or list of values'),
            usertext=_('Whisker max')), 0 )
        s.add( setting.DatasetExtended(
            'whiskermin', '',
            descr=_('Dataset with whisker minima or list of values'),
            usertext=_('Whisker min')), 0 )
        s.add( setting.DatasetExtended(
            'boxmax', '',
            descr=_('Dataset with box maxima or list of values'),
            usertext=_('Box max')), 0 )
        s.add( setting.DatasetExtended(
            'boxmin', '',
            descr=_('Dataset with box minima or list of values'),
            usertext=_('Box min')), 0 )
        s.add( setting.DatasetExtended(
            'median', '',
            descr=_('Dataset with medians or list of values'),
            usertext=_('Median')), 0 )
        s.add( setting.DatasetExtended(
            'mean', '',
            descr=_('Dataset with means or list of values'),
            usertext=_('Mean')), 0 )

        # switch between different modes
        s.add( setting.BoolSwitch(
            'calculate', True,
            descr=_(
                'Calculate statistics from datasets rather than given manually'),
            usertext=_('Calculate'),
            settingstrue=('whiskermode', 'values'),
            settingsfalse=(
                'boxmin', 'whiskermin',
                'boxmax', 'whiskermax',
                'mean', 'median')), 0 )

        # formatting options
        s.add( setting.Float(
            'fillfraction', 0.75,
            descr=_('Fill fraction of boxes'),
            usertext=_('Fill fraction'), formatting=True) )
        s.add( setting.ChoiceOrMore(
            'fillPalette',
            ['single color',
             'cb-set1', 'cb-set2', 'cb-dark2', 'cb-paired',
             'npg', 'nejm', 'lancet', 'jama', 'aaas', 'okabe-ito'],
            'cb-set1',
            descr=_('Color palette for boxes (type any colormap name or choose from list)'),
            usertext=_('Fill palette'), formatting=True) )

        # mean marker
        s.add( setting.Marker(
            'meanmarker',
            'linecross',
            descr=_('Marker for mean'),
            usertext=_('Mean marker'), formatting=True) )

        # individual data points (strip plot)
        s.add( setting.BoolSwitch(
            'showPoints', False,
            descr=_('Show individual data points (strip plot)'),
            usertext=_('Show points'),
            settingstrue=(
                'pointsMarker', 'pointsSize', 'jitter',
                'showOutliers', 'outliersmarker'),
            formatting=True) )
        s.add( setting.Marker(
            'pointsMarker',
            'circle',
            descr=_('Marker for data points'),
            usertext=_('Points marker'), formatting=True) )
        s.add( setting.DistancePt(
            'pointsSize',
            '3pt',
            descr=_('Size of data point markers'),
            usertext=_('Points size'), formatting=True) )
        s.add( setting.Float(
            'jitter', 0.3,
            minval=0.0, maxval=2.0,
            descr=_('Jitter spread as fraction of box width'),
            usertext=_('Jitter'), formatting=True) )

        # outlier settings (only available when showPoints is on)
        s.add( setting.Bool(
            'showOutliers', False,
            descr=_('Highlight outliers with a different marker'),
            usertext=_('Show outliers'), formatting=True) )
        s.add( setting.Marker(
            'outliersmarker',
            'circle',
            descr=_('Marker for outliers'),
            usertext=_('Outlier marker'), formatting=True) )
        s.add( setting.DistancePt(
            'markerSize',
            '3pt',
            descr=_('Size of outlier and mean markers'),
            usertext=_('Outlier/mean size'), formatting=True) )

        # sub-settings groups (formatting tabs)
        s.add( _BoxFill(
            'Fill',
            descr=_('Box fill'),
            usertext=_('Box fill')),
            pixmap='settings_bgfill' )
        s.add( setting.Line(
            'Border',
            descr=_('Box border line'),
            usertext=_('Box border')),
            pixmap='settings_border')
        s.add( setting.Line(
            'Whisker',
            descr=_('Whisker line'),
            usertext=_('Whisker line')),
            pixmap='settings_whisker')
        s.add( setting.Line(
            'PointsLine',
            descr=_('Line around data point markers'),
            usertext=_('Points border')),
            pixmap='settings_pointsline' )
        s.add( _PointsFill(
            'PointsFill',
            descr=_('Data point markers fill'),
            usertext=_('Points fill')),
            pixmap='settings_pointsfill' )
        s.add( setting.Line(
            'MarkersLine',
            descr=_('Line around outlier and mean markers'),
            usertext=_('Outlier border')),
            pixmap='settings_plotmarkerline' )
        s.add( setting.BoxPlotMarkerFillBrush(
            'MarkersFill',
            descr=_('Outlier and mean markers fill'),
            usertext=_('Outlier fill')),
            pixmap='settings_plotmarkerfill' )

    @property
    def userdescription(self):
        """Friendly description for user."""
        s = self.settings
        return "values='%s', position='%s'" % (
            ', '.join(s.values),  s.posn)

    def affectsAxisRange(self):
        """This widget provides range information about these axes."""
        s = self.settings
        return ( (s.xAxis, 'sx'), (s.yAxis, 'sy') )

    def rangeManual(self):
        """For updating range in manual mode."""
        s = self.settings
        ds = []
        for name in (
                'whiskermin', 'whiskermax', 'boxmin', 'boxmax', 'mean', 'median'):
            ds.append( s.get(name).getData(self.document) )
        r = [N.inf, -N.inf]
        if None not in ds:
            concat = N.concatenate([d.data for d in ds])
            r[0] = N.nanmin(concat)
            r[1] = N.nanmax(concat)
        return r

    def getPosns(self):
        """Get values of positions of bars."""

        s = self.settings
        doc = self.document

        posns = s.get('posn').getData(doc)
        if posns is not None:
            # manual positions
            return posns.data
        else:
            if s.calculate:
                # number of datasets
                vals = s.get('values').getData(doc)
            else:
                # length of mean array
                vals = s.get('mean').getData(doc)
                if vals:
                    vals = vals.data

            if vals is None:
                return N.array([])
            else:
                return N.arange(1, len(vals)+1, dtype=N.float64)

    def getRange(self, axis, depname, axrange):
        """Update axis range from data."""

        s = self.settings
        doc = self.document

        if ( (depname == 'sx' and s.direction == 'horizontal') or
             (depname == 'sy' and s.direction == 'vertical') ):
            # update axis in direction of data
            if s.calculate:
                # update from values
                values = s.get('values').getData(doc)
                if values:
                    for v in values:
                        if len(v.data) > 0:
                            axrange[0] = min(axrange[0], N.nanmin(v.data))
                            axrange[1] = max(axrange[1], N.nanmax(v.data))
            else:
                # update from manual entries
                drange = self.rangeManual()
                axrange[0] = min(axrange[0], drange[0])
                axrange[1] = max(axrange[1], drange[1])
        else:
            # update axis in direction of datasets
            posns = self.getPosns()
            if len(posns) > 0:
                axrange[0] = min(axrange[0], N.nanmin(posns)-0.5)
                axrange[1] = max(axrange[1], N.nanmax(posns)+0.5)

    def getAxisLabels(self, direction):
        """Get labels for axis if using a label axis."""

        s = self.settings
        doc = self.document
        text = s.get('labels').getData(doc, checknull=True)
        values = s.get('values').getData(doc)
        if text is None or values is None:
            return (None, None)
        positions = self.getPosns()
        return (text, positions)

    def plotBox(self, painter, axes, boxposn, posn, width, clip, stats,
                boxindex=0):
        """Draw box for dataset."""

        if not N.isfinite(stats.median):
            # skip bad datapoints
            return

        s = self.settings
        horz = (s.direction == 'horizontal')

        # convert quartiles, top and bottom whiskers to plotter
        medplt, botplt, topplt, botwhisplt, topwhisplt = tuple(
            axes[not horz].dataToPlotterCoords(
                posn,
                N.array([
                    stats.median, stats.botquart, stats.topquart,
                    stats.botwhisker, stats.topwhisker
                ]))
        )

        # draw whisker top to bottom
        p = s.Whisker.makeQPenWHide(painter)
        p.setCapStyle(qt.Qt.PenCapStyle.FlatCap)
        painter.setPen(p)
        swapline(painter, boxposn, topwhisplt, boxposn, botwhisplt, horz)
        # draw ends of whiskers
        endsize = width/2
        swapline(
            painter, boxposn-endsize/2, topwhisplt,
            boxposn+endsize/2, topwhisplt, horz)
        swapline(
            painter, boxposn-endsize/2, botwhisplt,
            boxposn+endsize/2, botwhisplt, horz)

        # draw box fill
        boxpath = qt.QPainterPath()
        boxpath.addRect( swapbox(
            painter, boxposn-width/2, botplt, boxposn+width/2, topplt, horz) )
        if not s.Fill.hide:
            palette = s.fillPalette
            if palette != 'single color':
                # use palette color by index
                from ..utils.colormap import getColormapArray
                cmap = self.document.evaluate.colormaps.get(palette)
                if cmap is not None:
                    arr = N.array(cmap)
                    is_step = len(arr) > 0 and arr[0][0] < 0
                    ncolors = (len(arr) - 1) if is_step else max(len(arr), 1)
                    rgba = getColormapArray(cmap, ncolors)
                    ci = boxindex % ncolors
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
            painter.setPen(qt.QPen(qt.Qt.PenStyle.NoPen))
            painter.drawPath(boxpath)

        # draw line across box
        p = s.Whisker.makeQPenWHide(painter)
        p.setCapStyle(qt.Qt.PenCapStyle.FlatCap)
        painter.setPen(p)
        swapline(
            painter, boxposn-width/2, medplt,
            boxposn+width/2, medplt, horz)

        # draw box
        painter.strokePath(boxpath, s.Border.makeQPenWHide(painter) )

        # marker size for outliers and mean
        markersize = s.get('markerSize').convert(painter)

        # draw individual data points with jitter (strip plot)
        if s.showPoints and hasattr(stats, 'alldata') and len(stats.alldata) > 0:
            pointsdata = stats.alldata
            pltvals = axes[not horz].dataToPlotterCoords(posn, pointsdata)

            # jitter relative to box half-width
            jitter_range = s.jitter * (width / 2)
            rng = N.random.RandomState(42)
            jitters = (rng.random(len(pointsdata)) - 0.5) * 2 * jitter_range

            otherpos = N.full_like(pltvals, boxposn) + jitters
            if horz:
                px, py = pltvals, otherpos
            else:
                px, py = otherpos, pltvals

            pt_size = s.get('pointsSize').convert(painter)
            painter.setPen(s.PointsLine.makeQPenWHide(painter))
            painter.setBrush(s.PointsFill.makeQBrushWHide(painter))
            utils.plotMarkers(
                painter, px, py, s.pointsMarker, pt_size, clip=clip)

        # draw outliers (only when showPoints is on and showOutliers is enabled)
        if s.showPoints and s.showOutliers and stats.outliers.shape[0] != 0:
            pltvals = axes[not horz].dataToPlotterCoords(posn, stats.outliers)
            otherpos = N.zeros(pltvals.shape) + boxposn
            if horz:
                x, y = pltvals, otherpos
            else:
                x, y = otherpos, pltvals
            painter.setPen(s.MarkersLine.makeQPenWHide(painter))
            painter.setBrush(s.MarkersFill.makeQBrushWHide(painter))
            utils.plotMarkers(
                painter, x, y, s.outliersmarker, markersize, clip=clip)

        # draw mean
        painter.setPen(s.MarkersLine.makeQPenWHide(painter))
        painter.setBrush(s.MarkersFill.makeQBrushWHide(painter))
        meanplt = axes[not horz].dataToPlotterCoords(
            posn, N.array([stats.mean]))[0]
        if horz:
            x, y = meanplt, boxposn
        else:
            x, y = boxposn, meanplt
        utils.plotMarker(painter, x, y, s.meanmarker, markersize)

    def dataDraw(self, painter, axes, widgetposn, clip):
        """Plot the data on a plotter."""

        s = self.settings

        # get data
        doc = self.document
        positions = self.getPosns()
        if s.calculate:
            # calculate from data
            values = s.get('values').getData(doc)
            if values is None:
                return
        else:
            # use manual datasets
            datasets = [
                s.get(x).getData(doc) for x in
                ('whiskermin', 'whiskermax', 'boxmin', 'boxmax', 'mean', 'median')
            ]
            if any((d is None for d in datasets)):
                return

        # get axes widgets
        axes = self.parent.getAxes( (s.xAxis, s.yAxis) )

        # return if there are no proper axes
        if ( axes[0] is None or axes[1] is None or
             axes[0].settings.direction != 'horizontal' or
             axes[1].settings.direction != 'vertical' ):
            return

        # get boxes visible along direction of boxes to work out width
        horz = (s.direction == 'horizontal')
        plotposns = axes[horz].dataToPlotterCoords(widgetposn, positions)

        if horz:
            inplot = (plotposns > widgetposn[1]) & (plotposns < widgetposn[3])
        else:
            inplot = (plotposns > widgetposn[0]) & (plotposns < widgetposn[2])
        inplotposn = plotposns[inplot]
        if inplotposn.shape[0] < 2:
            if horz:
                width = (widgetposn[3]-widgetposn[1])*0.5
            else:
                width = (widgetposn[2]-widgetposn[0])*0.5
        else:
            # use minimum different between points to get width
            inplotposn.sort()
            width = N.nanmin(inplotposn[1:] - inplotposn[:-1])

        # adjust width
        width = width * s.fillfraction

        if s.calculate:
            # calculated boxes
            for idx, (vals, plotpos) in enumerate(zip(values, plotposns)):
                stats = _Stats()
                stats.calculate(vals.data, s.whiskermode)
                self.plotBox(
                    painter, axes, plotpos, widgetposn, width,
                    clip, stats, boxindex=idx)
        else:
            # manually given boxes
            vals = [d.data for d in datasets] + [plotposns]
            lens = [len(d) for d in vals]
            for i in range(min(lens)):
                stats = _Stats()
                stats.topwhisker = vals[0][i]
                stats.botwhisker = vals[1][i]
                stats.botquart = vals[2][i]
                stats.topquart = vals[3][i]
                stats.mean = vals[4][i]
                stats.median = vals[5][i]
                stats.outliers = N.array([])
                stats.alldata = N.array([])
                self.plotBox(
                    painter, axes, vals[6][i], widgetposn,
                    width, clip, stats, boxindex=i)

# allow the factory to instantiate a boxplot
document.thefactory.register(BoxPlot)
