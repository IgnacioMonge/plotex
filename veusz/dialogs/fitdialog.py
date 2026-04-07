#    Copyright (C) 2026 M. Ignacio Monge Garcia
#
#    This file is part of Plotex (based on Veusz).
#
##############################################################################

"""Fit dialog for interactive curve fitting.

Inspired by GraphPad Prism fit dialog and lmfit reporting.
"""

from .. import qtall as qt
from .. import document

def _(text, disambiguation=None, context='FitDialog'):
    return qt.QCoreApplication.translate(context, text, disambiguation)


# common functions (like Prism's function library)
_FUNCTION_PRESETS = [
    ('Linear', 'a + b*x'),
    ('Quadratic', 'a + b*x + c*x**2'),
    ('Cubic', 'a + b*x + c*x**2 + d*x**3'),
    ('Power', 'a * x**b'),
    ('Exponential growth', 'a * exp(b*x)'),
    ('Exponential decay', 'a * exp(-b*x) + c'),
    ('Gaussian', 'a * exp(-((x-b)/c)**2 / 2)'),
    ('Lorentzian', 'a / (1 + ((x-b)/c)**2)'),
    ('Sigmoidal (logistic)', 'a / (1 + exp(-b*(x-c)))'),
    ('Log', 'a + b*log(x)'),
    ('Michaelis-Menten', 'a*x / (b + x)'),
    ('Hill equation', 'a * x**b / (c**b + x**b)'),
]


