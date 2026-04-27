# data editing dialog
#
#    Copyright (C) 2005 Jeremy S. Sanders
#    Copyright (C) 2026 M. Ignacio Monge García (modernized editor)
#
#    This file is part of Veusz / Plotex.
#
#    Veusz is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
##############################################################################

"""Data editing dialog with spreadsheet-like editing, paste from
clipboard, validation feedback, and readonly visual indicators."""

import numpy as N

from .. import qtall as qt
from .. import document
from .. import datasets
from .. import setting
from .. import utils
from ..qtwidgets.datasetbrowser import DatasetBrowser
from .veuszdialog import VeuszDialog, recreate_register


def _(text, disambiguation=None, context="DataEditDialog"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


# ── Table Models ─────────────────────────────────────────────────

_readonly_bg = qt.QBrush(qt.QColor(235, 235, 235))


def _autoDisconnectOnDestroyed(qobject, signal, slot):
    """Disconnect ``signal`` from ``slot`` when ``qobject`` is destroyed.

    Table models created here connect to ``document.signalModified`` and
    are then replaced (or the dialog is closed) without explicit
    disconnects. The Document keeps a strong reference to the bound
    method, so when the model's C++ side is deleted Qt eventually fires
    ``signalModified`` into a sip-deleted wrapper → AttributeError or
    RuntimeError per emission. This helper registers a one-shot
    disconnect on the model's ``destroyed`` signal so the connection is
    cleaned up automatically. Lambda is safe here: it does not capture
    the qobject (only the signal+slot), so it cannot keep the model
    alive.
    """

    def _do(*_):
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            # Already disconnected / wrong signal arity — ignore.
            pass

    qobject.destroyed.connect(_do)


class DatasetTableModel1D(qt.QAbstractTableModel):
    """Model for a single 1D dataset."""

    def __init__(self, parent, document, datasetname):
        qt.QAbstractTableModel.__init__(self, parent)
        self.document = document
        self.dsname = datasetname
        self._refreshTimer = qt.QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(50)
        self._refreshTimer.timeout.connect(self._doRefresh)
        document.signalModified.connect(self._scheduleRefresh)
        _autoDisconnectOnDestroyed(self, document.signalModified, self._scheduleRefresh)

    def _scheduleRefresh(self):
        if not self._refreshTimer.isActive():
            self._refreshTimer.start()

    def _doRefresh(self):
        self.layoutChanged.emit()

    def rowCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        try:
            ds = self.document.data[self.dsname]
            return len(ds.data) + (1 if ds.editable else 0)
        except (KeyError, AttributeError):
            return 0

    def columnCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        try:
            return len(self.document.data[self.dsname].column_descriptions)
        except KeyError:
            return 0

    def data(self, index, role):
        try:
            ds = self.document.data[self.dsname]
        except KeyError:
            return None

        col_data = getattr(ds, ds.columns[index.column()])

        if role in (qt.Qt.ItemDataRole.DisplayRole, qt.Qt.ItemDataRole.EditRole):
            if col_data is None or index.row() >= len(ds.data):
                return None
            return ds.uiDataItemToData(col_data[index.row()])

        if role == qt.Qt.ItemDataRole.BackgroundRole:
            if not ds.editable:
                return _readonly_bg

        return None

    def headerData(self, section, orientation, role):
        try:
            ds = self.document.data[self.dsname]
        except KeyError:
            return None

        if role == qt.Qt.ItemDataRole.DisplayRole:
            if orientation == qt.Qt.Orientation.Horizontal:
                return ds.column_descriptions[section]
            else:
                if ds.editable and section == len(ds.data):
                    return "\u2795"
                return section + 1
        return None

    def flags(self, index):
        if not index.isValid():
            return qt.Qt.ItemFlag.ItemIsEnabled
        f = qt.QAbstractTableModel.flags(self, index)
        ds = self.document.data.get(self.dsname)
        if ds is not None and ds.editable:
            f |= qt.Qt.ItemFlag.ItemIsEditable
        return f

    def removeRows(self, row, count):
        self.document.applyOperation(
            document.OperationDatasetDeleteRow(self.dsname, row, count)
        )

    def insertRows(self, row, count):
        self.document.applyOperation(
            document.OperationDatasetInsertRow(self.dsname, row, count)
        )

    def setData(self, index, value, role):
        if not index.isValid() or role != qt.Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        column = index.column()
        ds = self.document.data[self.dsname]
        col_data = getattr(ds, ds.columns[column])

        ops = document.OperationMultiple([], descr=_("set value"))
        if col_data is None:
            ops.addOperation(
                document.OperationDatasetAddColumn(self.dsname, ds.columns[column])
            )
        if row == len(ds.data):
            ops.addOperation(document.OperationDatasetInsertRow(self.dsname, row, 1))

        try:
            val = ds.uiConvertToDataItem(value)
        except ValueError:
            return False

        ops.addOperation(
            document.OperationDatasetSetVal(self.dsname, ds.columns[column], row, val)
        )
        try:
            self.document.applyOperation(ops)
        except RuntimeError:
            return False
        return True


class DatasetTableModelMulti(qt.QAbstractTableModel):
    """Edit multiple 1D datasets side by side."""

    def __init__(self, parent, document, datasetnames):
        qt.QAbstractTableModel.__init__(self, parent)
        self.document = document
        self.dsnames = datasetnames
        self.changeset = -1
        self.rows = 0
        self._refreshTimer = qt.QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(50)
        self._refreshTimer.timeout.connect(self._doRefresh)
        document.signalModified.connect(self._scheduleRefresh)
        _autoDisconnectOnDestroyed(self, document.signalModified, self._scheduleRefresh)

    def _scheduleRefresh(self):
        if not self._refreshTimer.isActive():
            self._refreshTimer.start()

    def _doRefresh(self):
        self.updateCounts()
        self.layoutChanged.emit()

    def updateCounts(self):
        self.changeset = self.document.changeset
        rows = 0
        self.rowcounts = []
        self.colcounts = []
        self.colattrs = []

        for dsidx, name in enumerate(self.dsnames):
            if name not in self.document.data:
                continue
            dataset = self.document.data[name]
            if (
                not hasattr(dataset, "data")
                or not hasattr(dataset, "columns")
                or dataset.dimensions != 1
            ):
                continue

            r = len(dataset.data) + (1 if dataset.editable else 0)
            self.rowcounts.append(r)
            rows = max(rows, r)

            for colidx, col in enumerate(dataset.columns):
                data = getattr(dataset, col)
                if data is not None:
                    self.colattrs.append((name, col, dsidx, colidx))
            self.colcounts.append(len(self.colattrs))

        self.rows = rows

    def rowCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        if self.changeset != self.document.changeset:
            self.updateCounts()
        return self.rows

    def columnCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        if self.changeset != self.document.changeset:
            self.updateCounts()
        return len(self.colattrs)

    def data(self, index, role):
        dsname, colname, dsidx, colidx = self.colattrs[index.column()]
        ds = self.document.data[dsname]
        col_data = getattr(ds, colname)

        if role == qt.Qt.ItemDataRole.DisplayRole:
            if index.row() < self.rowcounts[dsidx] - (1 if ds.editable else 0):
                return ds.uiDataItemToData(col_data[index.row()])

        if role == qt.Qt.ItemDataRole.BackgroundRole:
            if not ds.editable:
                return _readonly_bg

        return None

    def headerData(self, section, orientation, role):
        if role == qt.Qt.ItemDataRole.DisplayRole:
            if orientation == qt.Qt.Orientation.Horizontal:
                dsname, colname, dsidx, colidx = self.colattrs[section]
                ds = self.document.data[dsname]
                return dsname + "\n" + ds.column_descriptions[colidx]
            else:
                if section == self.rows - 1:
                    return "\u2795"
                return section + 1
        return None

    def flags(self, index):
        if not index.isValid():
            return qt.Qt.ItemFlag.ItemIsEnabled
        f = qt.QAbstractTableModel.flags(self, index)
        dsname = self.colattrs[index.column()][0]
        ds = self.document.data.get(dsname)
        if ds is not None and ds.editable:
            f |= qt.Qt.ItemFlag.ItemIsEditable
        return f

    def setData(self, index, value, role):
        if not index.isValid() or role != qt.Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        dsname, colname, dsidx, colidx = self.colattrs[index.column()]
        ds = self.document.data[dsname]

        ops = document.OperationMultiple([], descr=_("set value"))
        edit_rows = self.rowcounts[dsidx] - (1 if ds.editable else 0)
        if row >= edit_rows:
            ops.addOperation(
                document.OperationDatasetInsertRow(
                    dsname, edit_rows, row + 1 - edit_rows
                )
            )

        try:
            val = ds.uiConvertToDataItem(value)
        except ValueError:
            return False

        ops.addOperation(document.OperationDatasetSetVal(dsname, colname, row, val))
        try:
            self.document.applyOperation(ops)
            return True
        except RuntimeError:
            return False

    def insertRows(self, row, count):
        ops = []
        for i, name in enumerate(self.dsnames):
            if i < len(self.rowcounts) and self.rowcounts[i] - 1 >= row:
                ops.append(document.OperationDatasetInsertRow(name, row, count))
        if ops:
            self.document.applyOperation(
                document.OperationMultiple(ops, _("insert rows"))
            )

    def removeRows(self, row, count):
        ops = []
        for i, name in enumerate(self.dsnames):
            if i < len(self.rowcounts) and self.rowcounts[i] - 1 >= row:
                ops.append(document.OperationDatasetDeleteRow(name, row, count))
        if ops:
            self.document.applyOperation(
                document.OperationMultiple(ops, _("delete rows"))
            )


class DatasetTableModel2D(qt.QAbstractTableModel):
    """A 2D dataset model."""

    def __init__(self, parent, document, datasetname):
        qt.QAbstractTableModel.__init__(self, parent)
        self.document = document
        self.dsname = datasetname
        self.updatePixelCoords()
        self._refreshTimer = qt.QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(50)
        self._refreshTimer.timeout.connect(self._doRefresh)
        document.signalModified.connect(self._scheduleRefresh)
        _autoDisconnectOnDestroyed(self, document.signalModified, self._scheduleRefresh)

    def _scheduleRefresh(self):
        if not self._refreshTimer.isActive():
            self._refreshTimer.start()

    def _doRefresh(self):
        self.updatePixelCoords()
        self.layoutChanged.emit()

    def updatePixelCoords(self):
        self.xedge = self.yedge = self.xcent = self.ycent = []
        ds = self.document.data.get(self.dsname)
        if ds and ds.dimensions == 2:
            self.xcent, self.ycent = ds.getPixelCentres()
            self.xedge, self.yedge = ds.getPixelEdges()

    def rowCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        try:
            data = self.document.data[self.dsname].data
        except KeyError:
            return 0
        return data.shape[0] if data is not None and data.ndim == 2 else 0

    def columnCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        try:
            data = self.document.data[self.dsname].data
        except KeyError:
            return 0
        return data.shape[1] if data is not None and data.ndim == 2 else 0

    def data(self, index, role):
        if role == qt.Qt.ItemDataRole.DisplayRole:
            try:
                data = self.document.data[self.dsname].data
            except KeyError:
                return None
            if data is not None and data.ndim == 2:
                try:
                    return float(data[data.shape[0] - index.row() - 1, index.column()])
                except IndexError:
                    pass

        if role == qt.Qt.ItemDataRole.BackgroundRole:
            ds = self.document.data.get(self.dsname)
            if ds is not None and not ds.editable:
                return _readonly_bg

        return None

    def headerData(self, section, orientation, role):
        ds = self.document.data.get(self.dsname)
        if ds is None or ds.dimensions != 2:
            return None

        xaxis = orientation == qt.Qt.Orientation.Horizontal
        if role == qt.Qt.ItemDataRole.DisplayRole:
            v = (
                self.xcent[section]
                if xaxis
                else self.ycent[len(self.ycent) - section - 1]
            )
            return "%i (%s)" % (
                len(self.ycent) - section,
                setting.ui_floattostring(v, maxdp=4),
            )

        elif role == qt.Qt.ItemDataRole.ToolTipRole:
            v1 = (
                self.xedge[section]
                if xaxis
                else self.yedge[len(self.yedge) - section - 2]
            )
            v2 = (
                self.xedge[section + 1]
                if xaxis
                else self.yedge[len(self.yedge) - section - 1]
            )
            return "%s\u2013%s" % (
                setting.ui_floattostring(v1),
                setting.ui_floattostring(v2),
            )

        return None

    def flags(self, index):
        if not index.isValid():
            return qt.Qt.ItemFlag.ItemIsEnabled
        f = qt.QAbstractTableModel.flags(self, index)
        ds = self.document.data.get(self.dsname)
        if ds is not None and ds.editable:
            f |= qt.Qt.ItemFlag.ItemIsEditable
        return f

    def setData(self, index, value, role):
        if not index.isValid() or role != qt.Qt.ItemDataRole.EditRole:
            return False
        ds = self.document.data[self.dsname]
        row = ds.data.shape[0] - index.row() - 1
        col = index.column()
        try:
            val = ds.uiConvertToDataItem(value)
        except ValueError:
            return False
        self.document.applyOperation(
            document.OperationDatasetSetVal2D(self.dsname, row, col, val)
        )
        return True


class DatasetTableModelND(qt.QAbstractTableModel):
    """An ND dataset model."""

    def __init__(self, parent, document, datasetname):
        qt.QAbstractTableModel.__init__(self, parent)
        self.document = document
        self.dsname = datasetname
        self._refreshTimer = qt.QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(50)
        self._refreshTimer.timeout.connect(lambda: self.layoutChanged.emit())
        document.signalModified.connect(self._scheduleRefresh)
        _autoDisconnectOnDestroyed(self, document.signalModified, self._scheduleRefresh)

    def _scheduleRefresh(self):
        if not self._refreshTimer.isActive():
            self._refreshTimer.start()

    def rowCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        try:
            data = self.document.data[self.dsname].data
        except KeyError:
            return 0
        return 0 if data is None else data.size

    def columnCount(self, parent=qt.QModelIndex()):
        if parent.isValid():
            return 0
        try:
            data = self.document.data[self.dsname].data
        except KeyError:
            return 0
        return 1 if data is not None else 0

    def data(self, index, role):
        if role == qt.Qt.ItemDataRole.DisplayRole:
            try:
                data = self.document.data[self.dsname].data
            except KeyError:
                return None
            if data is not None:
                try:
                    return float(N.ravel(data)[index.row()])
                except IndexError:
                    pass

        if role == qt.Qt.ItemDataRole.BackgroundRole:
            ds = self.document.data.get(self.dsname)
            if ds is not None and not ds.editable:
                return _readonly_bg

        return None

    def headerData(self, section, orientation, role):
        ds = self.document.data.get(self.dsname)
        if ds is None:
            return None
        if role == qt.Qt.ItemDataRole.DisplayRole:
            if orientation == qt.Qt.Orientation.Horizontal:
                return _("Value")
            else:
                idx = N.unravel_index(section, ds.data.shape)
                return ",".join([str(v + 1) for v in idx])
        return None


# ── View Delegate ────────────────────────────────────────────────


class ViewDelegate(qt.QStyledItemDelegate):
    """Delegate with validation feedback and proper float editing."""

    def createEditor(self, parent, option, index):
        editor = qt.QLineEdit(parent)
        return editor

    def setEditorData(self, editor, index):
        val = index.data()
        if isinstance(val, float):
            editor.setText(setting.ui_floattostring(val))
        elif val is not None:
            editor.setText(str(val))
        else:
            editor.setText("")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        """Commit edit with validation feedback."""
        value = editor.text()
        if not value and index.data() is None:
            return

        success = model.setData(index, value, qt.Qt.ItemDataRole.EditRole)
        if not success and value:
            # flash red for invalid input
            try:
                editor.setStyleSheet("background-color: #ffcccc;")
                qt.QToolTip.showText(
                    editor.mapToGlobal(qt.QPoint(0, editor.height())),
                    _('Invalid value: "%s"') % value,
                    editor,
                    qt.QRect(),
                    2000,
                )
            except RuntimeError:
                pass


class _EnterMovesDownFilter(qt.QObject):
    """Event filter that makes Enter move down (like a spreadsheet)."""

    def eventFilter(self, obj, event):
        if (
            isinstance(event, qt.QKeyEvent)
            and event.type() == qt.QEvent.Type.KeyPress
            and event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter)
        ):
            view = obj
            if isinstance(view, qt.QTableView) and view.model():
                # close any active editor
                if view.state() == qt.QAbstractItemView.State.EditingState:
                    view.commitData(view.indexWidget(view.currentIndex()))
                    view.closeEditor(
                        view.indexWidget(view.currentIndex()),
                        qt.QAbstractItemDelegate.EndEditHint.NoHint,
                    )
                # move down
                cur = view.currentIndex()
                nxt = view.model().index(cur.row() + 1, cur.column())
                if nxt.isValid():
                    view.setCurrentIndex(nxt)
                return True
        return False


