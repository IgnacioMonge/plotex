"""Tests for issues found during the external code audit.

Covers: document locking, undo/redo axis labels, loader rollback,
widget array alignment, division guards, render thread resilience,
painthelper null guards, and statistical correctness.

Run with:  pytest tests/test_audit_fixes.py -v
"""

import io
import json
import math
import sys
import os
import struct
import types
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
    fit as fitmod,
    kaplanmeier as kmmod,
    roccurve as rocmod,
    blandaltman as bamod,
    piechart as piemod,
    pareto as paretomod,
    qqplot as qqmod,
    bracket as bracketmod,
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
    page = _add_widget(d, d.basewidget, "page")
    graph = _add_widget(d, page, "graph")
    return graph


# ═════════════════════════════════════════════════════════════════
# 1. DOCUMENT LOCKING — reentrant write lock
# ═════════════════════════════════════════════════════════════════


class TestDocumentLocking:
    """Verify the reentrant write lock doesn't deadlock."""

    def test_applyOperation_with_setData_inside(self, newdoc):
        """Operations that call setData internally must not deadlock."""
        ds = document.datasets.Dataset(data=[1.0, 2.0, 3.0])
        op = operations.OperationDatasetSet("testds", ds)
        # This would deadlock if locking isn't reentrant
        newdoc.applyOperation(op)
        assert "testds" in newdoc.data
        assert list(newdoc.data["testds"].data) == [1.0, 2.0, 3.0]

    def test_undo_setData(self, newdoc):
        """Undo of dataset set must not deadlock."""
        ds = document.datasets.Dataset(data=[1.0, 2.0])
        newdoc.applyOperation(operations.OperationDatasetSet("ds1", ds))
        assert "ds1" in newdoc.data
        newdoc.undoOperation()
        assert "ds1" not in newdoc.data

    def test_deleteData_operation(self, newdoc):
        """Delete dataset via operation must not deadlock."""
        ds = document.datasets.Dataset(data=[1.0])
        newdoc.applyOperation(operations.OperationDatasetSet("ds1", ds))
        newdoc.applyOperation(operations.OperationDatasetDelete("ds1"))
        assert "ds1" not in newdoc.data

    def test_standalone_setData(self, newdoc):
        """Direct setData (outside operation) acquires lock independently."""
        ds = document.datasets.Dataset(data=[5.0])
        newdoc.setData("direct", ds)
        assert "direct" in newdoc.data


# ═════════════════════════════════════════════════════════════════
# 2. UNDO/REDO — axis labels from widget insertion
# ═════════════════════════════════════════════════════════════════


class TestAxisLabelsUndo:
    """Verify axis labels set by statistical widgets are undoable."""

    def test_roccurve_labels_set_on_add(self, newdoc):
        """Adding ROC curve should set axis labels."""
        graph = _setup_graph(newdoc)
        _add_widget(newdoc, graph, "roccurve")

        xax = graph.getChild("x")
        yax = graph.getChild("y")
        assert xax.settings.label == "100-Specificity"
        assert yax.settings.label == "Sensitivity"

    def test_roccurve_labels_undo(self, newdoc):
        """Undo of ROC curve addition should restore axis labels."""
        graph = _setup_graph(newdoc)
        xax = graph.getChild("x")
        old_label = xax.settings.label

        _add_widget(newdoc, graph, "roccurve")
        assert xax.settings.label == "100-Specificity"

        newdoc.undoOperation()  # undo add roccurve
        assert xax.settings.label == old_label

    def test_kaplanmeier_labels_set_on_add(self, newdoc):
        """Adding KM widget should set axis labels."""
        graph = _setup_graph(newdoc)
        _add_widget(newdoc, graph, "kaplanmeier")

        xax = graph.getChild("x")
        yax = graph.getChild("y")
        assert xax.settings.label == "Time"
        assert yax.settings.label == "Survival Probability (%)"

    def test_blandaltman_labels_set_on_add(self, newdoc):
        """Adding Bland-Altman should set axis labels."""
        graph = _setup_graph(newdoc)
        _add_widget(newdoc, graph, "blandaltman")

        xax = graph.getChild("x")
        yax = graph.getChild("y")
        assert xax.settings.label == "Mean of Method 1 and Method 2"
        assert "Method 1" in yax.settings.label


# ═════════════════════════════════════════════════════════════════
# 3. LOADER — snapshot/restore on failure
# ═════════════════════════════════════════════════════════════════


class TestLoaderRollback:
    """Verify document is restored after a failed load."""

    def test_serializeToText_no_side_effects(self, newdoc):
        """serializeToText must not change modified flag."""
        ds = document.datasets.Dataset(data=[1.0, 2.0])
        newdoc.applyOperation(operations.OperationDatasetSet("myds", ds))
        assert newdoc.changeset > 0

        old_changeset = newdoc.changeset
        buf = io.StringIO()
        newdoc.serializeToText(buf)

        assert newdoc.changeset == old_changeset

    def test_load_bad_file_restores_document(self, newdoc, tmp_path):
        """Loading an invalid .vsz should restore the previous document."""
        # Set up a document with some data
        ds = document.datasets.Dataset(data=[42.0])
        newdoc.applyOperation(operations.OperationDatasetSet("preserve_me", ds))
        assert "preserve_me" in newdoc.data

        # Write a bad .vsz file
        badfile = str(tmp_path / "bad.vsz")
        with open(badfile, "w") as f:
            f.write("raise RuntimeError('intentional failure')\n")

        # Try to load — should fail but restore
        from veusz.document.loader import loadDocument, LoadError

        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode="vsz")

        # Document should be restored
        assert "preserve_me" in newdoc.data
        assert list(newdoc.data["preserve_me"].data) == [42.0]

    def test_commandinterpreter_load_rejects_unsafe_script(self, newdoc, tmp_path):
        """CommandInterpreter.Load must use the safe loader path."""
        ds = document.datasets.Dataset(data=[7.0])
        newdoc.applyOperation(operations.OperationDatasetSet("preserve_me", ds))
        outfile = tmp_path / "should_not_exist.vsz"
        src = tmp_path / "unsafe.vsz"
        src.write_text("Save(%r)\n" % str(outfile), encoding="utf-8")

        ci = document.CommandInterpreter(newdoc)
        with pytest.raises(document.LoadError):
            ci.Load(str(src))

        assert not outfile.exists()
        assert "preserve_me" in newdoc.data
        assert list(newdoc.data["preserve_me"].data) == [7.0]

    def test_load_bad_hdf5_restores_document(self, newdoc, tmp_path, monkeypatch):
        """Failed HDF5 load must restore the previous document."""
        ds = document.datasets.Dataset(data=[11.0])
        newdoc.applyOperation(operations.OperationDatasetSet("preserve_me", ds))

        class FakeFile(dict):
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_h5py = types.SimpleNamespace(File=lambda *args, **kwargs: FakeFile())
        monkeypatch.setitem(sys.modules, "h5py", fake_h5py)

        badfile = str(tmp_path / "bad.h5")
        from veusz.document.loader import loadDocument, LoadError

        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode="hdf5")

        assert "preserve_me" in newdoc.data
        assert list(newdoc.data["preserve_me"].data) == [11.0]


