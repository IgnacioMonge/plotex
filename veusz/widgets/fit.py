# fitting plotter

#    Copyright (C) 2005 Jeremy S. Sanders
#    Copyright (C) 2026 M. Ignacio Monge García (confidence/prediction bands)
#
#    This file is part of Veusz / Plotex.
#
#    Veusz is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
##############################################################################

"""Fit widget with confidence and prediction bands.

Architecture:
  actionFit() [main thread] — fits data, computes bands, saves ALL
      results to persistent settings (survives save/load).
  dataDraw() [render thread] — reads settings and draws. NEVER
      modifies settings or document state.

If data changes after a fit, the user must re-run the fit manually.
"""

import math
import re
import sys

import numpy as N

from .. import document
from .. import setting
from .. import utils
from .. import qtall as qt

from .function import FunctionPlotter
from . import widget
from ..helpers.qtloops import addNumpyToPolygonF

# try importing iminuit first, then minuit, then None
try:
    import iminuit as minuit
except ImportError:
    try:
        import minuit
    except ImportError:
        minuit = None

# scipy.stats loaded lazily on first use
_sp_stats_cache = None
def _get_sp_stats():
    global _sp_stats_cache
    if _sp_stats_cache is None:
        try:
            from scipy import stats
            # verify it actually works
            stats.t.ppf(0.975, 10)
            _sp_stats_cache = stats
        except Exception:
            _sp_stats_cache = False
    return _sp_stats_cache if _sp_stats_cache is not False else None

# Check whether iminuit version is old (1.x)
if minuit is not None:
    isiminuit1 = minuit.__version__[0:1] == '1'

