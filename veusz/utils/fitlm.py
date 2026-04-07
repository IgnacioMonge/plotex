#    Copyright (C) 2005 Jeremy S. Sanders
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

"""
Numerical fitting of functions to data.

Uses scipy.optimize.least_squares (Trust Region Reflective) for robust,
fast fitting with automatic Jacobian via finite differences in compiled C.
"""

import sys
import numpy as N

def fitLM(func, params, xvals, yvals, errors,
          stopdeltalambda=1e-5,
          deltaderiv=1e-5, maxiters=200, Lambda=1e-4, log=None):
    """Fit func to data using scipy least_squares (or fallback LM).

    func(params, xvals) -> yvals
    params: initial parameter values (numpy array, modified in place)
    xvals, yvals, errors: data arrays
    log: file-like object for output (defaults to sys.stdout)
    Returns (params, chi2, dof, param_errors, covariance_matrix)
    """

    try:
        from scipy.optimize import least_squares
        return _fitScipy(func, params, xvals, yvals, errors, maxiters,
                         log=log)
    except ImportError:
        return _fitLMFallback(func, params, xvals, yvals, errors,
                              stopdeltalambda, deltaderiv, maxiters, Lambda,
                              log=log)


def _fitScipy(func, params, xvals, yvals, errors, maxiters, log=None):
    """Fast fitting using scipy.optimize.least_squares."""

    import warnings
    from scipy.optimize import least_squares

    weights = 1.0 / N.maximum(N.abs(errors), 1e-30)

    def residuals(p):
        r = func(p, xvals) - yvals
        # clamp infinities to large values to keep optimizer stable
        r = N.where(N.isfinite(r), r, 0.)
        return r * weights

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        result = least_squares(
            residuals, params,
            method='trf',
            max_nfev=maxiters * len(params),
            ftol=1e-10, xtol=1e-10, gtol=1e-10,
        )

    params[:] = result.x
    dof = max(len(yvals) - len(params), 1)
    chi2 = (result.fun**2).sum()  # weighted residuals squared

    # convert back to unweighted chi2
    residuals_unw = func(params, xvals) - yvals
    safe_errors = N.maximum(N.abs(errors), 1e-30)
    chi2 = ((residuals_unw / safe_errors)**2).sum()

    # covariance from Jacobian: cov = inv(J^T J)
    # Note: return UNSCALED covariance — fit.py scales by redchi2 for bands
    cov = None
    param_errors = N.zeros(len(params))
    try:
        J = result.jac
        JTJ = J.T @ J
        cov = N.linalg.inv(JTJ)
        # parameter errors = sqrt(diag(cov)) — already in correct units
        # because J is from weighted residuals
        param_errors = N.sqrt(N.abs(N.diag(cov)))
    except Exception:
        pass

    if log is None:
        log = sys.stdout
    print("chi^2 = %g, dof = %i, reduced-chi^2 = %g" % (
        chi2, dof, chi2 / dof), file=log)
    print("Parameter errors: " + ", ".join(
        ["%g" % e for e in param_errors]), file=log)

    return (params, chi2, dof, param_errors, cov)


def _fitLMFallback(func, params, xvals, yvals, errors,
                   stopdeltalambda, deltaderiv, maxiters, Lambda, log=None):
    """Legacy Levenberg-Marquardt fallback (no scipy)."""

    try:
        import numpy.linalg as NLA
    except ImportError:
        import scipy.linalg as NLA

    inve2 = 1. / errors**2
    oldfunc = func(params, xvals)
    chi2 = ((oldfunc - yvals)**2 * inve2).sum()

    beta = N.zeros(len(params), dtype='float64')
    alpha = N.zeros((len(params), len(params)), dtype='float64')
    derivs = N.zeros((len(params), len(xvals)), dtype='float64')

    done = False
    iters = 0
    while iters < maxiters and not done:
        for i in range(len(params)):
            params[i] += deltaderiv
            new_func = func(params, xvals)
            chi2_new = ((new_func - yvals)**2 * inve2).sum()
            params[i] -= deltaderiv

            beta[i] = chi2_new - chi2
            derivs[i] = new_func - oldfunc

        beta *= (-0.5 / deltaderiv)
        derivs *= (1. / deltaderiv)

        for j in range(len(params)):
            for k in range(j + 1):
                v = (derivs[j] * derivs[k] * inve2).sum()
                alpha[j][k] = v
                alpha[k][j] = v

        alpha *= 1. + N.identity(len(params), dtype='float64') * Lambda
        deltas = NLA.solve(alpha, beta)

        new_params = params + deltas
        new_func = func(new_params, xvals)
        new_chi2 = ((new_func - yvals)**2 * inve2).sum()

        if N.isnan(new_chi2):
            sys.stderr.write('Chi2 is NaN. Aborting fit.\n')
            break

        if new_chi2 > chi2:
            Lambda *= 10.
        else:
            done = chi2 - new_chi2 < stopdeltalambda
            chi2 = new_chi2
            params = new_params
            oldfunc = new_func
            Lambda *= 0.1
            iters += 1

    if not done:
        sys.stderr.write("Warning: maximum number of iterations reached\n")

    if log is None:
        log = sys.stdout
    dof = max(len(yvals) - len(params), 1)
    print("chi^2 = %g, dof = %i, reduced-chi^2 = %g" % (
        chi2, dof, chi2 / dof), file=log)

    cov = None
    param_errors = N.zeros(len(params))
    try:
        for j in range(len(params)):
            for k in range(j + 1):
                v = (derivs[j] * derivs[k] * inve2).sum()
                alpha[j][k] = v
                alpha[k][j] = v
        cov = NLA.inv(alpha)
        param_errors = N.sqrt(N.abs(N.diag(cov)))
    except Exception:
        pass

    return (params, chi2, dof, param_errors, cov)
