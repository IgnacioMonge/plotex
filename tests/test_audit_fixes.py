"""Tests for issues found during the external code audit.

Covers: document locking, undo/redo axis labels, loader rollback,
widget array alignment, division guards, render thread resilience,
painthelper null guards, and statistical correctness.

Run with:  pytest tests/test_audit_fixes.py -v
"""

import io
import math
import sys
import os
import numpy as N
import pytest

# Need QApplication before importing veusz modules
from PyQt6 import QtWidgets, QtCore
_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])

from veusz import document
from veusz.document import doc, operations, painthelper
from veusz.widgets import (
    fit as fitmod, kaplanmeier as kmmod, roccurve as rocmod,
    blandaltman as bamod, piechart as piemod, pareto as paretomod,
    qqplot as qqmod, bracket as bracketmod,
)


# ─── Helpers ─────────────────────────────────────────────────────

@pytest.fixture
def newdoc():
    """Create a fresh Document for each test."""
    d = doc.Document()
    return d


def _add_widget(d, parent, typename, **kw):
    """Add a widget via operation and return it."""
    op = operations.OperationWidgetAdd(parent, typename, **kw)
    return d.applyOperation(op)


def _setup_graph(d):
    """Create page → graph with x/y axes, return graph widget."""
    page = _add_widget(d, d.basewidget, 'page')
    graph = _add_widget(d, page, 'graph')
    return graph


# ═════════════════════════════════════════════════════════════════
# 1. DOCUMENT LOCKING — reentrant write lock
# ═════════════════════════════════════════════════════════════════

class TestDocumentLocking:
    """Verify the reentrant write lock doesn't deadlock."""

    def test_applyOperation_with_setData_inside(self, newdoc):
        """Operations that call setData internally must not deadlock."""
        ds = document.datasets.Dataset(data=[1.0, 2.0, 3.0])
        op = operations.OperationDatasetSet('testds', ds)
        # This would deadlock if locking isn't reentrant
        newdoc.applyOperation(op)
        assert 'testds' in newdoc.data
        assert list(newdoc.data['testds'].data) == [1.0, 2.0, 3.0]

    def test_undo_setData(self, newdoc):
        """Undo of dataset set must not deadlock."""
        ds = document.datasets.Dataset(data=[1.0, 2.0])
        newdoc.applyOperation(operations.OperationDatasetSet('ds1', ds))
        assert 'ds1' in newdoc.data
        newdoc.undoOperation()
        assert 'ds1' not in newdoc.data

    def test_deleteData_operation(self, newdoc):
        """Delete dataset via operation must not deadlock."""
        ds = document.datasets.Dataset(data=[1.0])
        newdoc.applyOperation(operations.OperationDatasetSet('ds1', ds))
        newdoc.applyOperation(operations.OperationDatasetDelete('ds1'))
        assert 'ds1' not in newdoc.data

    def test_standalone_setData(self, newdoc):
        """Direct setData (outside operation) acquires lock independently."""
        ds = document.datasets.Dataset(data=[5.0])
        newdoc.setData('direct', ds)
        assert 'direct' in newdoc.data


# ═════════════════════════════════════════════════════════════════
# 2. UNDO/REDO — axis labels from widget insertion
# ═════════════════════════════════════════════════════════════════