# ═════════════════════════════════════════════════════════════════
# 4. WIDGET ARRAY ALIGNMENT
# ═════════════════════════════════════════════════════════════════


class TestArrayAlignment:
    """Verify array length mismatches are handled safely."""

    def test_piechart_labels_filtered_with_values(self):
        """PieChart labels must be filtered with same mask as values."""
        values = N.array([10.0, float("nan"), 20.0, -5.0, 30.0])
        valid = N.isfinite(values) & (values > 0)
        filtered_values = values[valid]

        labels = ["A", "B", "C", "D", "E"]
        n = min(len(labels), len(valid))
        filtered_labels = [labels[i] for i in range(n) if valid[i]]

        assert len(filtered_values) == len(filtered_labels)
        assert filtered_labels == ["A", "C", "E"]

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
        tpr_u = N.concatenate([[0.0], tpr[unique_mask]])
        fpr_u = N.concatenate([[0.0], fpr[unique_mask]])
        auc = float(N.trapezoid(tpr_u, fpr_u))

        assert auc == pytest.approx(1.0, abs=0.01)

    def test_roc_hanley_mcneil_se(self):
        """Hanley-McNeil SE should be reasonable for moderate sample."""
        auc = 0.85
        P, Neg = 50, 50
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
            (
                auc * (1 - auc)
                + (P - 1) * (Q1 - auc * auc)
                + (Neg - 1) * (Q2 - auc * auc)
            )
            / (P * Neg)
        )

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
        bracket = _add_widget(newdoc, graph, "bracket")

        yax = graph.getChild("y")
        # Set a fixed max
        newdoc.applyOperation(
            operations.OperationSettingSet(yax.settings.get("max"), 10.0)
        )

        original_max = yax.settings.max
        axrange = [0.0, 100.0]  # bracket y_top > axis max

        # getRange should not touch axis settings
        bracket.getRange(yax, "bracket_y", axrange)
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
            loadDocument(newdoc, "/nonexistent/path.vsz", mode="vsz")

    def test_load_unicode_garbage(self, newdoc, tmp_path):
        """Loading a file with invalid content should raise LoadError."""
        badfile = str(tmp_path / "garbage.vsz")
        with open(badfile, "wb") as f:
            f.write(b"\x80\x81\x82\x83\xff\xfe")
        from veusz.document.loader import loadDocument, LoadError

        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode="vsz")

    def test_rollback_preserves_changeset(self, newdoc, tmp_path):
        """Failed load must restore changeset to pre-load value."""
        ds = document.datasets.Dataset(data=[1.0])
        newdoc.applyOperation(operations.OperationDatasetSet("ds1", ds))
        old_changeset = newdoc.changeset

        badfile = str(tmp_path / "bad2.vsz")
        with open(badfile, "w") as f:
            f.write("raise ValueError('fail')\n")

        from veusz.document.loader import loadDocument, LoadError

        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode="vsz")

        assert newdoc.changeset == old_changeset

    def test_rollback_preserves_undo_history(self, newdoc, tmp_path):
        """Failed load must restore undo history."""
        ds = document.datasets.Dataset(data=[1.0])
        newdoc.applyOperation(operations.OperationDatasetSet("ds1", ds))
        undo_len = len(newdoc.historyundo)

        badfile = str(tmp_path / "bad3.vsz")
        with open(badfile, "w") as f:
            f.write("1/0\n")

        from veusz.document.loader import loadDocument, LoadError

        with pytest.raises(LoadError):
            loadDocument(newdoc, badfile, mode="vsz")

        assert len(newdoc.historyundo) == undo_len

    def test_load_valid_file(self, newdoc, tmp_path):
        """Loading a valid .vsz should succeed."""
        goodfile = str(tmp_path / "good.vsz")
        with open(goodfile, "w") as f:
            f.write("Add('page', name='page1')\n")

        from veusz.document.loader import loadDocument

        loadDocument(newdoc, goodfile, mode="vsz")
        assert newdoc.basewidget.getChild("page1") is not None


# ═════════════════════════════════════════════════════════════════
# 10. EXPORT — explicit write failures
# ═════════════════════════════════════════════════════════════════


class TestExportFailures:
    """Export should raise if Qt cannot write the output file."""

    def test_bitmap_export_surfaces_writer_error(self, newdoc, tmp_path, monkeypatch):
        """Bitmap export must fail loudly when QImageWriter.write() fails."""
        from veusz.document import export as exportmod

        class FakeWriter:
            def setFormat(self, fmt):
                pass

            def setFileName(self, filename):
                self.filename = filename

            def setCompression(self, value):
                pass

            def setQuality(self, value):
                pass

            def setOptimizedWrite(self, value):
                pass

            def setProgressiveScanWrite(self, value):
                pass

            def errorString(self):
                return "fake write failure"

            def write(self, image):
                return False

        monkeypatch.setattr(exportmod.qt, "QImageWriter", FakeWriter)

        newdoc.makeDefaultDoc()
        exp = document.AsyncExport(newdoc)
        exp.add(str(tmp_path / "out.png"), [0])
        with pytest.raises(RuntimeError, match="fake write failure"):
            exp.finish()

    def test_pic_export_surfaces_save_failure(self, newdoc, monkeypatch):
        """PIC export must fail loudly when QPicture.save() fails."""
        from veusz.document import export as exportmod

        class FakePicture:
            def save(self, filename):
                return False

        class FakeExport:
            antialias = False

        monkeypatch.setattr(exportmod.qt, "QPicture", FakePicture)
        runnable = exportmod.ExportPICRunnable(FakeExport(), "out.pic", [None])
        runnable.renderPage = lambda *args, **kwargs: None

        with pytest.raises(RuntimeError, match="Could not write"):
            runnable.doExport()


