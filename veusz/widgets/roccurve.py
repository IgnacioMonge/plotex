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

"""ROC (Receiver Operating Characteristic) curve widget.

Professional ROC curve following Prism/MedCalc standards:
  - Axes in percentage (0–100%) with standard labels
  - Smooth ROC curve with AUC and 95% CI
  - Diagonal chance reference line
  - Youden's optimal threshold point with annotation
  - Approximate pointwise sensitivity band
  - Slight axis padding so curve doesn't touch borders
"""

import math
import numpy as N

from .. import qtall as qt
from .. import document
from .. import setting
from .. import utils

from .plotters import GenericPlotter


def _(text, disambiguation=None, context="ROCCurve"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


class ROCCurve(GenericPlotter):
    """Plot an ROC (Receiver Operating Characteristic) curve."""

    typename = "roccurve"
    allowusercreation = True
    description = _("ROC curve (diagnostic performance)")

    def __init__(self, parent, **args):
        GenericPlotter.__init__(self, parent, **args)
        self._fpr = None
        self._tpr = None
        self._auc = None
        self._auc_se = None
        self._youden_idx = None
        self._youden_threshold = None
        self._n = 0
        self._changeset = -1

    def defaultAxisLabels(self):
        """Return default axis labels for this widget type."""
        return {
            "x": "100-Specificity",
            "y": "Sensitivity",
        }

    @classmethod
    def addSettings(klass, s):
        GenericPlotter.addSettings(s)

        # ── Data ────────────────────────────────────────────────────
        s.add(
            setting.DatasetExtended(
                "truthData",
                "",
                descr=_("Binary outcome data (0/1)"),
                usertext=_("Truth data"),
            ),
            0,
        )
        s.add(
            setting.DatasetExtended(
                "scoreData",
                "",
                descr=_("Continuous predictor score"),
                usertext=_("Score data"),
            ),
            1,
        )

        # ── Curve ──────────────────────────────────────────────────
        s.add(
            setting.Color(
                "color",
                "auto",
                descr=_("ROC curve color"),
                usertext=_("Color"),
                formatting=True,
            )
        )

        # ── Display ────────────────────────────────────────────────
        s.add(
            setting.Bool(
                "percentAxes",
                True,
                descr=_("Show axes as 0–100% instead of 0–1"),
                usertext=_("Percent axes"),
                formatting=True,
            )
        )
        s.add(
            setting.Bool(
                "showDiagonal",
                True,
                descr=_("Show chance line (diagonal)"),
                usertext=_("Show diagonal"),
                formatting=True,
            )
        )
        s.add(
            setting.Bool(
                "showAUC",
                True,
                descr=_("Show AUC value with 95% CI"),
                usertext=_("Show AUC"),
                formatting=True,
            )
        )
        s.add(
            setting.Bool(
                "showConfBand",
                False,
                descr=_("Show approximate pointwise sensitivity band"),
                usertext=_("Show approx. band"),
                formatting=True,
            )
        )
        s.add(
            setting.Bool(
                "showYouden",
                False,
                descr=_("Show optimal threshold (Youden's J)"),
                usertext=_("Show Youden's point"),
                formatting=True,
            )
        )
        s.add(
            setting.Bool(
                "showYoudenAnnot",
                False,
                descr=_("Annotate Youden point with sensitivity/specificity"),
                usertext=_("Youden annotation"),
                formatting=True,
            )
        )

        # ── AUC position ───────────────────────────────────────────
        s.add(
            setting.Choice(
                "aucPosition",
                ["bottom-right", "bottom-left", "top-right", "top-left", "center"],
                "bottom-right",
                descr=_("Position of AUC annotation"),
                usertext=_("AUC position"),
                formatting=True,
            )
        )

        # ── Youden marker ─────────────────────────────────────────
        s.add(
            setting.Marker(
                "youdenMarker",
                "diamond",
                descr=_("Marker for Youden's point"),
                usertext=_("Youden marker"),
                formatting=True,
            )
        )
        s.add(
            setting.DistancePt(
                "youdenMarkerSize",
                "6pt",
                descr=_("Youden marker size"),
                usertext=_("Youden size"),
                formatting=True,
            )
        )

        # ── Line styles ────────────────────────────────────────────
        s.add(
            setting.Line("PlotLine", descr=_("ROC curve line"), usertext=_("ROC line")),
            pixmap="settings_plotline",
        )
        s.add(
            setting.Line(
                "DiagonalLine",
                descr=_("Diagonal reference line"),
                usertext=_("Diagonal"),
            ),
            pixmap="settings_plotline",
        )
        s.add(
            setting.PlotterFill(
                "ConfFill", descr=_("CI band fill"), usertext=_("CI band")
            ),
            pixmap="settings_plotfillbelow",
        )
        s.add(
            setting.Text(
                "Label", descr=_("AUC annotation font"), usertext=_("AUC label")
            ),
            pixmap="settings_axislabel",
        )

        # defaults
        s.DiagonalLine.get("color").newDefault("grey")
        s.DiagonalLine.get("style").newDefault("dashed")
        s.PlotLine.get("color").newDefault("auto")
        s.PlotLine.get("width").newDefault("1.5pt")
        # CI band: light blue, 70% transparent, NOT hidden
        s.ConfFill.get("color").newDefault("auto")
        s.ConfFill.get("transparency").newDefault(70)
        s.ConfFill.get("hide").newDefault(False)

    # ─── Computation ──────────────────────────────────────────────

    def _computeROC(self, truth, scores):
        """Compute ROC curve, AUC, SE (Hanley-McNeil approx), and Youden."""
        order = N.argsort(-scores)
        truth_sorted = truth[order]
        scores_sorted = scores[order]

        P = N.sum(truth == 1)
        Neg = N.sum(truth == 0)

        if P == 0 or Neg == 0:
            return (N.array([0.0, 1.0]), N.array([0.0, 1.0]), 0.5, 0.0, 0, None)

        tp = N.cumsum(truth_sorted == 1).astype(float)
        fp = N.cumsum(truth_sorted == 0).astype(float)
        tpr = tp / P
        fpr = fp / Neg

        # remove duplicate fpr points (keep last = highest tpr)
        unique_mask = N.concatenate([N.diff(fpr) > 0, [True]])
        tpr_u = N.concatenate([[0.0], tpr[unique_mask]])
        fpr_u = N.concatenate([[0.0], fpr[unique_mask]])

        # AUC — N.trapezoid in numpy 2.x, N.trapz in 1.x
        _trapz = getattr(N, "trapezoid", None) or N.trapz
        auc = float(_trapz(tpr_u, fpr_u))

        # Hanley-McNeil (1982) SE approximation
        Q1 = auc / (2.0 - auc)
        Q2 = 2.0 * auc * auc / (1.0 + auc)
        se = math.sqrt(
            (
                auc * (1 - auc)
                + (P - 1) * (Q1 - auc * auc)
                + (Neg - 1) * (Q2 - auc * auc)
            )
            / (P * Neg)
        )

        # Youden's J = max(sensitivity + specificity - 1) = max(tpr - fpr)
        tpr_full = N.concatenate([[0.0], tpr])
        fpr_full = N.concatenate([[0.0], fpr])
        j_values = tpr_full - fpr_full
        youden_idx_full = int(N.argmax(j_values))

        # map back to unique arrays for drawing
        # find closest index in fpr_u
        if youden_idx_full > 0 and youden_idx_full <= len(scores_sorted):
            threshold = scores_sorted[min(youden_idx_full - 1, len(scores_sorted) - 1)]
        else:
            threshold = None

        # youden in the unique arrays
        youden_fpr = fpr_full[youden_idx_full]
        youden_tpr = tpr_full[youden_idx_full]
        youden_idx = int(N.argmin(N.abs(fpr_u - youden_fpr)))

        return fpr_u, tpr_u, auc, se, youden_idx, threshold

    def _updateCache(self):
        d = self.document
        if self._changeset == d.changeset:
            return
        self._changeset = d.changeset
        self._fpr = self._tpr = self._auc = None
        self._auc_se = None
        self._youden_idx = None
        self._youden_threshold = None

        s = self.settings
        truth_ds = s.get("truthData").getData(d)
        score_ds = s.get("scoreData").getData(d)
        if truth_ds is None or score_ds is None:
            return

        truth = truth_ds.data
        scores = score_ds.data
        if truth is None or scores is None:
            return

        try:
            truth = N.asarray(truth, dtype=float)
            scores = N.asarray(scores, dtype=float)
        except (ValueError, TypeError):
            return

        if truth.ndim != 1 or scores.ndim != 1:
            return

        minlen = min(len(truth), len(scores))
        if minlen < 2:
            return
        truth = truth[:minlen]
        scores = scores[:minlen]

        finite = N.isfinite(truth) & N.isfinite(scores)
        truth = truth[finite]
        scores = scores[finite]
        if len(truth) < 2:
            return

        truth_bin = (truth > 0.5).astype(float)
        fpr, tpr, auc, se, yi, thr = self._computeROC(truth_bin, scores)

        self._fpr = fpr
        self._tpr = tpr
        self._auc = auc
        self._auc_se = se
        self._youden_idx = yi
        self._youden_threshold = thr
        self._n = len(truth)

    # ─── Axis range ──────────────────────────────────────────────

    def affectsAxisRange(self):
        s = self.settings
        return ((s.xAxis, "sx"), (s.yAxis, "sy"))

    def getRange(self, axis, depname, axrange):
        s = self.settings
        if s.percentAxes:
            axrange[0] = min(axrange[0], -2.0)
            axrange[1] = max(axrange[1], 102.0)
        else:
            axrange[0] = min(axrange[0], -0.02)
            axrange[1] = max(axrange[1], 1.02)

    # ─── Key ─────────────────────────────────────────────────────

    def drawKeySymbol(self, number, painter, x, y, width, height):
        s = self.settings
        yp = y + height / 2
        if not s.PlotLine.hide:
            painter.setBrush(qt.QBrush())
            pen = s.PlotLine.makeQPen(painter)
            if s.color == "auto":
                pen.setColor(painter.docColor(self.autoColor(painter)))
            else:
                pen.setColor(s.get("color").color(painter))
            painter.setPen(pen)
            painter.drawLine(qt.QPointF(x, yp), qt.QPointF(x + width, yp))

    # ─── Drawing ─────────────────────────────────────────────────

    def dataDraw(self, painter, axes, posn, cliprect):
        s = self.settings
        self._updateCache()
        if self._fpr is None:
            return

        fpr = self._fpr
        tpr = self._tpr
        auc = self._auc
        auc_se = self._auc_se
        yi = self._youden_idx

        # scale factor for percentage mode
        scale = 100.0 if s.percentAxes else 1.0
        fpr_s = fpr * scale
        tpr_s = tpr * scale

        px = axes[0].dataToPlotterCoords(posn, fpr_s)
        py = axes[1].dataToPlotterCoords(posn, tpr_s)

        x1, y1, x2, y2 = posn
        pw = 2.0
        clip = qt.QRectF(qt.QPointF(x1 - pw, y1 - pw), qt.QPointF(x2 + pw, y2 + pw))

        # resolve curve color from master color setting
        curvecolor = s.get("color").color(painter)

        # ── 1. Diagonal ───────────────────────────────────────────
        if s.showDiagonal and not s.DiagonalLine.hide:
            d0, d1 = 0.0, 1.0 * scale
            dx = axes[0].dataToPlotterCoords(posn, N.array([d0, d1]))
            dy = axes[1].dataToPlotterCoords(posn, N.array([d0, d1]))
            painter.setPen(s.DiagonalLine.makeQPenWHide(painter))
            painter.setBrush(qt.QBrush())
            pts = qt.QPolygonF()
            pts.append(qt.QPointF(dx[0], dy[0]))
            pts.append(qt.QPointF(dx[1], dy[1]))
            utils.plotClippedPolyline(painter, clip, pts)

        # ── 2. Approximate pointwise band ────────────────────────
        if s.showConfBand and len(fpr) > 2:
            # Approximate pointwise SE on sensitivity (binomial).
            # This is NOT a simultaneous confidence band for the
            # entire ROC curve — it is a rough visual guide only.
            se_pts = N.sqrt(tpr * (1 - tpr) / max(self._n, 1))
            ci_upper = N.clip(tpr + 1.96 * se_pts, 0, 1) * scale
            ci_lower = N.clip(tpr - 1.96 * se_pts, 0, 1) * scale

            py_up = axes[1].dataToPlotterCoords(posn, ci_upper)
            py_lo = axes[1].dataToPlotterCoords(posn, ci_lower)

            poly = qt.QPolygonF()
            for i in range(len(fpr_s)):
                poly.append(qt.QPointF(px[i], py_up[i]))
            for i in range(len(fpr_s) - 1, -1, -1):
                poly.append(qt.QPointF(px[i], py_lo[i]))

            path = qt.QPainterPath()
            path.addPolygon(poly)
            path.closeSubpath()

            # clip to plot area
            clippath = qt.QPainterPath()
            clippath.addRect(clip)
            path = path.intersected(clippath)

            utils.brushExtFillPath(painter, s.ConfFill, path)

        # ── 3. ROC curve ──────────────────────────────────────────
        if not s.PlotLine.hide:
            pen = s.PlotLine.makeQPen(painter)
            painter.setPen(pen)
            curvecolor = pen.color()
            painter.setBrush(qt.QBrush())
            pts = qt.QPolygonF()
            utils.addNumpyToPolygonF(pts, px, py)
            utils.plotClippedPolyline(painter, clip, pts)

        # ── 4. Youden's point ─────────────────────────────────────
        if s.showYouden and yi is not None and yi < len(px):
            yx = px[yi]
            yy = py[yi]
            ms = s.get("youdenMarkerSize").convert(painter)
            painter.setPen(qt.QPen(curvecolor, 1.5))
            painter.setBrush(qt.QBrush(curvecolor))
            utils.plotMarkers(
                painter, N.array([yx]), N.array([yy]), s.youdenMarker, ms, clip=clip
            )

            # annotation
            if s.showYoudenAnnot:
                sens = tpr[yi] * 100
                spec = (1 - fpr[yi]) * 100
                thr = self._youden_threshold
                parts = ["Sens: %.1f%%" % sens, "Spec: %.1f%%" % spec]
                if thr is not None:
                    parts.append("Cutoff: %.2g" % thr)
                annot = "\n".join(parts)

                font = s.Label.makeQFont(painter)
                painter.setFont(font)
                painter.setPen(s.Label.makeQPen(painter))
                fm = qt.QFontMetricsF(font)
                tr = fm.boundingRect(
                    qt.QRectF(-500, -500, 1000, 1000),
                    int(qt.Qt.AlignmentFlag.AlignLeft),
                    annot,
                )
                tr.moveTopLeft(qt.QPointF(yx + ms, yy - tr.height()))
                # keep on screen
                if tr.right() > x2:
                    tr.moveRight(yx - ms)
                if tr.top() < y1:
                    tr.moveTop(yy + ms)
                painter.drawText(tr, int(qt.Qt.AlignmentFlag.AlignLeft), annot)

        # ── 5. AUC text ──────────────────────────────────────────
        if s.showAUC and auc is not None and not s.Label.hide:
            ci_lo = max(auc - 1.96 * auc_se, 0)
            ci_hi = min(auc + 1.96 * auc_se, 1)
            text = "AUC = %.3f (95%% CI: %.3f\u2013%.3f)" % (auc, ci_lo, ci_hi)

            font = s.Label.makeQFont(painter)
            painter.setFont(font)
            painter.setPen(s.Label.makeQPen(painter))
            fm = qt.QFontMetricsF(font)
            textw = fm.horizontalAdvance(text)
            texth = fm.height()
            margin = 8

            pos = s.aucPosition
            if pos == "bottom-right":
                tx = x2 - textw - margin
                ty = y2 - margin
            elif pos == "bottom-left":
                tx = x1 + margin
                ty = y2 - margin
            elif pos == "top-right":
                tx = x2 - textw - margin
                ty = y1 + texth + margin
            elif pos == "top-left":
                tx = x1 + margin
                ty = y1 + texth + margin
            else:
                tx = (x1 + x2 - textw) / 2
                ty = (y1 + y2 + texth) / 2

            rect = qt.QRectF(tx, ty - texth, textw + 2, texth + 2)
            painter.drawText(
                rect,
                int(qt.Qt.AlignmentFlag.AlignLeft | qt.Qt.AlignmentFlag.AlignVCenter),
                text,
            )


document.thefactory.register(ROCCurve)