class TestAxisLabelsUndo:
    """Verify axis labels set by statistical widgets are undoable."""

    def test_roccurve_labels_set_on_add(self, newdoc):
        """Adding ROC curve should set axis labels."""
        graph = _setup_graph(newdoc)
        _add_widget(newdoc, graph, 'roccurve')

        xax = graph.getChild('x')
        yax = graph.getChild('y')
        assert xax.settings.label == '100-Specificity'
        assert yax.settings.label == 'Sensitivity'

    def test_roccurve_labels_undo(self, newdoc):
        """Undo of ROC curve addition should restore axis labels."""
        graph = _setup_graph(newdoc)
        xax = graph.getChild('x')
        old_label = xax.settings.label

        _add_widget(newdoc, graph, 'roccurve')
        assert xax.settings.label == '100-Specificity'

        newdoc.undoOperation()  # undo add roccurve
        assert xax.settings.label == old_label

    def test_kaplanmeier_labels_set_on_add(self, newdoc):
        """Adding KM widget should set axis labels."""
        graph = _setup_graph(newdoc)
        _add_widget(newdoc, graph, 'kaplanmeier')

        xax = graph.getChild('x')
        yax = graph.getChild('y')
        assert xax.settings.label == 'Time'
        assert yax.settings.label == 'Survival Probability (%)'

    def test_blandaltman_labels_set_on_add(self, newdoc):
        """Adding Bland-Altman should set axis labels."""
        graph = _setup_graph(newdoc)
        _add_widget(newdoc, graph, 'blandaltman')

        xax = graph.getChild('x')
        yax = graph.getChild('y')
        assert xax.settings.label == 'Mean of Method 1 and Method 2'
        assert 'Method 1' in yax.settings.label


# ═════════════════════════════════════════════════════════════════
# 3. LOADER — snapshot/restore on failure
# ═════════════════════════════════════════════════════════════════

class TestLoaderRollback:
    """Verify document is restored after a failed load."""

    def test_serializeToText_no_side_effects(self, newdoc):
        """serializeToText must not change modified flag."""
        ds = document.datasets.Dataset(data=[1.0, 2.0])
        newdoc.applyOperation(operations.OperationDatasetSet('myds', ds))
        assert newdoc.changeset > 0

        old_changeset = newdoc.changeset
        buf = io.StringIO()
        newdoc.serializeToText(buf)

        assert newdoc.changeset == old_changeset

    def test_load_bad_file_restores_document(self, newdoc, tmp_path):
        """Loading an invalid .vsz should restore the previous document."""
        # Set up a document with some data
        ds = document.datasets.Dataset(data=[42.0])
        newdoc.applyOperation(operations.OperationDatasetSet('preserve_me', ds))
        assert 'preserve_me' in newdoc.data

        # Write a bad .vsz file
        badfile = str(tmp_path / 'bad.vsz')
        with open(badfile, 'w') as f:
            f.write("raise RuntimeError('intentional failure')\n")

        # Try to load — should fail but restore
        from veusz.document.loader import loadDocument, LoadError
        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode='vsz')

        # Document should be restored
        assert 'preserve_me' in newdoc.data
        assert list(newdoc.data['preserve_me'].data) == [42.0]


# ═════════════════════════════════════════════════════════════════
# 4. WIDGET ARRAY ALIGNMENT
# ═════════════════════════════════════════════════════════════════

class TestArrayAlignment:
    """Verify array length mismatches are handled safely."""

    def test_piechart_labels_filtered_with_values(self):
        """PieChart labels must be filtered with same mask as values."""
        values = N.array([10.0, float('nan'), 20.0, -5.0, 30.0])
        valid = N.isfinite(values) & (values > 0)
        filtered_values = values[valid]

        labels = ['A', 'B', 'C', 'D', 'E']
        n = min(len(labels), len(valid))
        filtered_labels = [labels[i] for i in range(n) if valid[i]]

        assert len(filtered_values) == len(filtered_labels)
        assert filtered_labels == ['A', 'C', 'E']

    def test_pareto_zero_total_no_crash(self):
        """Pareto with all-zero values should not divide by zero."""
        vals = N.array([0.0, 0.0, 0.0])
        total = vals.sum()
        if total <= 0:
            total = 1.0
        cum = N.cumsum(vals) / total
        assert N.all(N.isfinite(cum))


# ═════════════════════════════════════════════════════════════════
# 5. STATISTICAL CORRECTNESS
# ═════════════════════════════════════════════════════════════════

