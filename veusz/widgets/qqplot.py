"""Q-Q Plot widget — quantile-quantile plot against a theoretical distribution."""

import numpy as N

from .. import qtall as qt
from .. import setting
from .. import document
from .. import utils

from .plotters import GenericPlotter

def _(text, disambiguation=None, context='QQPlot'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


class _RefLine(setting.Line):
    """Reference line style."""
    def __init__(self, name, **args):
        setting.Line.__init__(self, name, **args)
        self.get('color').newDefault('grey')
        self.get('width').newDefault('1pt')
        self.get('style').newDefault('dashed')

class _CIFill(setting.Brush):
    """Confidence band fill."""
    def __init__(self, name, **args):
        setting.Brush.__init__(self, name, **args)
        self.get('color').newDefault('grey')
        self.get('transparency').newDefault(75)


class QQPlot(GenericPlotter):
    """Q-Q plot: observed quantiles vs theoretical quantiles."""

    typename = 'qqplot'
    allowusercreation = True
    description = _('Q-Q plot (quantile-quantile)')

    @classmethod
    def addSettings(klass, s):
        GenericPlotter.addSettings(s)
        s.remove('key')

        s.add(setting.DatasetExtended(
            'data', '',
            descr=_('Dataset to plot'),
            usertext=_('Data')), 0)

        s.add(setting.Choice(
            'distribution',
            ('normal', 'uniform', 'exponential', 't', 'lognormal',
             'chi2', 'gamma'),
            'normal',
            descr=_('Theoretical distribution'),
            usertext=_('Distribution')), 1)
        s.add(setting.Float(
            'dfparam', 5.0, minval=0.1,
            descr=_('Degrees of freedom (for t, chi2) or shape (gamma)'),
            usertext=_('df / shape')), 2)
        s.add(setting.Bool(
            'showRefLine', True,
            descr=_('Show 45° reference line'),
            usertext=_('Reference line')), 3)
        s.add(setting.Bool(
            'showCI', True,
            descr=_('Show approximate pointwise envelope'),
            usertext=_('Envelope band')), 4)

        s.add(setting.Marker(
            'marker', 'circle',
            descr=_('Marker style'),
            usertext=_('Marker')), 5)
        s.add(setting.DistancePt(
            'markerSize', '3pt',
            descr=_('Marker size'),
            usertext=_('Marker size')), 6)
        s.add(setting.Color(
            'Color', 'auto',
            descr=_('Marker color'),
            usertext=_('Color')), 7)

        s.add(setting.Brush(
            'MarkerFill',
            descr=_('Marker fill'),
            usertext=_('Marker fill')),
            pixmap='settings_plotmarkerfill')
        s.add(setting.Line(
            'MarkerBorder',
            descr=_('Marker border'),
            usertext=_('Marker border')),
            pixmap='settings_plotmarkerline')
        s.add(_RefLine(
            'RefLine',
            descr=_('Reference line'),
            usertext=_('Ref. line')),
            pixmap='settings_plotline')
        s.add(_CIFill(
            'CIFill',
            descr=_('Confidence band fill'),
            usertext=_('CI fill')),
            pixmap='settings_bgfill')

    @property
    def userdescription(self):
        return "data='%s'" % self.settings.data

    def _getDistribution(self):
        """Return a scipy.stats distribution object."""
        try:
            from scipy import stats as scipystats
        except ImportError:
            return None
        s = self.settings
        dname = s.distribution
        df = s.dfparam
        if dname == 'normal':
            return scipystats.norm
        elif dname == 'uniform':
            return scipystats.uniform
        elif dname == 'exponential':
            return scipystats.expon
        elif dname == 't':
            return scipystats.t(df)
        elif dname == 'lognormal':
            return scipystats.lognorm(1)
        elif dname == 'chi2':
            return scipystats.chi2(df)
        elif dname == 'gamma':
            return scipystats.gamma(df)
        return scipystats.norm

    def _compute(self):
        """Compute theoretical and observed quantiles."""
        s = self.settings
        doc = self.document

        dset = s.get('data').getData(doc)
        if dset is None:
            return None, None
        data = N.array(dset.data, dtype=float)
        data = data[N.isfinite(data)]
        if len(data) < 2:
            return None, None

        data = N.sort(data)
        n = len(data)

        dist = self._getDistribution()
        if dist is None:
            return None, None

        # plotting positions (Filliben)
        pp = (N.arange(1, n + 1) - 0.375) / (n + 0.25)
        theoretical = dist.ppf(pp)

        # fit location/scale to match data
        loc = N.mean(data)
        scale = N.std(data, ddof=1)
        if scale < 1e-15:
            scale = 1.0

        # standardize theoretical quantiles to data scale
        if s.distribution == 'normal':
            theoretical = theoretical * scale + loc

        return theoretical, data

    def affectsAxisRange(self):
        s = self.settings
        return ((s.xAxis, 'sx'), (s.yAxis, 'sy'))

    def getRange(self, axis, depname, axrange):
        theo, obs = self._compute()
        if theo is None:
            return
        if depname == 'sx':
            axrange[0] = min(axrange[0], N.nanmin(theo))
            axrange[1] = max(axrange[1], N.nanmax(theo))
        elif depname == 'sy':
            axrange[0] = min(axrange[0], N.nanmin(obs))
            axrange[1] = max(axrange[1], N.nanmax(obs))

    def dataDraw(self, painter, axes, widgetposn, clip):
        s = self.settings
        theo, obs = self._compute()
        if theo is None:
            return

        xaxis, yaxis = axes

        xplt = xaxis.dataToPlotterCoords(widgetposn, theo)
        yplt = yaxis.dataToPlotterCoords(widgetposn, obs)

        cliprect = clip
        painter.save()
        try:
            painter.setClipRect(cliprect)

            # confidence band
            if s.showCI and len(theo) > 2:
                n = len(theo)
                dist = self._getDistribution()
                if dist is None:
                    return
                pp = (N.arange(1, n + 1) - 0.375) / (n + 0.25)

                # Approximate pointwise envelope using order-statistic
                # variance of the plotting positions.  This is NOT a
                # rigorous simultaneous confidence band — it provides a
                # rough visual guide only.
                se = (pp * (1 - pp) / n) ** 0.5
                if s.distribution == 'normal':
                    loc = N.mean(obs)
                    scale = N.std(obs, ddof=1)
                    if scale < 1e-15:
                        scale = 1.0
                    lower = dist.ppf(N.clip(pp - 1.96 * se, 0.001, 0.999)) * scale + loc
                    upper = dist.ppf(N.clip(pp + 1.96 * se, 0.001, 0.999)) * scale + loc
                else:
                    lower = dist.ppf(N.clip(pp - 1.96 * se, 0.001, 0.999))
                    upper = dist.ppf(N.clip(pp + 1.96 * se, 0.001, 0.999))

                yl = yaxis.dataToPlotterCoords(widgetposn, lower)
                yu = yaxis.dataToPlotterCoords(widgetposn, upper)

                cibrush = s.CIFill.makeQBrushWHide(painter)
                painter.setBrush(cibrush)
                painter.setPen(qt.Qt.PenStyle.NoPen)

                path = qt.QPainterPath()
                valid = N.isfinite(xplt) & N.isfinite(yl) & N.isfinite(yu)
                started = False
                for i in range(n):
                    if valid[i]:
                        if not started:
                            path.moveTo(xplt[i], yl[i])
                            started = True
                        else:
                            path.lineTo(xplt[i], yl[i])
                for i in range(n - 1, -1, -1):
                    if valid[i]:
                        path.lineTo(xplt[i], yu[i])
                path.closeSubpath()
                painter.drawPath(path)

            # reference line (45° through Q1-Q3)
            if s.showRefLine:
                refpen = s.RefLine.makeQPenWHide(painter)
                painter.setPen(refpen)
                painter.setBrush(qt.Qt.BrushStyle.NoBrush)

                q1_obs = N.percentile(obs, 25)
                q3_obs = N.percentile(obs, 75)
                q1_theo = N.percentile(theo, 25)
                q3_theo = N.percentile(theo, 75)

                if abs(q3_theo - q1_theo) > 1e-15:
                    slope = (q3_obs - q1_obs) / (q3_theo - q1_theo)
                    intercept = q1_obs - slope * q1_theo
                else:
                    slope = 1.0
                    intercept = 0.0

                xmin, xmax = N.nanmin(theo), N.nanmax(theo)
                margin = (xmax - xmin) * 0.05
                lx = N.array([xmin - margin, xmax + margin])
                ly = slope * lx + intercept

                lxp = xaxis.dataToPlotterCoords(widgetposn, lx)
                lyp = yaxis.dataToPlotterCoords(widgetposn, ly)
                if N.all(N.isfinite(lxp)) and N.all(N.isfinite(lyp)):
                    painter.drawLine(
                        qt.QPointF(lxp[0], lyp[0]),
                        qt.QPointF(lxp[1], lyp[1]))

            # markers
            markerbrush = s.MarkerFill.makeQBrushWHide(painter)
            markeredge = s.MarkerBorder.makeQPenWHide(painter)
            painter.setPen(markeredge)
            painter.setBrush(markerbrush)

            markersize = s.get('markerSize').convert(painter)
            valid = N.isfinite(xplt) & N.isfinite(yplt)
            utils.plotMarkers(
                painter, xplt[valid], yplt[valid],
                s.marker, markersize, clip=cliprect)
        finally:
            painter.restore()


document.thefactory.register(QQPlot)