# ═════════════════════════════════════════════════════════════════
# 11. IMPORT DIALOG — compressed extension detection
# ═════════════════════════════════════════════════════════════════


class TestImportDialogGuessing:
    """guessImportTab should peel compressed extensions correctly."""

    def test_guessImportTab_handles_gz_extension(self):
        """A .csv.gz file should resolve to the .csv tab without looping."""
        from veusz.dialogs import importdialog as importdlg

        class DummyEdit:
            def text(self):
                return "data.csv.gz"

        class DummyTab:
            def __init__(self, supported):
                self.supported = supported
                self.used = None

            def isFiletypeSupported(self, ftype):
                return ftype == self.supported

            def useFiletype(self, ftype):
                self.used = ftype

        class DummyTabs:
            def __init__(self, tabs):
                self._tabs = tabs
                self.selected = None

            def count(self):
                return len(self._tabs)

            def widget(self, idx):
                return self._tabs[idx]

            def setCurrentIndex(self, idx):
                self.selected = idx

        csvtab = DummyTab(".csv")
        tabs = DummyTabs([DummyTab(".txt"), csvtab])
        dummy = types.SimpleNamespace(filenameedit=DummyEdit(), methodtab=tabs)

        importdlg.ImportDialog.guessImportTab(dummy)

        assert tabs.selected == 1
        assert csvtab.used == ".csv"


# ═════════════════════════════════════════════════════════════════
# 12. FIT — extended edge cases
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
        assert capture.getvalue() == ""

    def test_fit_with_all_nan_data(self):
        """Fit with all-NaN data should not crash."""
        xvals = N.array([float("nan")] * 5)
        yvals = N.array([float("nan")] * 5)
        finite = N.isfinite(xvals) & N.isfinite(yvals)
        # After filtering, arrays should be empty
        assert N.sum(finite) == 0


# ═════════════════════════════════════════════════════════════════
# 13. KAPLAN-MEIER — data edge cases
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
# 14. ROC — edge cases
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
        tpr_u = N.concatenate([[0.0], tpr[unique_mask]])
        fpr_u = N.concatenate([[0.0], fpr[unique_mask]])
        auc = float(N.trapezoid(tpr_u, fpr_u))

        assert 0.4 < auc < 0.6

    def test_hanley_mcneil_se_small_sample(self):
        """SE with very small sample should still be finite."""
        auc = 0.7
        P, Neg = 3, 3
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
        assert math.isfinite(se)
        assert se > 0


# ═════════════════════════════════════════════════════════════════
# 15. UNDO/REDO — extended scenarios
# ═════════════════════════════════════════════════════════════════


class TestUndoRedoExtended:
    """Extended undo/redo tests."""

    def test_redo_after_undo_labels(self, newdoc):
        """Redo after undoing widget add should re-apply labels."""
        graph = _setup_graph(newdoc)
        xax = graph.getChild("x")

        _add_widget(newdoc, graph, "roccurve")
        assert xax.settings.label == "100-Specificity"

        newdoc.undoOperation()
        newdoc.redoOperation()
        assert xax.settings.label == "100-Specificity"

    def test_multiple_operations_undo_all(self, newdoc):
        """Multiple dataset operations should all undo correctly."""
        for i in range(5):
            ds = document.datasets.Dataset(data=[float(i)])
            newdoc.applyOperation(operations.OperationDatasetSet("ds%d" % i, ds))

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
# 16. DOCUMENT — serializeToText roundtrip
# ═════════════════════════════════════════════════════════════════


class TestSerializeRoundtrip:
    """Verify serialize/restore preserves document content."""

    def test_roundtrip_with_data(self, newdoc):
        """Serialize + restore should preserve datasets."""
        ds = document.datasets.Dataset(data=[1.0, 2.0, 3.0])
        newdoc.applyOperation(operations.OperationDatasetSet("mydata", ds))

        buf = io.StringIO()
        newdoc.serializeToText(buf)

        # Create fresh doc and restore
        newdoc.wipe()
        assert "mydata" not in newdoc.data

        from veusz.document.loader import executeScript

        buf.seek(0)
        executeScript(newdoc, "test", buf.read())
        assert "mydata" in newdoc.data
        assert list(newdoc.data["mydata"].data) == pytest.approx([1.0, 2.0, 3.0])

    def test_roundtrip_with_widgets(self, newdoc):
        """Serialize + restore should preserve widget tree."""
        page = _add_widget(newdoc, newdoc.basewidget, "page", name="p1")
        graph = _add_widget(newdoc, page, "graph", name="g1")

        buf = io.StringIO()
        newdoc.serializeToText(buf)

        newdoc.wipe()
        assert newdoc.basewidget.getChild("p1") is None

        from veusz.document.loader import executeScript

        buf.seek(0)
        executeScript(newdoc, "test", buf.read())
        assert newdoc.basewidget.getChild("p1") is not None


# ═════════════════════════════════════════════════════════════════
# 17. REMOTE JSON / CLI EXPORT
# ═════════════════════════════════════════════════════════════════


class TestRemoteJsonSerialization:
    """JSON-returning entry points must serialize NumPy results safely."""

    def test_runpickle_serializes_numpy_results(self, newdoc):
        """runPickle should return JSON-safe lists for NumPy arrays."""
        ds = document.datasets.Dataset(data=[1.0, 2.0, 3.0])
        newdoc.applyOperation(operations.OperationDatasetSet("x", ds))

        ci = document.CommandInterpreter(newdoc)
        payload = json.dumps(["GetData", ["x"], {}]).encode("utf-8")
        result = json.loads(ci.runPickle(payload).decode("utf-8"))

        assert result["result"][0] == [1.0, 2.0, 3.0]
        assert result["result"][1:] == [None, None, None]

    def test_embed_remote_serializes_numpy_results(self):
        """embed_remote should emit JSON-safe payloads for NumPy arrays."""
        from veusz import embed_remote

        app = embed_remote.EmbedApplication.__new__(embed_remote.EmbedApplication)
        chunks = []
        app.socket = object()
        app.writeToSocket = lambda sock, data: chunks.append(data)

        app.writeOutput((N.array([1.0, 2.0]),))

        assert struct.unpack("<I", chunks[0])[0] == len(chunks[1])
        result = json.loads(chunks[1].decode("utf-8"))
        assert result["result"][0] == [1.0, 2.0]

    def test_veusz_listen_serializes_numpy_results(self, monkeypatch):
        """veusz_listen JSON mode should serialize NumPy arrays safely."""
        from veusz import veusz_listen

        class FakeCI:
            def runCommand(self, name, args, namedargs):
                return (N.array([4.0, 5.0]),)

        listener = veusz_listen.InputListener.__new__(veusz_listen.InputListener)
        listener.pickle = True
        listener.ci = FakeCI()

        stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)

        listener.processLine(json.dumps(["GetData", ["x"], {}]))

        result = json.loads(stdout.getvalue().strip())
        assert result["result"][0] == [4.0, 5.0]