class FitDialog(qt.QDialog):
    """Dialog for interactive fitting of data."""

    def __init__(self, fitwidget, parent=None):
        super().__init__(parent)
        self.fitwidget = fitwidget
        self.setWindowTitle(_('Curve Fit — %s') % fitwidget.name)
        self.setMinimumSize(560, 520)
        self._build()
        self._loadFromWidget()

    def _build(self):
        layout = qt.QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Function with presets ──
        fgroup = qt.QGroupBox(_('Function'))
        flayout = qt.QGridLayout(fgroup)

        flayout.addWidget(qt.QLabel('f(x) ='), 0, 0)
        self.funcEdit = qt.QLineEdit()
        self.funcEdit.setFont(qt.QFont('Consolas', 11))
        self.funcEdit.setPlaceholderText('a + b*x')
        flayout.addWidget(self.funcEdit, 0, 1)

        self.presetCombo = qt.QComboBox()
        self.presetCombo.addItem(_('— Presets —'))
        for name, expr in _FUNCTION_PRESETS:
            self.presetCombo.addItem(name, expr)
        self.presetCombo.currentIndexChanged.connect(self._onPreset)
        flayout.addWidget(self.presetCombo, 0, 2)

        # variable selector
        flayout.addWidget(qt.QLabel(_('Variable:')), 1, 0)
        self.varCombo = qt.QComboBox()
        self.varCombo.addItems(['x', 'y'])
        flayout.addWidget(self.varCombo, 1, 1)

        layout.addWidget(fgroup)

        # ── Parameters table ──
        pgroup = qt.QGroupBox(_('Parameters'))
        playout = qt.QVBoxLayout(pgroup)

        self.paramTable = qt.QTableWidget()
        self.paramTable.setColumnCount(4)
        self.paramTable.setHorizontalHeaderLabels(
            [_('Name'), _('Initial value'), _('Fitted value'), _('Error (\u00b1)')])
        hdr = self.paramTable.horizontalHeader()
        hdr.setSectionResizeMode(0, qt.QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, qt.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, qt.QHeaderView.ResizeMode.Stretch)
        self.paramTable.verticalHeader().setVisible(False)
        self.paramTable.setAlternatingRowColors(True)
        playout.addWidget(self.paramTable)

        pbtn = qt.QHBoxLayout()
        self.addParamBtn = qt.QPushButton(_('+ Add'))
        self.addParamBtn.clicked.connect(self._addParam)
        self.removeParamBtn = qt.QPushButton(_('- Remove'))
        self.removeParamBtn.clicked.connect(self._removeParam)
        self.autoParamBtn = qt.QPushButton(_('Auto-detect'))
        self.autoParamBtn.setToolTip(
            _('Parse function and create parameters automatically'))
        self.autoParamBtn.clicked.connect(self._autoDetectParams)
        pbtn.addWidget(self.addParamBtn)
        pbtn.addWidget(self.removeParamBtn)
        pbtn.addWidget(self.autoParamBtn)
        pbtn.addStretch()
        playout.addLayout(pbtn)
        layout.addWidget(pgroup)

        # ── Data & Options ──
        ogroup = qt.QGroupBox(_('Data && Options'))
        olayout = qt.QGridLayout(ogroup)

        olayout.addWidget(qt.QLabel(_('X data:')), 0, 0)
        self.xDataEdit = qt.QLineEdit()
        olayout.addWidget(self.xDataEdit, 0, 1)

        olayout.addWidget(qt.QLabel(_('Y data:')), 0, 2)
        self.yDataEdit = qt.QLineEdit()
        olayout.addWidget(self.yDataEdit, 0, 3)

        olayout.addWidget(qt.QLabel(_('Error:')), 1, 0)
        self.defErrSpin = qt.QDoubleSpinBox()
        self.defErrSpin.setDecimals(4)
        self.defErrSpin.setRange(0.0001, 1e6)
        self.defErrSpin.setValue(0.05)
        olayout.addWidget(self.defErrSpin, 1, 1)

        self.confBandCheck = qt.QCheckBox(_('95% confidence band'))
        olayout.addWidget(self.confBandCheck, 1, 2)
        self.predBandCheck = qt.QCheckBox(_('Prediction band'))
        olayout.addWidget(self.predBandCheck, 1, 3)

        self.addLabelCheck = qt.QCheckBox(_('Add result label to graph'))
        olayout.addWidget(self.addLabelCheck, 2, 0, 1, 2)

        self.labelFormatCombo = qt.QComboBox()
        self.labelFormatCombo.addItems([
            'equation + R²',
            'equation only',
            'R² only',
            'equation + R² + params',
        ])
        olayout.addWidget(self.labelFormatCombo, 2, 2, 1, 2)

        layout.addWidget(ogroup)

        # ── Results ──
        rgroup = qt.QGroupBox(_('Goodness of fit'))
        rlayout = qt.QVBoxLayout(rgroup)
        self.resultText = qt.QTextEdit()
        self.resultText.setReadOnly(True)
        self.resultText.setMaximumHeight(80)
        self.resultText.setFont(qt.QFont('Consolas', 10))
        self.resultText.setPlainText(_('Press Fit to start'))
        rlayout.addWidget(self.resultText)
        layout.addWidget(rgroup)

        # ── Buttons ──
        btnLayout = qt.QHBoxLayout()

        self.fitBtn = qt.QPushButton(_('  Fit  '))
        self.fitBtn.setDefault(True)
        self.fitBtn.setStyleSheet(
            'font-weight: bold; font-size: 13px; padding: 8px 32px; '
            'background: #0066cc; color: white; border-radius: 4px;')
        self.fitBtn.clicked.connect(self._doFit)

        self.resetBtn = qt.QPushButton(_('Reset'))
        self.resetBtn.clicked.connect(self._loadFromWidget)

        self.closeBtn = qt.QPushButton(_('Close'))
        self.closeBtn.clicked.connect(self.accept)

        btnLayout.addWidget(self.resetBtn)
        btnLayout.addStretch()
        btnLayout.addWidget(self.fitBtn)
        btnLayout.addWidget(self.closeBtn)
        layout.addLayout(btnLayout)

    def _onPreset(self, index):
        """Apply a function preset."""
        if index <= 0:
            return
        expr = self.presetCombo.itemData(index)
        if expr:
            self.funcEdit.setText(expr)
            self._autoDetectParams()
            # clear previous results since function changed
            self.resultText.setPlainText(_('Function changed — press Fit'))
            for row in range(self.paramTable.rowCount()):
                for col in (2, 3):
                    item = self.paramTable.item(row, col)
                    if item:
                        item.setText('')

    def _autoDetectParams(self):
        """Parse function string and create parameter entries."""
        import re
        func = self.funcEdit.text()
        # find single-letter variables that aren't the independent variable
        # or known functions
        var = self.varCombo.currentText()
        known = {
            var, 'exp', 'log', 'sin', 'cos', 'tan', 'sqrt', 'abs',
            'pi', 'e', 'arcsin', 'arccos', 'arctan', 'sinh', 'cosh',
            'tanh', 'log10', 'log2',
        }
        tokens = set(re.findall(r'\b([a-zA-Z_]\w*)\b', func))
        params = sorted(tokens - known)

        if not params:
            return

        # preserve existing values
        existing = self._getParams()

        self.paramTable.setRowCount(len(params))
        for row, name in enumerate(params):
            self._setParamRow(row, name, existing.get(name, 1.0))

    def _setParamRow(self, row, name, initial, fitted='', error=''):
        """Set a parameter row in the table."""
        nameItem = qt.QTableWidgetItem(name)
        nameItem.setFlags(
            nameItem.flags() & ~qt.Qt.ItemFlag.ItemIsEditable)
        nameItem.setFont(qt.QFont('Consolas', 10))
        self.paramTable.setItem(row, 0, nameItem)

        valItem = qt.QTableWidgetItem('%.6g' % initial)
        valItem.setFont(qt.QFont('Consolas', 10))
        self.paramTable.setItem(row, 1, valItem)

        fittedItem = qt.QTableWidgetItem(str(fitted))
        fittedItem.setFlags(
            fittedItem.flags() & ~qt.Qt.ItemFlag.ItemIsEditable)
        fittedItem.setForeground(qt.QColor('#0066cc'))
        fittedItem.setFont(qt.QFont('Consolas', 10))
        self.paramTable.setItem(row, 2, fittedItem)

        errItem = qt.QTableWidgetItem(str(error))
        errItem.setFlags(
            errItem.flags() & ~qt.Qt.ItemFlag.ItemIsEditable)
        errItem.setForeground(qt.QColor('#888888'))
        errItem.setFont(qt.QFont('Consolas', 10))
        self.paramTable.setItem(row, 3, errItem)

    def _loadFromWidget(self):
        """Load current settings from the fit widget."""
        s = self.fitwidget.settings

        self.funcEdit.setText(s.function)
        self.varCombo.setCurrentText(s.variable)
        self.xDataEdit.setText(s.xData)
        self.yDataEdit.setText(s.yData)
        self.defErrSpin.setValue(s.defErr)
        self.confBandCheck.setChecked(s.showConfBand)
        self.predBandCheck.setChecked(s.showPredBand)

        params = s.values
        errors = s.paramErrors if hasattr(s, 'paramErrors') else {}

        self.paramTable.setRowCount(len(params))
        for row, (name, val) in enumerate(sorted(params.items())):
            fitted = '%.6g' % val if s.chi2 > 0 else ''
            err = ('\u00b1 %.4g' % errors[name]
                   if name in errors and errors[name] > 0 else '')
            self._setParamRow(row, name, val, fitted, err)

        if s.chi2 > 0:
            self._showResults(s.values, errors, s.chi2, s.dof)
        else:
            self.resultText.setPlainText(_('Press Fit to start'))

    def _addParam(self):
        """Add a new parameter row."""
        row = self.paramTable.rowCount()
        existing = set()
        for r in range(row):
            item = self.paramTable.item(r, 0)
            if item:
                existing.add(item.text())

        for ch in 'cdefghijklmnopqrstuvwxyz':
            if ch not in existing:
                name = ch
                break
        else:
            name = 'p%d' % row

        self.paramTable.setRowCount(row + 1)
        self._setParamRow(row, name, 1.0)

    def _removeParam(self):
        """Remove selected parameter row."""
        row = self.paramTable.currentRow()
        if row >= 0:
            self.paramTable.removeRow(row)

    def _getParams(self):
        """Read parameters from table."""
        params = {}
        for row in range(self.paramTable.rowCount()):
            nameItem = self.paramTable.item(row, 0)
            valItem = self.paramTable.item(row, 1)
            if nameItem and valItem:
                try:
                    params[nameItem.text()] = float(valItem.text())
                except ValueError:
                    params[nameItem.text()] = 0.0
        return params

    def _saveToWidget(self):
        """Save dialog settings to the fit widget."""
        s = self.fitwidget.settings
        doc = self.fitwidget.document
        ops = []

        for attr, edit in [
            ('function', self.funcEdit.text()),
            ('xData', self.xDataEdit.text()),
            ('yData', self.yDataEdit.text()),
        ]:
            if getattr(s, attr) != edit:
                ops.append(document.OperationSettingSet(
                    s.get(attr), edit))

        var = self.varCombo.currentText()
        if s.variable != var:
            ops.append(document.OperationSettingSet(
                s.get('variable'), var))

        params = self._getParams()
        if params != s.values:
            ops.append(document.OperationSettingSet(
                s.get('values'), params))

        defErr = self.defErrSpin.value()
        if defErr != s.defErr:
            ops.append(document.OperationSettingSet(
                s.get('defErr'), defErr))

        for attr, check in [
            ('showConfBand', self.confBandCheck),
            ('showPredBand', self.predBandCheck),
        ]:
            if check.isChecked() != getattr(s, attr):
                ops.append(document.OperationSettingSet(
                    s.get(attr), check.isChecked()))

        if ops:
            doc.applyOperation(
                document.OperationMultiple(
                    ops, descr=_('update fit settings')))

    def _doFit(self):
        """Run the fit and update plot in real time."""
        self.fitBtn.setEnabled(False)
        self.fitBtn.setText(_('Fitting…'))
        self.resultText.setPlainText(_('Fitting…'))
        qt.QApplication.processEvents()

        try:
            self._saveToWidget()
            self.fitwidget.actionFit()

            # force plot update so the user sees the curve immediately
            doc = self.fitwidget.document
            doc.setModified()
            doc.signalModified.emit(True)
            qt.QApplication.processEvents()
            # give render thread time to finish
            qt.QApplication.processEvents()
            qt.QApplication.processEvents()

            s = self.fitwidget.settings
            if s.chi2 > 0:
                self._showResults(s.values, s.paramErrors, s.chi2, s.dof)

                # update table with fitted values
                for row in range(self.paramTable.rowCount()):
                    nameItem = self.paramTable.item(row, 0)
                    if nameItem is None:
                        continue
                    name = nameItem.text()

                    if name in s.values:
                        # update initial to fitted
                        valItem = self.paramTable.item(row, 1)
                        if valItem:
                            valItem.setText('%.6g' % s.values[name])
                        # show fitted
                        fittedItem = self.paramTable.item(row, 2)
                        if fittedItem:
                            fittedItem.setText('%.6g' % s.values[name])

                    if name in s.paramErrors and s.paramErrors[name] > 0:
                        errItem = self.paramTable.item(row, 3)
                        if errItem:
                            errItem.setText(
                                '\u00b1 %.4g' % s.paramErrors[name])
                # add result label to graph if requested
                if self.addLabelCheck.isChecked():
                    self._addResultLabel(s)

            else:
                self.resultText.setPlainText(_('Fit did not converge'))

        except Exception as e:
            self.resultText.setPlainText(_('Error: %s') % str(e))

        self.fitBtn.setEnabled(True)
        self.fitBtn.setText(_('  Fit  '))

    def _showResults(self, values, errors, chi2, dof):
        """Show goodness-of-fit report."""
        redchi2 = chi2 / max(dof, 1)

        lines = []
        lines.append('\u03c7\u00b2 = %.6g' % chi2)
        lines.append('d.o.f. = %d' % dof)
        lines.append('\u03c7\u00b2/dof = %.4g' % redchi2)

        # build expression with fitted values
        s = self.fitwidget.settings
        expr = s.function
        for name in sorted(values.keys(), key=len, reverse=True):
            expr = expr.replace(name, '%.4g' % values[name])
        lines.append('')
        lines.append('f(x) = %s' % expr)

        self.resultText.setPlainText('\n'.join(lines))

    def _addResultLabel(self, s):
        """Create or update a text label on the graph with fit results."""
        import numpy as N

        doc = self.fitwidget.document
        graph = self.fitwidget.parent
        if graph is None:
            return

        # build label text
        fmt = self.labelFormatCombo.currentText()
        values = s.values
        errors = s.paramErrors
        chi2 = s.chi2
        dof = max(s.dof, 1)

        # equation with fitted values
        expr = s.function
        for name in sorted(values.keys(), key=len, reverse=True):
            expr = expr.replace(name, '%.4g' % values[name])

        # R²
        r2_text = ''
        try:
            data = self.fitwidget._findData()
            if data and data[0] is not None and data[1] is not None:
                xd = data[0].data
                yd = data[1].data
                minlen = min(len(xd), len(yd))
                xd, yd = xd[:minlen], yd[:minlen]
                mask = N.isfinite(xd) & N.isfinite(yd)
                yd_clean = yd[mask]

                evalenv = doc.evaluate.context.copy()
                compiled = doc.evaluate.compileCheckedExpression(
                    s.function)
                evalenv[s.variable] = xd[mask]
                evalenv.update(values)
                yfit = eval(compiled, evalenv) + xd[mask] * 0.

                ss_res = N.sum((yd_clean - yfit) ** 2)
                ss_tot = N.sum((yd_clean - N.mean(yd_clean)) ** 2)
                if ss_tot > 0:
                    r2 = 1.0 - ss_res / ss_tot
                    r2_text = 'r^{2} = %.4g' % r2
        except Exception:
            pass

        # assemble label parts
        parts = []
        if 'equation' in fmt:
            parts.append('y = %s' % expr)
        if 'R' in fmt and r2_text:
            parts.append(r2_text)
        if 'params' in fmt:
            for name in sorted(values.keys()):
                val = values[name]
                if name in errors and errors[name] > 0:
                    parts.append('%s = %.4g \\pm %.4g' % (
                        name, val, errors[name]))
                else:
                    parts.append('%s = %.4g' % (name, val))

        if not parts:
            return

        label_text = '\\\\'.join(parts)

        # reuse existing label or create new one
        label_name = 'fitresult_%s' % self.fitwidget.name
        label = graph.getChild(label_name)

        if label is None:
            # create new label
            doc.applyOperation(
                document.OperationWidgetAdd(
                    graph, 'label', autoadd=False,
                    name=label_name))
            label = graph.getChild(label_name)
            if label is None:
                return

            # set position only on first creation
            ops = [
                document.OperationSettingSet(
                    label.settings.get('xPos'), [0.05]),
                document.OperationSettingSet(
                    label.settings.get('yPos'), [0.95]),
                document.OperationSettingSet(
                    label.settings.get('alignVert'), 'top'),
                document.OperationSettingSet(
                    label.settings.get('alignHorz'), 'left'),
            ]
            doc.applyOperation(document.OperationMultiple(
                ops, descr=_('position fit label')))

        # always update the text
        doc.applyOperation(
            document.OperationSettingSet(
                label.settings.get('label'), label_text))

        # force graph update
        doc.setModified()
        doc.signalModified.emit(True)
        qt.QApplication.processEvents()