# ── Main Dialog ──────────────────────────────────────────────────


class DataEditDialog(VeuszDialog):
    """Dialog for editing and rearranging data sets."""

    def __init__(self, parent, document):
        VeuszDialog.__init__(self, parent, "dataedit.ui")
        self.document = document

        # configure the existing QTableView for spreadsheet behavior
        self.datatableview.setEditTriggers(
            qt.QAbstractItemView.EditTrigger.DoubleClicked
            | qt.QAbstractItemView.EditTrigger.EditKeyPressed
            | qt.QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.datatableview.setSelectionMode(
            qt.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.datatableview.setTabKeyNavigation(True)

        # set up dataset browser
        self.dsbrowser = DatasetBrowser(document, parent, parent)
        self.dsbrowser.setToolTip(_("Select multiple datasets to edit simultaneously"))
        self.splitter.insertWidget(0, self.dsbrowser)

        self.delegate = ViewDelegate()
        self.datatableview.setItemDelegate(self.delegate)

        # Enter moves down like a spreadsheet
        self._enterFilter = _EnterMovesDownFilter(self)
        self.datatableview.installEventFilter(self._enterFilter)

        # ── Toolbar above table ──────────────────────────────
        toolbar = qt.QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        self.addRowBtn = qt.QPushButton(_("Add Row"))
        self.addRowBtn.setToolTip(_("Append a new row at the end"))
        self.deleteRowsBtn = qt.QPushButton(_("Delete Row(s)"))
        self.deleteRowsBtn.setToolTip(_("Delete selected rows"))
        self.pasteBtn = qt.QPushButton(_("Paste"))
        self.pasteBtn.setToolTip(
            _("Paste data from clipboard into selected cells (Ctrl+V)")
        )
        self.pasteNewBtn = qt.QPushButton(_("Paste as New"))
        self.pasteNewBtn.setToolTip(_("Create new dataset(s) from clipboard data"))

        toolbar.addWidget(self.addRowBtn)
        toolbar.addWidget(self.deleteRowsBtn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.pasteBtn)
        toolbar.addWidget(self.pasteNewBtn)

        # insert toolbar before the table in the splitter's right side
        right_widget = self.splitter.widget(1)
        if right_widget and right_widget.layout():
            right_widget.layout().insertLayout(0, toolbar)

        # ── Status label for feedback ────────────────────────
        self.statusLabel = qt.QLabel()
        self.statusLabel.setStyleSheet("color: #888; font-size: 9pt;")
        if right_widget and right_widget.layout():
            right_widget.layout().addWidget(self.statusLabel)

        # ── Context menu ─────────────────────────────────────
        self.datatableview.setContextMenuPolicy(
            qt.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.datatableview.customContextMenuRequested.connect(self._showContextMenu)

        # ── Keyboard shortcuts ───────────────────────────────
        paste_sc = qt.QShortcut(qt.QKeySequence.StandardKey.Paste, self.datatableview)
        paste_sc.activated.connect(self.slotPaste)
        copy_sc = qt.QShortcut(qt.QKeySequence.StandardKey.Copy, self.datatableview)
        copy_sc.activated.connect(self.slotCopy)
        del_sc = qt.QShortcut(qt.QKeySequence.StandardKey.Delete, self.datatableview)
        del_sc.activated.connect(self.slotClearSelection)

        # ── Layout ───────────────────────────────────────────
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 4)

        self.linkedlabel.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.linkedlabel.viewport().setBackgroundRole(qt.QPalette.ColorRole.Window)

        # ── Connections ──────────────────────────────────────
        document.signalModified.connect(self.slotDocumentModified)
        _autoDisconnectOnDestroyed(
            self, document.signalModified, self.slotDocumentModified
        )

        self.addRowBtn.clicked.connect(self.slotAppendRow)
        self.deleteRowsBtn.clicked.connect(self.slotDeleteRows)
        self.pasteBtn.clicked.connect(self.slotPaste)
        self.pasteNewBtn.clicked.connect(self.slotPasteAsNew)

        for btn, slot in (
            (self.deletebutton, self.slotDatasetDelete),
            (self.unlinkbutton, self.slotDatasetUnlink),
            (self.duplicatebutton, self.slotDatasetDuplicate),
            (self.importbutton, self.slotDatasetImport),
            (self.createbutton, self.slotDatasetCreate),
            (self.editbutton, self.slotDatasetEdit),
        ):
            btn.clicked.connect(slot)

        self.newmenu = qt.QMenu(self)
        for text, slot in (
            (_("Numerical dataset"), self.slotNewNumericalDataset),
            (_("Text dataset"), self.slotNewTextDataset),
            (_("Date/time dataset"), self.slotNewDateDataset),
        ):
            self.newmenu.addAction(text).triggered.connect(slot)
        self.newbutton.setMenu(self.newmenu)

        self.dsbrowser.navtree.selecteddatasets.connect(self.slotDatasetsSelected)

        # select first dataset
        if len(self.document.data) > 0:
            self.selectDataset(sorted(self.document.data)[0])
        else:
            self.slotDatasetsSelected([])

    # ── Context menu ─────────────────────────────────────────

    def _showContextMenu(self, pos):
        menu = qt.QMenu(self)
        model = self.datatableview.model()
        has_model = model is not None

        menu.addAction(_("Copy"), self.slotCopy).setEnabled(has_model)
        menu.addAction(_("Paste"), self.slotPaste).setEnabled(has_model)
        menu.addAction(_("Paste as New Dataset…"), self.slotPasteAsNew)
        menu.addSeparator()
        selmodel = self.datatableview.selectionModel()
        n = 1
        if selmodel and selmodel.hasSelection():
            n = len(set(idx.row() for idx in selmodel.selectedIndexes()))

        insert_text = (_("Insert Rows (%d)") % n) if n > 1 else _("Insert Row")
        delete_text = (_("Delete Rows (%d)") % n) if n > 1 else _("Delete Row")

        menu.addAction(insert_text, self.slotInsertRow).setEnabled(has_model)
        menu.addAction(delete_text, self.slotDeleteRows).setEnabled(has_model)
        menu.addAction(_("Clear Selection"), self.slotClearSelection).setEnabled(
            has_model
        )

        menu.exec(self.datatableview.viewport().mapToGlobal(pos))

    # ── Dataset selection ────────────────────────────────────

    def slotDatasetsSelected(self, names):
        """Called when a new dataset is selected."""
        model = None
        if len(names) == 1:
            ds = self.document.data.get(names[0])
            if ds is not None:
                if ds.dimensions == 1:
                    model = DatasetTableModel1D(self, self.document, names[0])
                elif ds.dimensions == 2:
                    model = DatasetTableModel2D(self, self.document, names[0])
                elif ds.dimensions == -1:
                    model = DatasetTableModelND(self, self.document, names[0])
        elif len(names) > 1:
            model = DatasetTableModelMulti(self, self.document, names)

        self.datatableview.setModel(model)

        # reconnect selection change for button labels
        if self.datatableview.selectionModel():
            self.datatableview.selectionModel().selectionChanged.connect(
                self._updateRowButtonLabels
            )
        self._updateRowButtonLabels()

        # update toolbar state
        editable = False
        if names:
            for n in names:
                ds = self.document.data.get(n)
                if ds and ds.editable:
                    editable = True
                    break
        self.addRowBtn.setEnabled(editable)
        self.deleteRowsBtn.setEnabled(editable)
        self.pasteBtn.setEnabled(editable)

        # status
        if names and not editable:
            self.statusLabel.setText(_("Read-only dataset"))
        else:
            self.statusLabel.setText("")

        self.setUnlinkState()

    def setUnlinkState(self):
        linkinfo = []
        canunlink = []
        canedit = []
        names = self.dsbrowser.navtree.getSelectedDatasets()
        for name in names:
            ds = self.document.data.get(name)
            if ds is None:
                continue
            canunlink.append(ds.canUnlink())
            if len(names) > 1:
                linkinfo.append(name)
            linkinfo.append(ds.linkedInformation())
            canedit.append(type(ds) in recreate_register)

        self.editbutton.setVisible(any(canedit))
        self.unlinkbutton.setEnabled(any(canunlink))
        self.linkedlabel.setText("\n".join(linkinfo))
        self.deletebutton.setEnabled(bool(names))
        self.duplicatebutton.setEnabled(bool(names))

    def slotDocumentModified(self):
        self.setUnlinkState()

    def _updateRowButtonLabels(self):
        """Update Add/Delete button text with row count."""
        selmodel = self.datatableview.selectionModel()
        if selmodel and selmodel.hasSelection():
            n = len(set(idx.row() for idx in selmodel.selectedIndexes()))
        else:
            n = 1

        if n > 1:
            self.addRowBtn.setText(_("Add Rows (%d)") % n)
            self.deleteRowsBtn.setText(_("Delete Rows (%d)") % n)
        else:
            self.addRowBtn.setText(_("Add Row"))
            self.deleteRowsBtn.setText(_("Delete Row"))

    def selectDataset(self, dsname):
        self.dsbrowser.navtree.selectDataset(dsname)
        self.slotDatasetsSelected([dsname])

    # ── Copy ─────────────────────────────────────────────────

    def slotCopy(self):
        """Copy selected cells as tab-separated text."""
        selmodel = self.datatableview.selectionModel()
        model = self.datatableview.model()
        if not model or not selmodel:
            return

        indices = sorted(
            [(idx.row(), idx.column()) for idx in selmodel.selectedIndexes()]
        )

        lines = []
        rowitems = []
        lastrow = -1
        for row, column in indices:
            if row != lastrow:
                if rowitems:
                    lines.append("\t".join(rowitems))
                    rowitems = []
                lastrow = row
            val = model.createIndex(row, column).data()
            rowitems.append(str(val) if val is not None else "")
        if rowitems:
            lines.append("\t".join(rowitems))

        qt.QApplication.clipboard().setText("\n".join(lines))
        self.statusLabel.setText(_("Copied %d cells") % len(indices))
        utils.safe_singleShot(3000, self, self.statusLabel.clear)

    # ── Paste into existing dataset ──────────────────────────

    def slotPaste(self):
        """Paste clipboard data into selected cells."""
        model = self.datatableview.model()
        if model is None:
            return

        text = qt.QApplication.clipboard().text()
        if not text:
            return

        rows = text.rstrip("\n").split("\n")
        parsed = [row.split("\t") for row in rows]

        current = self.datatableview.currentIndex()
        start_row = current.row() if current.isValid() else 0
        start_col = current.column() if current.isValid() else 0

        count = 0
        for r_off, row_data in enumerate(parsed):
            for c_off, cell_text in enumerate(row_data):
                target_row = start_row + r_off
                target_col = start_col + c_off
                idx = model.index(target_row, target_col)
                if idx.isValid():
                    if model.setData(
                        idx, cell_text.strip(), qt.Qt.ItemDataRole.EditRole
                    ):
                        count += 1

        self.statusLabel.setText(_("Pasted %d values") % count)
        utils.safe_singleShot(3000, self, self.statusLabel.clear)

    # ── Paste as new dataset(s) ──────────────────────────────

    def slotPasteAsNew(self):
        """Create new dataset(s) from clipboard."""
        text = qt.QApplication.clipboard().text()
        if not text:
            self.statusLabel.setText(_("Clipboard is empty"))
            utils.safe_singleShot(3000, self, self.statusLabel.clear)
            return

        rows = text.rstrip("\n").split("\n")
        parsed = [row.split("\t") for row in rows if row.strip()]
        if not parsed:
            return

        num_cols = max(len(row) for row in parsed)

        # detect headers in first row
        first_is_header = False
        if num_cols > 0:
            try:
                [float(c.replace(",", ".")) for c in parsed[0] if c.strip()]
            except ValueError:
                first_is_header = True

        start = 1 if first_is_header else 0
        ops = []
        created_names = []

        for col_idx in range(num_cols):
            values = []
            for row in parsed[start:]:
                if col_idx < len(row) and row[col_idx].strip():
                    try:
                        values.append(float(row[col_idx].strip().replace(",", ".")))
                    except ValueError:
                        values.append(float("nan"))
                else:
                    values.append(float("nan"))

            if not values or all(N.isnan(v) for v in values):
                continue

            if first_is_header and col_idx < len(parsed[0]):
                name = parsed[0][col_idx].strip()
                if not name:
                    name = "col_%d" % (col_idx + 1)
            else:
                name = "pasted_%d" % (col_idx + 1)

            # unique name
            base = name
            counter = 2
            while name in self.document.data:
                name = "%s_%d" % (base, counter)
                counter += 1

            ds = datasets.Dataset(data=N.array(values))
            ops.append(document.OperationDatasetSet(name, ds))
            created_names.append(name)

        if ops:
            self.document.applyOperation(
                document.OperationMultiple(ops, _("paste as new datasets"))
            )
            # select all created datasets so they appear side by side
            if len(created_names) > 1:
                self.dsbrowser.selectDatasets(created_names)
                self.slotDatasetsSelected(created_names)
            else:
                self.selectDataset(created_names[0])
            self.statusLabel.setText(
                _("Created %d dataset(s): %s")
                % (len(created_names), ", ".join(created_names))
            )
            utils.safe_singleShot(5000, self, self.statusLabel.clear)

    # ── Row operations ───────────────────────────────────────

    def slotAppendRow(self):
        """Insert row(s) below selection.

        If multiple rows are selected, inserts the same number of
        rows. If no selection, appends one row at the end.
        """
        model = self.datatableview.model()
        if model is None:
            return
        names = self.dsbrowser.navtree.getSelectedDatasets()
        if not names:
            return
        ds = self.document.data.get(names[0])
        if not ds or not ds.editable:
            return

        selmodel = self.datatableview.selectionModel()
        if selmodel and selmodel.hasSelection():
            rows = sorted(set(idx.row() for idx in selmodel.selectedIndexes()))
            count = len(rows)
            insert_at = rows[-1] + 1  # below the last selected row
        else:
            count = 1
            cur = self.datatableview.currentIndex()
            if cur.isValid():
                insert_at = cur.row() + 1
            else:
                insert_at = len(ds.data)

        # clamp to data length
        insert_at = min(insert_at, len(ds.data))
        model.insertRows(insert_at, count)

    def slotInsertRow(self):
        """Insert row(s) at current position (context menu)."""
        model = self.datatableview.model()
        if model is None:
            return
        selmodel = self.datatableview.selectionModel()
        if selmodel and selmodel.hasSelection():
            rows = sorted(set(idx.row() for idx in selmodel.selectedIndexes()))
            model.insertRows(rows[0], len(rows))
        else:
            model.insertRows(self.datatableview.currentIndex().row(), 1)

    def slotDeleteRows(self):
        """Delete selected rows."""
        model = self.datatableview.model()
        selmodel = self.datatableview.selectionModel()
        if not model or not selmodel:
            return
        rows = sorted(
            set(idx.row() for idx in selmodel.selectedIndexes()), reverse=True
        )
        for row in rows:
            model.removeRows(row, 1)

    def slotClearSelection(self):
        """Clear selected cells to default value."""
        model = self.datatableview.model()
        selmodel = self.datatableview.selectionModel()
        if not model or not selmodel:
            return
        for idx in selmodel.selectedIndexes():
            model.setData(idx, "0", qt.Qt.ItemDataRole.EditRole)

    # ── Dataset operations ───────────────────────────────────

    def slotDatasetDelete(self):
        dsnames = self.dsbrowser.navtree.getSelectedDatasets()
        if dsnames:
            self.document.applyOperation(
                document.OperationMultiple(
                    [document.OperationDatasetDelete(n) for n in dsnames],
                    descr=_("delete datasets"),
                )
            )

    def slotDatasetUnlink(self):
        ops = []
        for name in self.dsbrowser.navtree.getSelectedDatasets():
            d = self.document.data.get(name)
            if d is None:
                continue
            if d.linked is not None:
                ops.append(document.OperationDatasetUnlinkFile(name))
            elif d.canUnlink():
                ops.append(document.OperationDatasetUnlinkRelation(name))
        if ops:
            self.document.applyOperation(
                document.OperationMultiple(ops, _("unlink datasets"))
            )

    def slotDatasetDuplicate(self):
        ops = []
        for name in self.dsbrowser.navtree.getSelectedDatasets():
            index = 2
            while True:
                newname = "%s_%d" % (name, index)
                if newname not in self.document.data:
                    break
                index += 1
            ops.append(document.OperationDatasetDuplicate(name, newname))
        if ops:
            self.document.applyOperation(
                document.OperationMultiple(ops, _("duplicate datasets"))
            )

    def slotDatasetImport(self):
        self.mainwindow.slotDataImport()

    def slotDatasetCreate(self):
        self.mainwindow.slotDataCreate()

    def slotDatasetEdit(self):
        for name in self.dsbrowser.navtree.getSelectedDatasets():
            dataset = self.document.data.get(name)
            if dataset is not None:
                try:
                    recreate_register[type(dataset)](
                        self.mainwindow, self.document, dataset, name
                    )
                except KeyError:
                    pass

    # ── New dataset ──────────────────────────────────────────

    def slotNewNumericalDataset(self):
        self.newDataset(datasets.Dataset(data=[0.0]))

    def slotNewTextDataset(self):
        self.newDataset(datasets.DatasetText(data=[""]))

    def slotNewDateDataset(self):
        self.newDataset(datasets.DatasetDateTime(data=[]))

    def newDataset(self, ds):
        name = _("new dataset")
        if name in self.document.data:
            count = 1
            while name in self.document.data:
                name = _("new dataset %i") % count
                count += 1
        self.document.applyOperation(document.OperationDatasetSet(name, ds))
        self.dsbrowser.selectDataset(name)