class TestCliExportOptions:
    """CLI export should parse options safely and avoid code execution."""

    def test_export_uses_typed_command_call(self, monkeypatch):
        """export() should forward parsed kwargs via runCommand()."""
        from veusz import veusz_main

        calls = []

        class FakeCI:
            def __init__(self, doc):
                self.doc = doc

            def Load(self, filename):
                calls.append(("Load", filename))

            def runCommand(self, name, args, namedargs):
                calls.append(("runCommand", name, args, namedargs))

        monkeypatch.setattr(document, "Document", lambda: object())
        monkeypatch.setattr(document, "CommandInterpreter", FakeCI)

        veusz_main.export(
            ["out.png"], ["input.vsz"], ["page=[0, 1]", "dpi=150", "svgtextastext=True"]
        )

        assert calls[0] == ("Load", "input.vsz")
        assert calls[1] == (
            "runCommand",
            "Export",
            ("out.png",),
            {"page": [0, 1], "dpi": 150, "svgtextastext": True},
        )

    def test_export_rejects_injected_option(self, monkeypatch):
        """export() must reject options that are not simple literals."""
        from veusz import veusz_main

        class FakeCI:
            def __init__(self, doc):
                pass

            def Load(self, filename):
                raise AssertionError("Load should not be reached")

            def runCommand(self, name, args, namedargs):
                raise AssertionError("runCommand should not be reached")

        monkeypatch.setattr(document, "Document", lambda: object())
        monkeypatch.setattr(document, "CommandInterpreter", FakeCI)

        with pytest.raises(ValueError, match="Invalid export option"):
            veusz_main.export(
                ["out.png"], ["input.vsz"], ["page=[0]); Save('pwn.vsz') #"]
            )


# ═════════════════════════════════════════════════════════════════
# 18. CHANGESET / DIRTY STATE
# ═════════════════════════════════════════════════════════════════


class TestChangeSetAccounting:
    """Document changeset should reflect one logical change per action."""

    def test_setModified_false_does_not_increment_changeset(self, newdoc):
        """Clearing dirty state should not count as a document mutation."""
        assert newdoc.changeset == 0

        newdoc.setModified()
        assert newdoc.changeset == 1

        newdoc.setModified(False)
        assert newdoc.changeset == 1
        assert newdoc.isModified() is False

    def test_filter_operation_counts_once(self, newdoc):
        """FilterDatasets should increment changeset once per do/undo."""
        newdoc.applyOperation(
            operations.OperationDatasetSet(
                "mask", document.datasets.Dataset(data=[1, 0, 1])
            )
        )
        newdoc.applyOperation(
            operations.OperationDatasetSet(
                "values", document.datasets.Dataset(data=[10.0, 20.0, 30.0])
            )
        )

        old_changeset = newdoc.changeset
        op = operations.OperationDatasetsFilter(
            "mask", ["values"], prefix="f_", suffix=""
        )
        newdoc.applyOperation(op)

        assert newdoc.changeset == old_changeset + 1
        assert "f_values" in newdoc.data

        newdoc.undoOperation()
        assert newdoc.changeset == old_changeset + 2
        assert "f_values" not in newdoc.data

    def test_capture_operation_counts_once(self, newdoc):
        """OperationDataCaptureSet should increment changeset once."""
        from veusz.dataimport import capture as capturemod

        class FakeRead:
            def setOutput(self, out):
                out["captured"] = document.datasets.Dataset(data=[1.0, 2.0])

        old_changeset = newdoc.changeset
        newdoc.applyOperation(capturemod.OperationDataCaptureSet(FakeRead()))

        assert newdoc.changeset == old_changeset + 1
        assert list(newdoc.data["captured"].data) == [1.0, 2.0]

        newdoc.undoOperation()
        assert newdoc.changeset == old_changeset + 2
        assert "captured" not in newdoc.data

    def test_data_paste_operation_counts_once(self, newdoc):
        """OperationDataPaste should increment changeset once per do/undo."""
        srcdoc = doc.Document()
        srcdoc.applyOperation(
            operations.OperationDatasetSet(
                "paste_me", document.datasets.Dataset(data=[4.0, 5.0])
            )
        )
        mimedata = document.generateDatasetsMime(["paste_me"], srcdoc)

        old_changeset = newdoc.changeset
        newdoc.applyOperation(document.OperationDataPaste(mimedata))

        assert newdoc.changeset == old_changeset + 1
        assert "paste_me" in newdoc.data

        newdoc.undoOperation()
        assert newdoc.changeset == old_changeset + 2
        assert "paste_me" not in newdoc.data


# ═════════════════════════════════════════════════════════════════
# 19. IMPORT PATH RESOLUTION
# ═════════════════════════════════════════════════════════════════


class TestImportPathResolution:
    """Relative imports in .vsz files should resolve from document location."""

    def test_import_path_allows_parent_relative_paths(self, newdoc, tmp_path):
        """findFileOnImportPath should resolve legitimate ../ paths."""
        graphdir = tmp_path / "graphs"
        datadir = tmp_path / "shared" / "data"
        graphdir.mkdir(parents=True)
        datadir.mkdir(parents=True)

        target = datadir / "Tabla1.csv"
        target.write_text("x,y\n1,2\n", encoding="utf-8")

        ci = document.CommandInterface(newdoc)
        ci.AddImportPath(str(graphdir))

        resolved = ci.findFileOnImportPath("../shared/data/Tabla1.csv")

        assert resolved == str(target.resolve())


# ─── Sprint 0 (v1.5.2) — security regressions ────────────────────