def _(text, disambiguation=None, context='Fit'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

# ── Minuit fitting ───────────────────────────────────────────────

def minuitFit(evalfunc, params, names, values, xvals, yvals, yserr,
              log=None):
    """Do fitting with minuit (if installed)."""

    if log is None:
        log = sys.stdout

    def chi2(params):
        c = ((evalfunc(params, xvals) - yvals)**2 / yserr**2).sum()
        if chi2.runningFit:
            chi2.iters += 1
            p = [chi2.iters, c] + params.tolist()
            s = ("%5i " + "%8g " * (len(params)+1)) % tuple(p)
            print(s, file=log)
        return c

    def fn(*vals):
        return chi2(N.array(vals))

    print(_('Fitting via Minuit:'), file=log)
    initial_values = [values[n] for n in names]
    if isiminuit1:
        m = minuit.Minuit(fn, *initial_values,
                          forced_parameters=names, errordef=1.0)
    else:
        m = minuit.Minuit(fn, *initial_values, name=names)
    m.errordef = 1.0

    chi2.runningFit = True
    chi2.iters = 0
    m.migrad()

    have_symerr, have_err = False, False
    try:
        chi2.runningFit = False
        m.hesse()
        have_symerr = True
        m.minos()
        have_err = True
    except Exception as e:
        print(e, file=log)
        if str(e).startswith('Discovered a new minimum'):
            raise

    retchi2 = m.fval
    dof = len(yvals) - len(params)
    redchi2 = retchi2 / dof if dof > 0 else N.nan

    if have_err:
        if isiminuit1:
            results = ["    %s = %g \u00b1 %g (+%g / %g)" % (
                n, m.values[n], m.errors[n], m.merrors[(n, 1.0)],
                m.merrors[(n, -1.0)]) for n in names]
        else:
            results = ["    %s = %g \u00b1 %g (+%g / %g)" % (
                n, m.values[n], m.errors[n], m.merrors[n].upper,
                m.merrors[n].lower) for n in names]
        print(_('Fit results:\n') + "\n".join(results), file=log)
    elif have_symerr:
        print(_('Fit results:\n') + "\n".join([
            "    %s = %g \u00b1 %g" % (n, m.values[n], m.errors[n])
            for n in names]), file=log)
    else:
        print(_('Fit results:\n') + "\n".join([
            '    %s = %g' % (n, m.values[n]) for n in names]), file=log)

    print("chi^2 = %g, dof = %i, reduced-chi^2 = %g" % (
        retchi2, dof, redchi2), file=log)

    vals = {name: m.values[name] for name in names}

    param_errors = {}
    cov = None
    if have_symerr:
        for n in names:
            param_errors[n] = float(m.errors[n])
        try:
            cov_raw = m.covariance
            nparams = len(names)
            cov = N.zeros((nparams, nparams))
            for i in range(nparams):
                for j in range(nparams):
                    cov[i, j] = cov_raw[i, j]
        except Exception:
            cov = None

    return vals, retchi2, dof, param_errors, cov

# ── Fit Widget ───────────────────────────────────────────────────

class Fit(FunctionPlotter):
    """A plotter to fit a function to data."""

    typename = 'fit'
    allowusercreation = True
    description = _('Fit a function to data')

    def __init__(self, parent, name=None):
        FunctionPlotter.__init__(self, parent, name=name)

        self.addAction(widget.Action(
            'fit', self.actionFitDialog,
            descr=_('Open fit dialog'),
            usertext=_('Fit…')))
        self.addAction(widget.Action(
            'fitquick', self.actionFit,
            descr=_('Fit with current parameters (no dialog)'),
            usertext=_('Quick fit')))

        # runtime cache (not persisted)
        self._path_cache = {}
        self._path_cache_key = None

    # ── Settings ─────────────────────────────────────────────

    @classmethod
    def addSettings(klass, s):
        """Construct list of settings."""
        FunctionPlotter.addSettings(s)

        s.add(setting.DatasetExtended(
            'xData', 'x',
            descr=_('X data to fit'),
            usertext=_('X data')), 0)
        s.add(setting.DatasetExtended(
            'yData', 'y',
            descr=_('Y data to fit'),
            usertext=_('Y data')), 1)
        s.add(setting.FloatDict(
            'values', {'a': 0.0, 'b': 1.0},
            descr=_('Variables and fit values'),
            usertext=_('Parameters')), 3)
        s.add(setting.Choice(
            'defErrType', ['absolute', 'relative'], 'absolute',
            descr=_('Default error type'),
            usertext=_('Def. error type')))
        s.add(setting.Float(
            'defErr', 0.05,
            descr='Default absolute/relative error value for data',
            usertext=_('Default error')))
        s.add(setting.FloatOrAuto(
            'fitMin', 'Auto',
            descr=_('Minimum value at which to fit function'),
            usertext=_('Min. fit range')))
        s.add(setting.FloatOrAuto(
            'fitMax', 'Auto',
            descr=_('Maximum value at which to fit function'),
            usertext=_('Max. fit range')))
        s.add(setting.Bool(
            'fitRange', False,
            descr=_('Fit only the data between the min/max of the axis'),
            usertext=_('Fit only range')), 4)
        s.add(setting.WidgetChoice(
            'outLabel', '',
            descr=_('Write best fit parameters to this text label'),
            widgettypes=('label',),
            usertext=_('Output label')), 5)
        s.add(setting.Str(
            'outExpr', '',
            descr=_('Output best fitting expression'),
            usertext=_('Output expression')),
            6, readonly=True)
        s.add(setting.Float(
            'chi2', -1,
            descr='Output chi^2 from fitting',
            usertext=_('Fit chi2')),
            7, readonly=True)
        s.add(setting.Int(
            'dof', -1,
            descr=_('Output degrees of freedom'),
            usertext=_('Fit d.o.f.')),
            8, readonly=True)
        s.add(setting.Float(
            'redchi2', -1,
            descr=_('Output reduced chi-squared'),
            usertext=_('Fit red. chi2')),
            9, readonly=True)
        s.add(setting.FloatDict(
            'paramErrors', {},
            descr=_('Parameter standard errors'),
            usertext=_('Param errors')),
            10, readonly=True)

        # persisted band data (saved in .vsz file)
        for name, default, descr in (
            ('bandXData', [], 'Band X evaluation points'),
            ('bandConfUpper', [], 'Confidence band upper Y'),
            ('bandConfLower', [], 'Confidence band lower Y'),
            ('bandPredUpper', [], 'Prediction band upper Y'),
            ('bandPredLower', [], 'Prediction band lower Y'),
        ):
            setn = setting.FloatList(name, default, descr=descr,
                                     usertext=descr)
            setn.hidden = True
            s.add(setn)
        for name, default, descr in (
            ('bandResidVar', 0.0, 'Residual variance'),
        ):
            if isinstance(default, float):
                setn = setting.Float(name, default, descr=descr,
                                     usertext=descr)
            else:
                setn = setting.Str(name, default, descr=descr,
                                   usertext=descr)
            setn.hidden = True
            s.add(setn)

        # band display settings
        s.add(setting.Bool(
            'verbose', False,
            descr=_('Show fitting details in console'),
            usertext=_('Verbose output')))
        s.add(setting.Bool(
            'showConfBand', False,
            descr=_('Show confidence band around fitted curve'),
            usertext=_('Confidence band'),
            formatting=True))
        s.add(setting.Float(
            'confLevel', 95.0,
            descr=_('Confidence level (%) for bands'),
            usertext=_('Confidence %'),
            formatting=True))
        s.add(setting.Bool(
            'showPredBand', False,
            descr=_('Show prediction band (where data points fall)'),
            usertext=_('Prediction band'),
            formatting=True))

        f = s.get('function')
        f.newDefault('a + b*x')

        # ensure fit line color is auto (cycles through theme)
        s.get('color').newDefault('auto')
        f.descr = _('Function to fit')

    # ── Helpers ──────────────────────────────────────────────

    def affectsAxisRange(self):
        s = self.settings
        return ((s.xAxis, 'sx'), (s.yAxis, 'sy'))

    def getRange(self, axis, depname, axrange):
        dataname = {'sx': 'xData', 'sy': 'yData'}[depname]
        data = self.settings.get(dataname).getData(self.document)
        if data:
            drange = data.getRange()
            if drange:
                axrange[0] = min(axrange[0], drange[0])
                axrange[1] = max(axrange[1], drange[1])

    def initEnviron(self):
        env = self.document.evaluate.context.copy()
        env.update(self.settings.values)
        return env

    def _findData(self):
        """Find X and Y data, checking sibling scatter plots if needed."""
        s = self.settings
        d = self.document
        if s.variable == 'x':
            xdata = s.get('xData').getData(d)
            ydata = s.get('yData').getData(d)
        else:
            xdata = s.get('yData').getData(d)
            ydata = s.get('xData').getData(d)

        if xdata is None or ydata is None:
            from . import point
            for sib in self.iterSiblings(point.PointPlotter):
                ss = sib.settings
                if xdata is None:
                    xdata = ss.get('xData').getData(d)
                if ydata is None:
                    ydata = ss.get('yData').getData(d)
                if xdata is not None and ydata is not None:
                    return xdata, ydata, sib.name
        return xdata, ydata, None

    # ── Output label ─────────────────────────────────────────

    def updateOutputLabel(self, ops, vals, chi2, dof):
        s = self.settings
        labelwidget = s.get('outLabel').findWidget()
        if labelwidget is not None:
            loc = self.document.locale
            txt = []
            for l, v in sorted(vals.items()):
                val = utils.formatNumber(v, '%.4Vg', locale=loc)
                txt.append('%s = %s' % (l, val))
            redchi2_label = chi2/dof if dof > 0 else N.nan
            txt.append(r'\chi^{2}_{\nu} = %s/%i = %s' % (
                utils.formatNumber(chi2, '%.4Vg', locale=loc),
                dof,
                utils.formatNumber(redchi2_label, '%.4Vg', locale=loc)))
            text = r'\\'.join(txt)
            ops.append(document.OperationSettingSet(
                labelwidget.settings.get('label'), text))

    # ── Action: Fit dialog ─────────────────────────────────────

    def actionFitDialog(self):
        """Open the fit dialog."""
        from ..dialogs.fitdialog import FitDialog
        # find a parent QWidget for the dialog
        parent = None
        try:
            from .. import qtall as qt
            for w in qt.QApplication.topLevelWidgets():
                if hasattr(w, '_tabs'):
                    parent = w
                    break
        except Exception:
            pass
        dlg = FitDialog(self, parent)
        dlg.exec()

    # ── Action: Fit (main thread) ────────────────────────────

    def actionFit(self):
        """Fit the data and compute confidence/prediction bands."""

        s = self.settings
        compiled = self.document.evaluate.compileCheckedExpression(
            s.function)
        if compiled is None:
            return

        paramnames = sorted(s.values)
        params = N.array([s.values[p] for p in paramnames])
        d = self.document

        # find data
        xdata, ydata, sib_name = self._findData()
        if xdata is None or ydata is None:
            sys.stderr.write(
                _('No data to fit. Assign datasets or add scatter plot.\n'))
            return

        verbose = s.verbose
        if sib_name and verbose:
            print(_('Using data from scatter plot "%s"') % sib_name)

        xvals = xdata.data
        yvals = ydata.data
        yserr = ydata.serr

        # trim to equal length
        minlen = min(len(xvals), len(yvals))
        xvals, yvals = xvals[:minlen], yvals[:minlen]
        if yserr is not None:
            yserr = yserr[:minlen]

        # default errors
        if yserr is None:
            if ydata.perr is not None and ydata.nerr is not None:
                perr = ydata.perr[:minlen]
                nerr = ydata.nerr[:minlen]
                yserr = N.sqrt(0.5 * (perr**2 + nerr**2))
            else:
                err = s.defErr
                if s.defErrType == 'absolute':
                    yserr = err + yvals * 0
                else:
                    yserr = yvals * err
                    yserr[yserr < 1e-8] = 1e-8

        # range filtering
        mask = None
        if s.fitRange:
            if s.variable == 'x':
                axlist = self.parent.getAxes((s.xAxis,))
                ax = axlist[0] if axlist and axlist[0] is not None else None
                if ax is None:
                    sys.stderr.write(
                        _('Fit: axis "%s" not found, ignoring fitRange\n')
                        % s.xAxis)
                else:
                    drange = ax.getPlottedRange()
                    mask = (xvals >= drange[0]) & (xvals <= drange[1])
            else:
                axlist = self.parent.getAxes((s.yAxis,))
                ax = axlist[0] if axlist and axlist[0] is not None else None
                if ax is None:
                    sys.stderr.write(
                        _('Fit: axis "%s" not found, ignoring fitRange\n')
                        % s.yAxis)
                else:
                    drange = ax.getPlottedRange()
                    mask = (yvals >= drange[0]) & (yvals <= drange[1])
            if mask is not None:
                xvals, yvals, yserr = xvals[mask], yvals[mask], yserr[mask]

        evalenv = self.initEnviron()

        def evalfunc(params, xv):
            evalenv[s.variable] = xv
            evalenv.update(zip(paramnames, params))
            try:
                return eval(compiled, evalenv) + xv * 0.
            except Exception as e:
                self.document.log(str(e))
                return N.nan

        # min/max filtering
        if s.fitMin != 'Auto':
            mask = (xvals >= s.fitMin) if s.variable == 'x' else (
                yvals >= s.fitMin)
            xvals, yvals, yserr = xvals[mask], yvals[mask], yserr[mask]
        if s.fitMax != 'Auto':
            mask = (xvals <= s.fitMax) if s.variable == 'x' else (
                yvals <= s.fitMax)
            xvals, yvals, yserr = xvals[mask], yvals[mask], yserr[mask]

        # error checks
        if len(xvals) == 0:
            sys.stderr.write(_('No data values. Not fitting.\n'))
            return
        if len(params) > len(xvals):
            sys.stderr.write(_('No degrees of freedom. Not fitting.\n'))
            return

        # finite values only
        finite = N.isfinite(xvals) & N.isfinite(yvals) & N.isfinite(yserr)
        xvals, yvals, yserr = xvals[finite], yvals[finite], yserr[finite]
        if len(xvals) == 0:
            sys.stderr.write(_('No finite data. Not fitting.\n'))
            return

        # ── Do the fit ───────────────────────────────────────
        import io
        _fitlog = sys.stdout if verbose else io.StringIO()

        param_errors = {}
        cov = None
        if minuit is not None:
            vals, chi2, dof, param_errors, cov = minuitFit(
                evalfunc, params, paramnames, s.values,
                xvals, yvals, yserr, log=_fitlog)
        else:
            retn, chi2, dof, lm_errors, cov = utils.fitLM(
                evalfunc, params, xvals, yvals, yserr,
                log=_fitlog)
            vals = {n: float(v) for n, v in zip(paramnames, retn)}
            for i, n in enumerate(paramnames):
                if i < len(lm_errors) and lm_errors[i] > 0:
                    param_errors[n] = float(lm_errors[i])

        # check for NaN
        if math.isnan(chi2):
            print(_('Fit failed (chi² is NaN). Check data/function.'))
            return

        # residual variance (in Y units, for prediction band)
        fitted_vals = N.array([vals[p] for p in paramnames])
        yfit = evalfunc(fitted_vals, xvals)
        residuals = yvals - yfit
        resid_var = float(N.sum(residuals**2) / max(dof, 1))

        # fingerprint
        # filter NaN from errors
        clean_errors = {k: v for k, v in param_errors.items()
                        if not math.isnan(v)}

        # ── Compute bands ────────────────────────────────────
        band_x = []
        conf_upper = []
        conf_lower = []
        pred_upper = []
        pred_lower = []

        sp_stats = _get_sp_stats()
        has_cov = cov is not None or clean_errors
        if has_cov and dof > 0:
            # covariance matrix
            if cov is None:
                pe = N.array([clean_errors.get(p, 0) for p in paramnames])
                cov = N.diag(pe ** 2)

            # scale by reduced chi-squared
            redchi2_val = chi2 / max(dof, 1)
            if redchi2_val > 0:
                cov_scaled = cov * redchi2_val
            else:
                cov_scaled = cov

            # t-critical value (use scipy if available, else z-approximation)
            alpha = 1.0 - s.confLevel / 100.0
            if sp_stats is not None:
                t_crit = sp_stats.t.ppf(1.0 - alpha / 2.0, max(dof, 1))
            else:
                # normal approximation (good for dof > 30)
                p = 1.0 - alpha / 2.0
                # Abramowitz & Stegun rational approximation
                t = math.sqrt(-2.0 * math.log(1.0 - p))
                t_crit = t - (2.515517 + 0.802853*t + 0.010328*t*t) / (
                    1.0 + 1.432788*t + 0.189269*t*t + 0.001308*t*t*t)

            # evaluation grid
            axis_obj = self.parent.getAxes(
                (s.xAxis,) if s.variable == 'x' else (s.yAxis,))
            if axis_obj and axis_obj[0] is not None:
                axrange = axis_obj[0].getPlottedRange()
            else:
                axrange = [N.min(xvals), N.max(xvals)]
            npts = max(s.steps, 30)
            xeval = N.linspace(axrange[0], axrange[1], npts)

            # Jacobian + band variance
            func_str = s.function.strip()
            nparams = len(paramnames)
            pv = N.array([vals[p] for p in paramnames])

            # fast path for a + b*x
            if (nparams == 2 and
                    func_str in ('a + b*x', 'b*x + a',
                                 'a+b*x', 'b*x+a')):
                jac = N.column_stack([N.ones(npts), xeval])
                y_center = pv[0] + pv[1] * xeval
            else:
                # numerical Jacobian
                y_center = evalfunc(pv, xeval)
                jac = N.zeros((npts, nparams))
                for i in range(nparams):
                    h = max(abs(pv[i]) * 1e-5, 1e-8)
                    p_up = pv.copy()
                    p_up[i] += h
                    jac[:, i] = (evalfunc(p_up, xeval) - y_center) / h

            conf_var = N.einsum('ni,ij,nj->n', jac, cov_scaled, jac)
            conf_var = N.maximum(conf_var, 0)
            conf_width = t_crit * N.sqrt(conf_var)
            pred_width = t_crit * N.sqrt(conf_var + resid_var)

            band_x = xeval.tolist()
            conf_upper = (y_center + conf_width).tolist()
            conf_lower = (y_center - conf_width).tolist()
            pred_upper = (y_center + pred_width).tolist()
            pred_lower = (y_center - pred_width).tolist()

        # ── Save everything via Operations ───────────────────
        ops = []
        ops.append(document.OperationSettingSet(s.get('values'), vals))
        ops.append(document.OperationSettingSet(
            s.get('chi2'), float(chi2)))
        ops.append(document.OperationSettingSet(
            s.get('dof'), int(dof)))
        rdchi2 = float(chi2 / dof) if dof > 0 else -1.0
        ops.append(document.OperationSettingSet(
            s.get('redchi2'), rdchi2))
        ops.append(document.OperationSettingSet(
            s.get('paramErrors'), clean_errors))
        ops.append(document.OperationSettingSet(
            s.get('bandResidVar'), resid_var))
        ops.append(document.OperationSettingSet(
            s.get('bandXData'), band_x))
        ops.append(document.OperationSettingSet(
            s.get('bandConfUpper'), conf_upper))
        ops.append(document.OperationSettingSet(
            s.get('bandConfLower'), conf_lower))
        ops.append(document.OperationSettingSet(
            s.get('bandPredUpper'), pred_upper))
        ops.append(document.OperationSettingSet(
            s.get('bandPredLower'), pred_lower))

        expr = self.generateOutputExpr(vals)
        ops.append(document.OperationSettingSet(
            s.get('outExpr'), expr))

        self.updateOutputLabel(ops, vals, chi2, dof)

        d.applyOperation(
            document.OperationMultiple(ops, descr=_('fit')))

        # clear runtime cache
        self._path_cache = {}
        self._path_cache_key = None
        self._stale_checked = True

    def generateOutputExpr(self, vals):
        paramvals = dict(vals)
        s = self.settings
        if s.variable == 'x':
            paramvals['x'] = s.xData
        else:
            paramvals['y'] = s.yData
        parts = re.split('([^A-Za-z0-9.])', s.function)
        for i, p in enumerate(parts):
            if p in paramvals:
                parts[i] = str(paramvals[p])
        return ''.join(parts)

    # ── Drawing (render thread — read-only) ──────────────────

    def dataDraw(self, painter, axes, posn, cliprect):
        """Draw fitted curve and bands. Read-only — never modifies settings."""

        s = self.settings

        # draw bands from saved data
        has_bands = bool(s.bandXData)
        if has_bands and s.showPredBand:
            self._drawSavedBand(painter, axes, posn, cliprect,
                                s.bandXData, s.bandPredUpper,
                                s.bandPredLower, prediction=True)
        if has_bands and s.showConfBand:
            self._drawSavedBand(painter, axes, posn, cliprect,
                                s.bandXData, s.bandConfUpper,
                                s.bandConfLower, prediction=False)

        # draw the curve if fit has been done (chi2 > 0 or bands exist)
        if s.chi2 > 0 or has_bands:
            FunctionPlotter.dataDraw(self, painter, axes, posn, cliprect)

    def _drawSavedBand(self, painter, axes, posn, cliprect,
                       xdata, upper, lower, prediction=False):
        """Draw a band from saved data arrays. Read-only, no computation."""

        if not xdata or not upper or not lower:
            return
        if len(xdata) != len(upper) or len(xdata) != len(lower):
            return

        s = self.settings

        # cache key for QPainterPath
        cache_key = (
            id(xdata), prediction,
            tuple(round(posn[i], 1) for i in range(4)))
        band_key = 'pred' if prediction else 'conf'

        if (self._path_cache_key == cache_key and
                band_key in self._path_cache):
            path = self._path_cache[band_key]
        else:
            xarr = N.array(xdata)
            y_up = N.array(upper)
            y_lo = N.array(lower)

            if s.variable == 'x':
                xplt = axes[0].dataToPlotterCoords(posn, xarr)
                yplt_up = axes[1].dataToPlotterCoords(posn, y_up)
                yplt_lo = axes[1].dataToPlotterCoords(posn, y_lo)
            else:
                xplt = axes[1].dataToPlotterCoords(posn, xarr)
                yplt_up = axes[0].dataToPlotterCoords(posn, y_up)
                yplt_lo = axes[0].dataToPlotterCoords(posn, y_lo)

            poly = qt.QPolygonF()
            addNumpyToPolygonF(poly, xplt, yplt_lo)
            for i in range(len(xarr) - 1, -1, -1):
                poly.append(qt.QPointF(xplt[i], yplt_up[i]))

            path = qt.QPainterPath()
            path.addPolygon(poly)
            path.closeSubpath()

            clip_path = qt.QPainterPath()
            if isinstance(cliprect, qt.QRectF):
                clip_path.addRect(cliprect)
            else:
                clip_path.addRect(qt.QRectF(
                    qt.QPointF(cliprect[0], cliprect[1]),
                    qt.QPointF(cliprect[2], cliprect[3])))
            path = path.intersected(clip_path)

            if self._path_cache_key != cache_key:
                self._path_cache = {}
                self._path_cache_key = cache_key
            self._path_cache[band_key] = path

        # band color from fit line color
        try:
            bandcolor = s.Line.makeQPen(painter).color()
        except AttributeError:
            bandcolor = qt.QColor(100, 100, 200)

        alpha = 50 if prediction else 80
        bandcolor.setAlpha(alpha)
        painter.setPen(qt.Qt.PenStyle.NoPen)
        painter.setBrush(qt.QBrush(bandcolor))
        painter.drawPath(path)

# allow the factory to instantiate an x,y plotter
document.thefactory.register(Fit)