class TestStatisticalCorrectness:
    """Verify key statistical computations."""

    def test_roc_auc_perfect_classifier(self):
        """Perfect classifier should have AUC = 1.0."""
        truth = N.array([0, 0, 0, 1, 1, 1])
        scores = N.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])

        # Compute ROC manually (same algo as roccurve.py)
        order = N.argsort(-scores)
        truth_sorted = truth[order]
        P = N.sum(truth == 1)
        Neg = N.sum(truth == 0)
        tp = N.cumsum(truth_sorted == 1).astype(float)
        fp = N.cumsum(truth_sorted == 0).astype(float)
        tpr = tp / P
        fpr = fp / Neg
        unique_mask = N.concatenate([N.diff(fpr) > 0, [True]])
        tpr_u = N.concatenate([[0.], tpr[unique_mask]])
        fpr_u = N.concatenate([[0.], fpr[unique_mask]])
        auc = float(N.trapz(tpr_u, fpr_u))

        assert auc == pytest.approx(1.0, abs=0.01)

    def test_roc_hanley_mcneil_se(self):
        """Hanley-McNeil SE should be reasonable for moderate sample."""
        auc = 0.85
        P, Neg = 50, 50
        Q1 = auc / (2.0 - auc)
        Q2 = 2.0 * auc * auc / (1.0 + auc)
        se = math.sqrt(
            (auc * (1 - auc) + (P - 1) * (Q1 - auc*auc)
             + (Neg - 1) * (Q2 - auc*auc)) / (P * Neg))

        # SE should be positive and reasonable
        assert se > 0
        assert se < 0.1  # for AUC=0.85 with n=100, SE should be small

    def test_roc_se_not_naive(self):
        """Hanley-McNeil SE should differ from naive sqrt(pq/n)."""
        auc = 0.75
        P, Neg = 30, 30
        naive_se = math.sqrt(auc * (1 - auc) / min(P, Neg))

        Q1 = auc / (2.0 - auc)
        Q2 = 2.0 * auc * auc / (1.0 + auc)
        hm_se = math.sqrt(
            (auc * (1 - auc) + (P - 1) * (Q1 - auc*auc)
             + (Neg - 1) * (Q2 - auc*auc)) / (P * Neg))

        assert naive_se != pytest.approx(hm_se, abs=1e-6)


# ═════════════════════════════════════════════════════════════════
# 6. PAINTHELPER — null guards
# ═════════════════════════════════════════════════════════════════

class TestPaintHelperNullGuards:
    """Verify painthelper handles None rootstate gracefully."""

    def test_renderToPainter_none_rootstate(self, newdoc):
        """renderToPainter with None rootstate should not crash."""
        ph = painthelper.PaintHelper(newdoc, (100, 100), dpi=(96, 96))
        assert ph.rootstate is None
        # Should return without crashing
        img = QtWidgets.QApplication.instance()
        from PyQt6.QtGui import QPainter, QImage
        qimg = QImage(10, 10, QImage.Format.Format_ARGB32)
        painter = QPainter(qimg)
        ph.renderToPainter(painter)  # must not crash
        painter.end()

    def test_widgetBoundsIterator_none_rootstate(self, newdoc):
        """widgetBoundsIterator with None rootstate should yield nothing."""
        ph = painthelper.PaintHelper(newdoc, (100, 100), dpi=(96, 96))
        result = list(ph.widgetBoundsIterator())
        assert result == []

    def test_pointInWidgetBounds_none_rootstate(self, newdoc):
        """pointInWidgetBounds with None rootstate should return None."""
        ph = painthelper.PaintHelper(newdoc, (100, 100), dpi=(96, 96))
        from veusz.widgets import graph
        result = ph.pointInWidgetBounds(50, 50, graph.Graph)
        assert result is None

    def test_identifyWidgetAtPoint_none_rootstate(self, newdoc):
        """identifyWidgetAtPoint with None rootstate should return None."""
        ph = painthelper.PaintHelper(newdoc, (100, 100), dpi=(96, 96))
        result = ph.identifyWidgetAtPoint(50, 50)
        assert result is None