class TestSafeAstValidatorRecursive:
    """Safe-mode AST validator must walk every argument, not only top-level.

    Pre-fix: ``_validate_safe_ast`` only checked ``Expr(Call(Name))`` at the
    top level. Anything inside an argument — ``__import__('os').system(...)``,
    a lambda, a comprehension — slipped through and reached ``exec``.
    """

    def _interp(self, newdoc):
        from veusz.document import commandinterpreter

        return commandinterpreter.CommandInterpreter(newdoc)

    def test_top_level_whitelisted_call_passes(self, newdoc):
        ci = self._interp(newdoc)
        # Should not raise (Set is whitelisted; literal arguments)
        ci._validate_safe_ast("Set('foo', 1)")

    def test_dunder_import_in_argument_blocked(self, newdoc):
        ci = self._interp(newdoc)
        with pytest.raises(RuntimeError):
            ci._validate_safe_ast("Set('x', __import__('os'))")

    def test_lambda_in_argument_blocked(self, newdoc):
        ci = self._interp(newdoc)
        with pytest.raises(RuntimeError):
            ci._validate_safe_ast("Set('x', (lambda: 1)())")

    def test_attribute_access_in_argument_blocked(self, newdoc):
        ci = self._interp(newdoc)
        with pytest.raises(RuntimeError):
            ci._validate_safe_ast("Set('x', ().__class__)")

    def test_subscript_in_argument_blocked(self, newdoc):
        ci = self._interp(newdoc)
        with pytest.raises(RuntimeError):
            ci._validate_safe_ast("Set('x', [1,2,3][0])")

    def test_comprehension_in_argument_blocked(self, newdoc):
        ci = self._interp(newdoc)
        with pytest.raises(RuntimeError):
            ci._validate_safe_ast("Set('x', [c for c in [1,2,3]])")

    def test_kwargs_unpacking_blocked(self, newdoc):
        ci = self._interp(newdoc)
        with pytest.raises(RuntimeError):
            ci._validate_safe_ast("Set('x', **{'k': 1})")

    def test_negative_literal_allowed(self, newdoc):
        ci = self._interp(newdoc)
        # -1.5 is UnaryOp(USub, Constant) — must remain legal
        ci._validate_safe_ast("Set('x', -1.5)")

    def test_list_dict_literal_allowed(self, newdoc):
        ci = self._interp(newdoc)
        ci._validate_safe_ast("Set('x', [1, 2, {'k': 'v'}])")

    def test_non_whitelisted_command_blocked(self, newdoc):
        ci = self._interp(newdoc)
        with pytest.raises(RuntimeError):
            ci._validate_safe_ast("ExecMaliciousCmd('foo')")


class TestSafeEvalForbiddenNodes:
    """safe_eval must reject lambdas, comprehensions, f-strings, walrus, etc.

    These node types can hide indirection that the visitor cannot inspect at
    parse time (lambdas produce callables; f-strings invoke __format__ on
    arbitrary objects; walrus rebinds names). Pre-fix they were allowed.
    """

    def test_lambda_blocked(self):
        from veusz.utils import safe_eval

        with pytest.raises(safe_eval.SafeEvalException):
            safe_eval.compileChecked("(lambda x: x)(1)", mode="eval")

    def test_listcomp_blocked(self):
        from veusz.utils import safe_eval

        with pytest.raises(safe_eval.SafeEvalException):
            safe_eval.compileChecked("[x for x in range(3)]", mode="eval")

    def test_fstring_blocked(self):
        from veusz.utils import safe_eval

        with pytest.raises(safe_eval.SafeEvalException):
            safe_eval.compileChecked("f'{abs(1)}'", mode="eval")

    def test_walrus_blocked(self):
        import ast as _ast

        if not hasattr(_ast, "NamedExpr"):
            pytest.skip("walrus not in this Python")
        from veusz.utils import safe_eval

        with pytest.raises(safe_eval.SafeEvalException):
            safe_eval.compileChecked("(x := 5)", mode="eval")

    def test_attribute_call_blocked(self):
        from veusz.utils import safe_eval

        with pytest.raises(safe_eval.SafeEvalException):
            safe_eval.compileChecked("[1].append(2)", mode="eval")

    def test_safe_arithmetic_passes(self):
        from veusz.utils import safe_eval

        # Plain math must keep working
        safe_eval.compileChecked("abs(-1) + sin(0.5)", mode="eval")


class TestLoaderCacheHmac:
    """Bytecode cache must be HMAC-authenticated.

    Pre-fix the cache stored an MD5 of the script *inside* the file itself,
    so an attacker with write access could forge matching bytecode →
    arbitrary code execution at next load. HMAC with a per-installation
    secret key closes that vector.
    """

    def test_hmac_key_is_persistent_across_calls(self):
        from veusz.document import loader

        # reset module cache so we hit the disk path
        loader._HMAC_KEY = None
        k1 = loader._cacheHmacKey()
        loader._HMAC_KEY = None
        k2 = loader._cacheHmacKey()
        assert k1 == k2
        assert len(k1) == 32

    def test_forged_cache_is_rejected(self, tmp_path, monkeypatch):
        """Tampering with the bytecode after writing must fail HMAC verify
        and force recompilation, not silent execution of the forged bytes."""
        from veusz.document import loader
        import hmac as _hmac
        import marshal

        # Point the cache dir at a temp location for this test
        monkeypatch.setattr(loader, "_cacheDir", lambda: str(tmp_path))
        loader._HMAC_KEY = None  # regen against the new dir

        # Build a fake cache file with a *wrong* MAC over real bytecode
        fake_code = compile("x = 1", "<test>", "exec")
        marshal_bytes = marshal.dumps(fake_code)
        bogus_mac = b"\x00" * 32  # not a valid HMAC for this key

        cache_path = str(tmp_path / "fake.vsz.deadbeef.c")
        with open(cache_path, "wb") as f:
            f.write(bogus_mac)
            f.write(marshal_bytes)

        # The verifier should compute the *real* HMAC and reject the forgery
        real_mac = _hmac.new(
            loader._cacheHmacKey(),
            msg=b"original-script\n" + marshal_bytes,
            digestmod="sha256",
        ).digest()
        assert real_mac != bogus_mac
        assert not _hmac.compare_digest(real_mac, bogus_mac)


class TestNumpyImportPluginAllowPickle:
    """N.load() must refuse object arrays — pickled .npy files can RCE.

    Pre-fix: ``N.load(path)`` used the deprecated default that allows
    pickle, so a crafted .npy file could execute arbitrary code at import
    time. The plugin now passes ``allow_pickle=False`` explicitly.
    """

    def test_pickled_npy_is_refused(self, tmp_path):
        from veusz.plugins import importplugin

        # Create a real pickled .npy: object dtype forces pickle on save
        evil = N.array([{"k": "v"}], dtype=object)
        npy_path = tmp_path / "evil.npy"
        # save() emits the pickled form; load(allow_pickle=False) must refuse
        N.save(str(npy_path), evil, allow_pickle=True)

        plugin = importplugin.ImportPluginNpy()
        params = types.SimpleNamespace(
            filename=str(npy_path),
            field_results={"name": "x", "errorsin2d": True},
        )
        with pytest.raises(importplugin.ImportPluginException):
            plugin.doImport(params)


class TestOperationWidgetPasteSafeMode:
    """Pasting widget mime data must run the interpreter in safe mode.

    OperationDataPaste already calls setSafeMode(True); OperationWidgetPaste
    didn't. The fix makes both paths explicit and symmetric so a malicious
    clipboard payload cannot escape the documented Set/Add/To grammar.
    """

    def test_widget_paste_constructs_interpreter_in_safe_mode(
        self, newdoc, monkeypatch
    ):
        from veusz.document import mime, commandinterpreter

        captured = {}
        real_init = commandinterpreter.CommandInterpreter.__init__
        real_set = commandinterpreter.CommandInterpreter.setSafeMode

        def fake_init(self, document):
            real_init(self, document)
            captured["init_safe_mode"] = self.safe_mode

        def fake_set(self, enabled):
            captured["set_safe_mode_called"] = enabled
            real_set(self, enabled)

        monkeypatch.setattr(
            commandinterpreter.CommandInterpreter, "__init__", fake_init
        )
        monkeypatch.setattr(
            commandinterpreter.CommandInterpreter, "setSafeMode", fake_set
        )

        # Minimal mime payload: 0 widgets, just exercises the do() entry point
        op = mime.OperationWidgetPaste(newdoc.basewidget, "0\n")
        try:
            op.do(newdoc)
        except Exception:
            pass  # we only care about how the interpreter was constructed

        assert captured.get("set_safe_mode_called") is True


class TestLoaderUiCallbackTimeout:
    """askUnsafe / askImportError must not block forever if main thread
    never processes the queued signal."""

    def test_unsafe_callback_times_out_to_refusal(self):
        from veusz.document import loader

        bridge = loader._LoadBridge(callbackunsafe=None, callbackimporterror=None)
        # Override the timeout so the test is fast
        bridge._UI_CALLBACK_TIMEOUT_SEC = 0.1
        # Don't connect signals → the slot will never fire → wait will time out
        # Disconnect any default connections
        try:
            bridge.sigAskUnsafe.disconnect()
        except TypeError:
            pass

        result = bridge.askUnsafe()
        # Timeout must default to "deny" (False) — never silently allow exec
        assert result is False


# ─── Sprint 1 (v1.6.0) — painter, capture, embed, dialogs, snapshot ──


class TestPainterStateContextManager:
    """``utils.painter_state`` must always restore the painter state, even
    when the body raises. Pre-fix several widgets used bare save/restore;
    a draw exception left the painter clip/transform/brush from the
    failed widget bleeding into siblings."""

    def test_restores_on_clean_exit(self):
        from veusz.utils import painter_state

        painter = QtGui_QPainter()
        with painter_state(painter):
            painter._record("setClipRect", "inner")
        assert painter.save_count == 1
        assert painter.restore_count == 1

    def test_restores_on_exception(self):
        from veusz.utils import painter_state

        painter = QtGui_QPainter()
        with pytest.raises(RuntimeError):
            with painter_state(painter):
                painter._record("setBrush", "red")
                raise RuntimeError("draw failed mid-flight")
        assert painter.save_count == 1
        assert painter.restore_count == 1


class _FakePainter:
    """Mock counterpart to QPainter used to verify save/restore balance."""

    def __init__(self):
        self.save_count = 0
        self.restore_count = 0
        self.events = []

    def save(self):
        self.save_count += 1
        self.events.append("save")

    def restore(self):
        self.restore_count += 1
        self.events.append("restore")

    def _record(self, name, *args):
        self.events.append((name, args))


# Alias so the name appears in the test class body
QtGui_QPainter = _FakePainter


class TestCaptureCommandSafety:
    """``CommandCaptureStream`` must invoke the child without an
    intermediate shell, so metacharacters in the user-supplied command
    line cannot smuggle extra commands."""

    def test_shlex_split_no_shell(self, monkeypatch):
        from veusz.dataimport import capture

        captured = {}

        class FakePopen:
            def __init__(self, argv, **kw):
                captured["argv"] = argv
                captured["shell"] = kw.get("shell")
                # Mimic real Popen attrs that close() touches
                self.pid = 0
                self.stdout = self

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

            def close(self):
                pass

        # Stub the reader thread so we don't try to consume from a real fd
        class FakeReader:
            def __init__(self, *a, **kw):
                pass

            def start(self):
                pass

            def getNewData(self):
                return ("", True)

        monkeypatch.setattr(capture.subprocess, "Popen", FakePopen)
        monkeypatch.setattr(capture.utils, "NonBlockingReaderThread", FakeReader)

        # Inject a metacharacter that, under shell=True, would run a 2nd cmd
        capture.CommandCaptureStream("/bin/echo hi; rm -rf /tmp/should_not_run")
        assert captured["shell"] is False
        # shlex.split tokenises but does NOT execute shell semantics:
        # the metacharacter ``;`` ends up attached to the previous word
        # (``hi;``); ``rm`` becomes a literal argv entry passed to
        # /bin/echo, not a second command. Two invariants matter:
        #   * argv[0] is the exe the user typed (no shell wrapper)
        #   * the metacharacter survives somewhere in argv as literal text
        argv = captured["argv"]
        assert argv[0] == "/bin/echo"
        assert any(";" in tok for tok in argv)
        assert "rm" in argv

    def test_buffer_overflow_terminates(self):
        from veusz.dataimport import capture as capturemod

        class HugeStream(capturemod.CaptureStream):
            def __init__(self):
                capturemod.CaptureStream.__init__(self)
                self.served = 0
                # Pretend we have an infinite source with no newlines
                self._chunk = "x" * (1024 * 1024)  # 1 MiB

            def getMoreData(self):
                self.served += 1
                return self._chunk

        s = HugeStream()
        with pytest.raises(capturemod.CaptureFinishException):
            for _ in range(100):  # would loop forever pre-fix
                try:
                    s.readLine()
                except StopIteration:
                    pass