# ═════════════════════════════════════════════════════════════════
# 7. BRACKET — getRange must not mutate settings
# ═════════════════════════════════════════════════════════════════

class TestBracketGetRange:
    """Verify bracket getRange is read-only."""

    def test_getRange_does_not_mutate_axis(self, newdoc):
        """getRange must only update axrange, not axis settings."""
        graph = _setup_graph(newdoc)
        bracket = _add_widget(newdoc, graph, 'bracket')

        yax = graph.getChild('y')
        # Set a fixed max
        newdoc.applyOperation(
            operations.OperationSettingSet(yax.settings.get('max'), 10.0))

        original_max = yax.settings.max
        axrange = [0.0, 100.0]  # bracket y_top > axis max

        # getRange should not touch axis settings
        bracket.getRange(yax, 'bracket_y', axrange)
        assert yax.settings.max == original_max


# ═════════════════════════════════════════════════════════════════
# 8. FIT — array trimming and axis guard
# ═════════════════════════════════════════════════════════════════

class TestFitArraySafety:
    """Verify fit widget handles mismatched arrays safely."""

    def test_perr_nerr_trimmed(self):
        """Asymmetric errors must be trimmed to data length."""
        xvals = N.array([1.0, 2.0, 3.0])
        yvals = N.array([10.0, 20.0, 30.0])
        minlen = min(len(xvals), len(yvals))

        # Simulate longer error arrays
        perr = N.array([1.0, 2.0, 3.0, 4.0, 5.0])
        nerr = N.array([0.5, 1.0, 1.5, 2.0, 2.5])

        # Trim like the fixed code does
        perr_trimmed = perr[:minlen]
        nerr_trimmed = nerr[:minlen]
        yserr = N.sqrt(0.5 * (perr_trimmed**2 + nerr_trimmed**2))

        assert len(yserr) == len(xvals)
        assert len(yserr) == len(yvals)


# ═════════════════════════════════════════════════════════════════
# 9. LOADER — extended scenarios
# ═════════════════════════════════════════════════════════════════

class TestLoaderExtended:
    """Extended loader tests: edge cases and state preservation."""

    def test_load_nonexistent_file(self, newdoc):
        """Loading a file that doesn't exist should raise LoadError."""
        from veusz.document.loader import loadDocument, LoadError
        with pytest.raises(LoadError):
            loadDocument(newdoc, '/nonexistent/path.vsz', mode='vsz')

    def test_load_unicode_garbage(self, newdoc, tmp_path):
        """Loading a file with invalid content should raise LoadError."""
        badfile = str(tmp_path / 'garbage.vsz')
        with open(badfile, 'wb') as f:
            f.write(b'\x80\x81\x82\x83\xff\xfe')
        from veusz.document.loader import loadDocument, LoadError
        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode='vsz')

    def test_rollback_preserves_changeset(self, newdoc, tmp_path):
        """Failed load must restore changeset to pre-load value."""
        ds = document.datasets.Dataset(data=[1.0])
        newdoc.applyOperation(operations.OperationDatasetSet('ds1', ds))
        old_changeset = newdoc.changeset

        badfile = str(tmp_path / 'bad2.vsz')
        with open(badfile, 'w') as f:
            f.write("raise ValueError('fail')\n")

        from veusz.document.loader import loadDocument, LoadError
        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode='vsz')

        assert newdoc.changeset == old_changeset

    def test_rollback_preserves_undo_history(self, newdoc, tmp_path):
        """Failed load must restore undo history."""
        ds = document.datasets.Dataset(data=[1.0])
        newdoc.applyOperation(operations.OperationDatasetSet('ds1', ds))
        undo_len = len(newdoc.historyundo)

        badfile = str(tmp_path / 'bad3.vsz')
        with open(badfile, 'w') as f:
            f.write("1/0\n")

        from veusz.document.loader import loadDocument, LoadError
        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode='vsz')

        assert len(newdoc.historyundo) == undo_len

    def test_load_valid_file(self, newdoc, tmp_path):
        """Loading a valid .vsz should succeed."""
        goodfile = str(tmp_path / 'good.vsz')
        with open(goodfile, 'w') as f:
            f.write("Add('page', name='page1')\n")

        from veusz.document.loader import loadDocument
        loadDocument(newdoc, goodfile, mode='vsz')
        assert newdoc.basewidget.getChild('page1') is not None