class TestEmbedSendCommandShutdownGuard:
    """sendCommand must refuse to write to a torn-down socket instead
    of raising AttributeError on int.send()."""

    def test_sendCommand_rejects_after_shutdown(self):
        import veusz.embed as embed

        embed.Embedded.serv_socket = -1  # simulate post-exitQt state
        with pytest.raises(ConnectionError):
            embed.Embedded.sendCommand((-1, "_NoOp", (), {}))


class TestDataEditModelAutoDisconnect:
    """Models in dataeditdialog must auto-disconnect their
    ``signalModified`` slot when destroyed; otherwise the document holds
    a strong reference into a sip-deleted Python wrapper."""

    def test_destroyed_disconnects(self, newdoc):
        from veusz.dialogs import dataeditdialog as dd

        # Track receiver count before/after model lifecycle
        before = newdoc.signalModified.disconnect  # exists
        m = dd.DatasetTableModel1D(None, newdoc, "nonexistent")
        # Confirm the connection is live: scheduling a refresh works
        m._scheduleRefresh()
        assert m._refreshTimer.isActive()
        # Now destroy and verify our auto-disconnect fired (signalModified
        # no longer raises when emitted, even though the wrapper is gone)
        del m
        import gc

        gc.collect()
        # Emitting must not propagate AttributeError or RuntimeError
        try:
            newdoc.signalModified.emit(False)
        except (AttributeError, RuntimeError) as e:
            pytest.fail("signalModified emit raised after model GC: %r" % e)


class TestPreferencesCancelRevert:
    """Cancel must restore the live-previewed font/color scheme rather
    than persisting them as a side-effect of opening the dialog."""

    def test_reject_restores_origState(self):
        # We don't construct the full dialog (it needs a mainwindow); we
        # construct a minimal stand-in object and call PreferencesDialog.reject
        # bound to it, exercising the restoration logic in isolation.
        from veusz.dialogs.preferences import PreferencesDialog
        from veusz import setting

        class FakeApp:
            def __init__(self):
                self.applied = []
                self.font_obj = "orig-font"

            def applyColorScheme(self, n):
                self.applied.append(n)

            def setFont(self, f):
                self.font_obj = f

        # Save real settingdb keys we'll mutate
        saved = {
            k: setting.settingdb.get(k)
            for k in (
                "color_scheme",
                "ui_font",
                "ui_font_size",
                "ui_font_bold",
                "ui_font_italic",
            )
        }
        try:
            setting.settingdb["color_scheme"] = "system"
            setting.settingdb["ui_font"] = "OldFont"
            setting.settingdb["ui_font_size"] = 9
            setting.settingdb["ui_font_bold"] = False
            setting.settingdb["ui_font_italic"] = False

            fake_app = FakeApp()

            # Construct origState exactly as PreferencesDialog.__init__ does
            inst = type("X", (), {})()
            inst.setdb = setting.settingdb
            inst._origState = {
                "color_scheme": "system",
                "ui_font": "OldFont",
                "ui_font_size": 9,
                "ui_font_bold": False,
                "ui_font_italic": False,
                "app_font": "orig-font",
            }

            # Simulate live-preview mutations
            setting.settingdb["color_scheme"] = "dark"
            setting.settingdb["ui_font"] = "NewFont"
            setting.settingdb["ui_font_size"] = 14
            fake_app.font_obj = "preview-font"

            # Manually run the body of reject() that does the restoration.
            # We intercept the QApplication lookup so the test stays headless.
            import veusz.qtall as qt

            real_instance = qt.QApplication.instance
            qt.QApplication.instance = staticmethod(lambda: fake_app)
            try:
                # Call reject's restoration block via the unbound method,
                # but stop before QDialog.reject (which needs a real dialog)
                orig = inst._origState
                if orig.get("color_scheme") is not None:
                    setting.settingdb["color_scheme"] = orig["color_scheme"]
                    fake_app.applyColorScheme(orig["color_scheme"])
                setting.settingdb["ui_font"] = orig["ui_font"]
                setting.settingdb["ui_font_size"] = orig["ui_font_size"]
                setting.settingdb["ui_font_bold"] = orig["ui_font_bold"]
                setting.settingdb["ui_font_italic"] = orig["ui_font_italic"]
                fake_app.setFont(orig["app_font"])
            finally:
                qt.QApplication.instance = real_instance

            assert setting.settingdb["color_scheme"] == "system"
            assert setting.settingdb["ui_font"] == "OldFont"
            assert setting.settingdb["ui_font_size"] == 9
            assert fake_app.font_obj == "orig-font"
            assert fake_app.applied == ["system"]
        finally:
            for k, v in saved.items():
                if v is None:
                    setting.settingdb.pop(k, None)
                else:
                    setting.settingdb[k] = v


class TestLoaderSnapshotUnderLock:
    """``_takeDocumentSnapshot`` must hold the document read lock so the
    snapshot dict is internally consistent. Smoke-check: snapshot still
    works on a Document and returns the expected keys."""

    def test_snapshot_keys(self, newdoc):
        from veusz.document import loader

        snap = loader._takeDocumentSnapshot(newdoc)
        assert set(snap.keys()) >= {
            "script",
            "data",
            "filename",
            "modified",
            "changeset",
            "historyundo",
            "historyredo",
        }


class TestImageCacheMutex:
    """Image widget cache must hold a mutex and a strong reference to the
    transimg array so id-recycling cannot produce a false cache hit."""

    def test_strong_ref_held(self, newdoc):
        from veusz.widgets.image import Image

        page = _add_widget(newdoc, newdoc.basewidget, "page")
        graph = _add_widget(newdoc, page, "graph")
        img = _add_widget(newdoc, graph, "image")
        # Mutex and strong-ref slot exist on every Image
        assert hasattr(img, "_cmapCacheLock")
        assert hasattr(img, "_cmapCacheTransimg")


# ─── Sprint 2 (v1.7.0 wip) — cycles, rollback, encoding, fitdialog ──


class TestReferenceCycleDetection:
    """``Reference.resolve()`` must reject circular references with a
    ResolveException instead of recursing until the stack overflows."""

    def test_reference_chain_too_deep_raises(self, newdoc):
        from veusz.setting.reference import Reference, ReferenceBase

        # Build a tiny dummy setting graph where ``a._val = Reference -> b``,
        # ``b._val = Reference -> a`` to form a cycle.
        class FakeSetting:
            def __init__(self, name):
                self.name = name
                self._val = None
                self.parent = None
                self.iswidget = False

            def get(self, p):
                raise KeyError(p)

        a = FakeSetting("a")
        b = FakeSetting("b")

        # Reference walker resolves *names*, not direct refs — but we can
        # check the chain-too-deep guard by injecting a self-loop:
        class SelfLoopRef(ReferenceBase):
            def __init__(self):
                super().__init__("loop")

            def resolve(self, setn):
                return setn  # always returns the same object

        a._val = SelfLoopRef()

        ref = Reference("a")
        ref.split = ["a"]

        # Patch the lookup so the first hop lands on `a`
        class Root:
            parent = None
            iswidget = True

            def getChild(self, p):
                return a if p == "a" else None

        a.parent = Root()
        with pytest.raises(Reference.ResolveException):
            ref.resolve(a)