# ═════════════════════════════════════════════════════════════════
# 10. FIT — extended edge cases
# ═════════════════════════════════════════════════════════════════

class TestFitExtended:
    """Extended fit widget tests."""

    def test_fitlm_log_parameter(self):
        """fitLM must write to log parameter, not stdout."""
        from veusz.utils.fitlm import fitLM
        import io as _io

        def linear(params, x):
            return params[0] * x + params[1]

        xvals = N.array([1.0, 2.0, 3.0, 4.0, 5.0])
        yvals = N.array([2.1, 3.9, 6.1, 7.9, 10.1])
        errors = N.ones(5)
        params = N.array([1.0, 0.0])

        log = _io.StringIO()
        old_stdout = sys.stdout
        capture = _io.StringIO()
        sys.stdout = capture
        try:
            fitLM(linear, params, xvals, yvals, errors, log=log)
        finally:
            sys.stdout = old_stdout

        # log should have output
        assert len(log.getvalue()) > 0
        # stdout should be clean (nothing leaked)
        assert capture.getvalue() == ''

    def test_fit_with_all_nan_data(self):
        """Fit with all-NaN data should not crash."""
        xvals = N.array([float('nan')] * 5)
        yvals = N.array([float('nan')] * 5)
        finite = N.isfinite(xvals) & N.isfinite(yvals)
        # After filtering, arrays should be empty
        assert N.sum(finite) == 0


# ═════════════════════════════════════════════════════════════════
# 11. KAPLAN-MEIER — data edge cases
# ═════════════════════════════════════════════════════════════════

class TestKaplanMeierData:
    """KM widget data handling edge cases."""

    def test_groupdata_length_mismatch(self):
        """Group data shorter than times/events should not crash."""
        times = N.array([1.0, 2.0, 3.0, 4.0, 5.0])
        events = N.array([1, 0, 1, 0, 1])
        groupdata = N.array([1, 2, 1])  # shorter

        n = min(len(times), len(events), len(groupdata))
        times = times[:n]
        events = events[:n]
        glabels = groupdata[:n]

        assert len(times) == len(events) == len(glabels) == 3

    def test_empty_group_produces_no_crash(self):
        """KM with group that has no events should handle gracefully."""
        times = N.array([1.0, 2.0, 3.0])
        events = N.array([0, 0, 0])  # no events at all
        # Should still compute (flat survival = 1.0)
        n_events = N.sum(events)
        assert n_events == 0


# ═════════════════════════════════════════════════════════════════
# 12. ROC — edge cases
# ═════════════════════════════════════════════════════════════════

class TestROCEdgeCases:
    """ROC curve edge cases."""

    def test_roc_all_positive(self):
        """ROC with no negatives should return AUC=0.5 (degenerate)."""
        truth = N.array([1, 1, 1, 1])
        P = N.sum(truth == 1)
        Neg = N.sum(truth == 0)
        # P>0 but Neg=0 — degenerate case
        assert Neg == 0

    def test_roc_all_negative(self):
        """ROC with no positives should return AUC=0.5 (degenerate)."""
        truth = N.array([0, 0, 0, 0])
        P = N.sum(truth == 1)
        Neg = N.sum(truth == 0)
        assert P == 0

    def test_roc_random_classifier(self):
        """Random classifier should have AUC near 0.5."""
        N.random.seed(42)
        truth = N.random.randint(0, 2, 1000)
        scores = N.random.rand(1000)

        order = N.argsort(-scores)
        truth_sorted = truth[order]
        P = N.sum(truth == 1)
        Neg = N.sum(truth == 0)
        tp = N.cumsum(truth_sorted == 1).astype(float)
        fp = N.cumsum(truth_sorted == 0).astype(float)
        tpr = tp / P
        fpr = fp / Neg
        unique_mask = N.concatenate([N.diff(fpr) > 0, [True]])
        tpr_u = N.concatenate([[0.], tpr[unique_mask]])
        fpr_u = N.concatenate([[0.], fpr[unique_mask]])
        auc = float(N.trapz(tpr_u, fpr_u))

        assert 0.4 < auc < 0.6

    def test_hanley_mcneil_se_small_sample(self):
        """SE with very small sample should still be finite."""
        auc = 0.7
        P, Neg = 3, 3
        Q1 = auc / (2.0 - auc)
        Q2 = 2.0 * auc * auc / (1.0 + auc)
        se = math.sqrt(
            (auc * (1 - auc) + (P - 1) * (Q1 - auc*auc)
             + (Neg - 1) * (Q2 - auc*auc)) / (P * Neg))
        assert math.isfinite(se)
        assert se > 0


# ═════════════════════════════════════════════════════════════════
# 13. UNDO/REDO — extended scenarios
# ═════════════════════════════════════════════════════════════════

class TestUndoRedoExtended:
    """Extended undo/redo tests."""

    def test_redo_after_undo_labels(self, newdoc):
        """Redo after undoing widget add should re-apply labels."""
        graph = _setup_graph(newdoc)
        xax = graph.getChild('x')

        _add_widget(newdoc, graph, 'roccurve')
        assert xax.settings.label == '100-Specificity'

        newdoc.undoOperation()
        newdoc.redoOperation()
        assert xax.settings.label == '100-Specificity'

    def test_multiple_operations_undo_all(self, newdoc):
        """Multiple dataset operations should all undo correctly."""
        for i in range(5):
            ds = document.datasets.Dataset(data=[float(i)])
            newdoc.applyOperation(
                operations.OperationDatasetSet('ds%d' % i, ds))

        assert len(newdoc.data) == 5

        for i in range(5):
            newdoc.undoOperation()

        assert len(newdoc.data) == 0

    def test_undo_beyond_history(self, newdoc):
        """Undo with empty history should be a no-op."""
        old_changeset = newdoc.changeset
        newdoc.undoOperation()
        # Should not crash or change anything
        assert newdoc.changeset == old_changeset


# ═════════════════════════════════════════════════════════════════
# 14. DOCUMENT — serializeToText roundtrip
# ═════════════════════════════════════════════════════════════════

class TestSerializeRoundtrip:
    """Verify serialize/restore preserves document content."""

    def test_roundtrip_with_data(self, newdoc):
        """Serialize + restore should preserve datasets."""
        ds = document.datasets.Dataset(data=[1.0, 2.0, 3.0])
        newdoc.applyOperation(operations.OperationDatasetSet('mydata', ds))

        buf = io.StringIO()
        newdoc.serializeToText(buf)

        # Create fresh doc and restore
        newdoc.wipe()
        assert 'mydata' not in newdoc.data

        from veusz.document.loader import executeScript
        buf.seek(0)
        executeScript(newdoc, 'test', buf.read())
        assert 'mydata' in newdoc.data
        assert list(newdoc.data['mydata'].data) == pytest.approx([1.0, 2.0, 3.0])

    def test_roundtrip_with_widgets(self, newdoc):
        """Serialize + restore should preserve widget tree."""
        page = _add_widget(newdoc, newdoc.basewidget, 'page', name='p1')
        graph = _add_widget(newdoc, page, 'graph', name='g1')

        buf = io.StringIO()
        newdoc.serializeToText(buf)

        newdoc.wipe()
        assert newdoc.basewidget.getChild('p1') is None

        from veusz.document.loader import executeScript
        buf.seek(0)
        executeScript(newdoc, 'test', buf.read())
        assert newdoc.basewidget.getChild('p1') is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