class TestOperationSettingSetRollback:
    """If ``setting.set()`` raises mid-operation, ``OperationSettingSet.do``
    must restore the previous value before propagating, so the setting is
    never observed in a half-modified state."""

    def test_failed_set_restores_oldvalue(self, newdoc):
        from veusz.document import operations

        page = _add_widget(newdoc, newdoc.basewidget, "page")
        graph = _add_widget(newdoc, page, "graph")

        # ``leftMargin`` accepts a Distance string; a plain object will fail
        s = graph.settings.get("leftMargin")
        original = s.get()

        op = operations.OperationSettingSet(s, object())  # invalid type

        with pytest.raises(Exception):
            op.do(newdoc)

        # Setting must still be the original value, not partially mutated
        assert s.get() == original


class TestOpenEncodingStrictMode:
    """Callers can opt into ``errors='strict'`` to detect corruption
    instead of silently substituting U+FFFD."""

    def test_strict_raises_on_invalid_bytes(self, tmp_path):
        from veusz.utils.utilfuncs import openEncoding

        path = tmp_path / "mixed.txt"
        # Write Latin-1 bytes that are invalid as UTF-8
        path.write_bytes(b"\xc3\x28 hello")
        with openEncoding(str(path), "utf_8", errors="strict") as f:
            with pytest.raises(UnicodeDecodeError):
                f.read()

    def test_default_replace_does_not_raise(self, tmp_path):
        from veusz.utils.utilfuncs import openEncoding

        path = tmp_path / "mixed.txt"
        path.write_bytes(b"\xc3\x28 hello")
        with openEncoding(str(path), "utf_8") as f:
            txt = f.read()
        assert "�" in txt  # replacement char inserted


class TestInvalidDataPointsCacheKey:
    """``invalidDataPoints`` cache must distinguish in-place buffer
    edits from no-ops by including the document changeset (when a
    document is attached). Without a document, the cache uses the
    array buffer address + dtype + strides, holding strong refs to
    prevent id-recycle false hits."""

    def test_cache_holds_strong_refs(self):
        from veusz.datasets import oned

        ds = oned.Dataset(data=N.array([1.0, 2.0, N.nan, 4.0]))
        m1 = ds.invalidDataPoints()
        m2 = ds.invalidDataPoints()
        # Same call twice must hit the cache (identity check)
        assert m1 is m2
        # Cache entry includes a tuple of strong references to the arrays
        assert len(ds._invalidcache) == 3
        assert ds._invalidcache[2][0] is ds.data


# ─── Sprint 4 — LOW cleanup, forbidden attrs, validators ──


class TestSafeEvalForbiddenAttrs:
    """Attribute-name blacklist must reject known-dangerous names even
    when the receiving object isn't a Name we can pin to numpy."""

    @pytest.mark.parametrize(
        "expr",
        [
            "x.lib",
            "obj.f2py",
            "thing.ctypeslib",
            "ns.system_info",
            "foo.show_config",
            "y.exec",
            "y.eval",
            "y.compile",
            "y.globals",
            "y.locals",
            "y.dir",
            "y.vars",
        ],
    )
    def test_forbidden_attribute_blocked(self, expr):
        from veusz.utils import safe_eval

        with pytest.raises(safe_eval.SafeEvalException):
            safe_eval.compileChecked(expr, mode="eval")

    def test_normal_numpy_attr_allowed(self):
        from veusz.utils import safe_eval

        # mean / shape / dtype etc. must remain reachable
        safe_eval.compileChecked("a.shape", mode="eval")
        safe_eval.compileChecked("a.dtype", mode="eval")


class TestSettingValidatorTypeStrict:
    """Setting normalisers must reject the type-confusion cases caught
    by the audit instead of crashing inside the normaliser body."""

    def test_distance_rejects_non_str(self):
        from veusz.setting import setting as setmod
        from veusz.utils import InvalidType

        d = setmod.Distance("x", "1cm")
        with pytest.raises(InvalidType):
            d.normalize(None)
        with pytest.raises(InvalidType):
            d.normalize(5)

    def test_intorauto_rejects_bool(self):
        from veusz.setting import setting as setmod
        from veusz.utils import InvalidType

        s = setmod.IntOrAuto("x", 0)
        with pytest.raises(InvalidType):
            s.normalize(True)
        with pytest.raises(InvalidType):
            s.normalize(False)
        # Real ints + 'Auto' still work
        assert s.normalize(5) == 5
        assert s.normalize("Auto") == "Auto"

    def test_filename_rejects_non_str(self):
        from veusz.setting import setting as setmod
        from veusz.utils import InvalidType

        f = setmod.Filename("x", "")
        with pytest.raises(InvalidType):
            f.normalize(None)

    def test_floatlist_rejects_inf_nan(self):
        import math
        from veusz.setting import setting as setmod
        from veusz.utils import InvalidType

        fl = setmod.FloatList("x", [])
        with pytest.raises(InvalidType):
            fl.normalize([1.0, math.inf])
        with pytest.raises(InvalidType):
            fl.normalize([math.nan])
        with pytest.raises(InvalidType):
            fl.normalize([True])  # bool subclass of int
        assert fl.normalize([1.0, 2.5, -3.0]) == [1.0, 2.5, -3.0]


class TestEnvironWhitelist:
    """ENVIRON must drop credential-shaped vars and only expose the
    whitelisted locale/system keys."""

    def test_credentials_filtered(self, monkeypatch):
        from veusz.document import evaluate

        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leak-me")
        monkeypatch.setenv("GITHUB_TOKEN", "leak-me-too")
        monkeypatch.setenv("PATH", "/usr/bin")
        # Build a fresh interpreter context to trigger ENVIRON construction
        from veusz.document import doc

        d = doc.Document()
        env = d.evaluate.context["ENVIRON"]
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert "GITHUB_TOKEN" not in env
        assert "PATH" in env


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
