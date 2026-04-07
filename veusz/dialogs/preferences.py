#    Copyright (C) 2006 Jeremy S. Sanders
#    Email: Jeremy Sanders <jeremy@jeremysanders.net>
#
#    This file is part of Veusz / Plotex.
#
#    Licenced under the GPL (version 2 or greater)
#
##############################################################################

"""Modern preferences dialog with sidebar navigation."""

from .. import qtall as qt
from .. import setting
from .. import utils
from .. import document

def _(text, disambiguation=None, context="PrefsDialog"):
    return qt.QCoreApplication.translate(context, text, disambiguation)

color_names = {
    'page': (_('Page'), _('Page background color')),
    'error': (_('Error'), _('Color for errors')),
    'command': (_('Console command'), _('Commands in the console window color')),
    'cntrlline': (_('Control line'), _('Color of lines controlling widgets')),
    'cntrlcorner': (_('Control corner'), _('Color of corners controlling widgets')),
}

color_schemes = [
    ('default', _('System default')),
    ('system-light', _('System light')),
    ('system-dark', _('System dark')),
    ('breeze-light', _('Breeze light')),
    ('breeze-dark', _('Breeze dark')),
    ('nord-light', _('Nord light')),
    ('nord-dark', _('Nord dark')),
    ('solarized-light', _('Solarized light')),
    ('solarized-dark', _('Solarized dark')),
    ('dracula', _('Dracula')),
    ('one-dark', _('One Dark')),
    ('material-dark', _('Material Dark')),
]

# available UI fonts
_ui_fonts = [
    '', 'Segoe UI', 'Inter', 'Roboto', 'Noto Sans', 'Source Sans Pro',
    'Open Sans', 'Lato', 'Arial', 'Helvetica', 'Calibri', 'Verdana',
    'Tahoma',
]


def _makeSection(title):
    """Create a styled section label."""
    lbl = qt.QLabel('<b>%s</b>' % title)
    lbl.setStyleSheet('font-size: 9pt; margin-top: 6px; margin-bottom: 2px;')
    return lbl


def _makeRow(label_text, widget, tooltip=None):
    """Create a horizontal layout with label + widget."""
    row = qt.QHBoxLayout()
    lbl = qt.QLabel(label_text)
    if tooltip:
        lbl.setToolTip(tooltip)
        widget.setToolTip(tooltip)
    lbl.setMinimumWidth(120)
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return row


class PreferencesDialog(qt.QDialog):
    """Modern preferences dialog with sidebar navigation."""

    def __init__(self, mainwindow):
        qt.QDialog.__init__(self, mainwindow)
        self.setWindowTitle(_('Preferences — Plotex'))
        self.resize(620, 460)
        self.setMinimumSize(550, 400)
        self.mainwindow = mainwindow
        self.plotwindow = mainwindow.plot
        self.setdb = setting.settingdb

        # main layout: sidebar + stacked content
        mainlayout = qt.QHBoxLayout(self)
        mainlayout.setContentsMargins(0, 0, 0, 0)
        mainlayout.setSpacing(0)

        # sidebar
        self.sidebar = qt.QListWidget()
        self.sidebar.setFixedWidth(130)
        self.sidebar.setIconSize(qt.QSize(20, 20))
        self.sidebar.setStyleSheet('''
            QListWidget {
                border: none;
                background: #2e3440;
                color: #d8dee9;
                font-size: 9pt;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-left: 3px solid transparent;
            }
            QListWidget::item:selected {
                background: #3b4252;
                border-left: 3px solid #88c0d0;
                color: #eceff4;
            }
            QListWidget::item:hover:!selected {
                background: #353d4a;
            }
        ''')

        # pages
        self.stack = qt.QStackedWidget()

        pages = [
            (_('Appearance'), 'settings_stylesheet', self._buildAppearancePage),
            (_('Display'), 'kde-view-refresh', self._buildDisplayPage),
            (_('Data'), 'kde-vzdata-import', self._buildDataPage),
            (_('Export'), 'kde-document-export', self._buildExportPage),
            (_('Plugins'), 'veusz-edit-custom', self._buildPluginsPage),
            (_('Advanced'), 'veusz-edit-prefs', self._buildAdvancedPage),
        ]

        for title, icon_name, builder in pages:
            item = qt.QListWidgetItem(utils.getIcon(icon_name), title)
            self.sidebar.addItem(item)
            self.stack.addWidget(builder())

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

        mainlayout.addWidget(self.sidebar)

        # right panel: stack + buttons
        rightpanel = qt.QVBoxLayout()
        rightpanel.setContentsMargins(8, 8, 8, 8)
        rightpanel.setSpacing(4)
        rightpanel.addWidget(self.stack, 1)

        # buttons
        btnlayout = qt.QHBoxLayout()
        btnlayout.addStretch()
        okbtn = qt.QPushButton(_('OK'))
        okbtn.setDefault(True)
        okbtn.clicked.connect(self.accept)
        cancelbtn = qt.QPushButton(_('Cancel'))
        cancelbtn.clicked.connect(self.reject)
        btnlayout.addWidget(okbtn)
        btnlayout.addWidget(cancelbtn)
        rightpanel.addLayout(btnlayout)
        mainlayout.addLayout(rightpanel, 1)

    # ---- Page Builders ----

    def _buildAppearancePage(self):
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)

        # Theme
        layout.addWidget(_makeSection(_('Theme')))
        self.colorSchemeCombo = qt.QComboBox()
        current = self.setdb['color_scheme']
        self._schemeIdx = 0
        for i, (name, usertext) in enumerate(color_schemes):
            self.colorSchemeCombo.addItem(usertext)
            if name == current:
                self._schemeIdx = i
        self.colorSchemeCombo.setCurrentIndex(self._schemeIdx)
        self.colorSchemeCombo.currentIndexChanged.connect(self._onColorSchemeChanged)
        layout.addLayout(_makeRow(_('Color scheme'), self.colorSchemeCombo))

        # Color theme for plots
        self.colorThemeDefCombo = qt.QComboBox()
        themes = sorted(list(document.colors.colorthemes))
        self.colorThemeDefCombo.addItems(themes)
        self.colorThemeDefCombo.setCurrentIndex(
            themes.index(self.setdb['colortheme_default']))
        layout.addLayout(_makeRow(_('Plot color theme'), self.colorThemeDefCombo,
            _('Default color theme for new plot elements')))

        # Font
        layout.addWidget(_makeSection(_('Font')))
        self.fontCombo = qt.QFontComboBox()
        currentfont = self.setdb.get('ui_font', '')
        if currentfont:
            self.fontCombo.setCurrentFont(qt.QFont(currentfont))
        layout.addLayout(_makeRow(_('UI font'), self.fontCombo,
            _('Font used for the application interface')))

        self.fontSizeSpin = qt.QSpinBox()
        self.fontSizeSpin.setRange(7, 16)
        self.fontSizeSpin.setValue(self.setdb.get('ui_font_size', 9))
        self.fontSizeSpin.setSuffix(' pt')
        layout.addLayout(_makeRow(_('Font size'), self.fontSizeSpin))

        stylerow = qt.QHBoxLayout()
        stylelbl = qt.QLabel(_('Font style'))
        stylelbl.setMinimumWidth(160)
        stylerow.addWidget(stylelbl)
        self.fontBoldCheck = qt.QCheckBox(_('Bold'))
        self.fontBoldCheck.setChecked(self.setdb.get('ui_font_bold', False))
        self.fontItalicCheck = qt.QCheckBox(_('Italic'))
        self.fontItalicCheck.setChecked(self.setdb.get('ui_font_italic', False))
        stylerow.addWidget(self.fontBoldCheck)
        stylerow.addWidget(self.fontItalicCheck)
        stylerow.addStretch()
        layout.addLayout(stylerow)

        # connect live preview for font changes
        self.fontCombo.currentFontChanged.connect(self._applyFontLive)
        self.fontSizeSpin.valueChanged.connect(self._applyFontLive)
        self.fontBoldCheck.toggled.connect(self._applyFontLive)
        self.fontItalicCheck.toggled.connect(self._applyFontLive)

        # Icons
        layout.addWidget(_makeSection(_('Toolbar')))
        self.iconSizeCombo = qt.QComboBox()
        for s in ('16', '20', '24', '32', '48'):
            self.iconSizeCombo.addItem(s)
        self.iconSizeCombo.setCurrentIndex(
            self.iconSizeCombo.findText(str(self.setdb['toolbar_size'])))
        layout.addLayout(_makeRow(_('Icon size'), self.iconSizeCombo))

        # UI colors
        layout.addWidget(_makeSection(_('UI Colors')))
        self.chosencolors = {}
        self.colorbutton = {}
        self.colordefaultcheck = {}
        for colname in self.setdb.colors:
            isdefault, colval = self.setdb['color_%s' % colname]
            self.chosencolors[colname] = qt.QColor(colval)
            name, tooltip = color_names[colname]

            row = qt.QHBoxLayout()
            lbl = qt.QLabel(name)
            lbl.setToolTip(tooltip)
            lbl.setMinimumWidth(120)
            row.addWidget(lbl)

            defcheck = qt.QCheckBox(_("Default"))
            self.colordefaultcheck[colname] = defcheck
            defcheck.setChecked(isdefault)
            row.addWidget(defcheck)

            button = qt.QPushButton()
            button.setFixedSize(28, 28)
            self.colorbutton[colname] = button
            def getcolclick(cn):
                return lambda: self._colorButtonClicked(cn)
            button.clicked.connect(getcolclick(colname))
            row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)

        self._updateButtonColors()
        layout.addStretch()
        return page

    def _buildDisplayPage(self):
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)

        layout.addWidget(_makeSection(_('Rendering')))
        self.antialiasCheck = qt.QCheckBox(_('Enable antialiasing'))
        self.antialiasCheck.setChecked(self.setdb['plot_antialias'])
        layout.addWidget(self.antialiasCheck)

        self.threadSpinBox = qt.QSpinBox()
        self.threadSpinBox.setRange(1, 16)
        self.threadSpinBox.setValue(self.setdb['plot_numthreads'])
        layout.addLayout(_makeRow(_('Render threads'), self.threadSpinBox))

        self.intervalCombo = qt.QComboBox()
        for intv in self.plotwindow.updateintervals:
            self.intervalCombo.addItem(intv[1])
        index = [i[0] for i in self.plotwindow.updateintervals].index(
            self.setdb['plot_updatepolicy'])
        self.intervalCombo.setCurrentIndex(index)
        layout.addLayout(_makeRow(_('Update policy'), self.intervalCombo))

        layout.addWidget(_makeSection(_('Picker')))
        self.pickerToConsoleCheck = qt.QCheckBox(_('Log to console'))
        self.pickerToConsoleCheck.setChecked(self.setdb['picker_to_console'])
        layout.addWidget(self.pickerToConsoleCheck)

        self.pickerToClipboardCheck = qt.QCheckBox(_('Copy to clipboard'))
        self.pickerToClipboardCheck.setChecked(self.setdb['picker_to_clipboard'])
        layout.addWidget(self.pickerToClipboardCheck)

        self.pickerSigFigs = qt.QSpinBox()
        self.pickerSigFigs.setRange(1, 15)
        self.pickerSigFigs.setValue(self.setdb['picker_sig_figs'])
        layout.addLayout(_makeRow(_('Significant figures'), self.pickerSigFigs))

        # Canvas helpers
        layout.addWidget(_makeSection(_('Canvas')))

        self.rulersDefaultCheck = qt.QCheckBox(_('Show rulers by default'))
        self.rulersDefaultCheck.setChecked(self.setdb.get('rulers_default', False))
        layout.addWidget(self.rulersDefaultCheck)

        self.rulersUnitCombo = qt.QComboBox()
        for unit in ('cm', 'in', 'mm'):
            self.rulersUnitCombo.addItem(unit)
        current_unit = self.setdb.get('rulers_unit', 'cm')
        idx = self.rulersUnitCombo.findText(current_unit)
        if idx >= 0:
            self.rulersUnitCombo.setCurrentIndex(idx)
        layout.addLayout(_makeRow(_('Ruler units'), self.rulersUnitCombo))

        self.snapEnabledCheck = qt.QCheckBox(_('Snap to guides'))
        self.snapEnabledCheck.setChecked(self.setdb.get('guides_snap_enabled', True))
        layout.addWidget(self.snapEnabledCheck)

        self.snapThresholdSpin = qt.QSpinBox()
        self.snapThresholdSpin.setRange(2, 20)
        self.snapThresholdSpin.setSuffix(' px')
        self.snapThresholdSpin.setValue(self.setdb.get('guides_snap_threshold', 8))
        layout.addLayout(_makeRow(_('Snap threshold'), self.snapThresholdSpin))

        layout.addStretch()
        return page

    def _buildDataPage(self):
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)

        layout.addWidget(_makeSection(_('File Directories')))
        self.dirDocCWDRadio = qt.QRadioButton(_('Use current working directory'))
        self.dirDocPrevRadio = qt.QRadioButton(_('Use previous directory'))
        (self.dirDocCWDRadio if self.setdb['dirname_usecwd']
            else self.dirDocPrevRadio).setChecked(True)
        layout.addWidget(self.dirDocPrevRadio)
        layout.addWidget(self.dirDocCWDRadio)

        self.docFileAddImportPaths = qt.QCheckBox(_('Add document path to import paths'))
        self.docFileAddImportPaths.setChecked(self.setdb['docfile_addimportpaths'])
        layout.addWidget(self.docFileAddImportPaths)

        layout.addWidget(_makeSection(_('New Documents')))
        self.styleLineEdit = qt.QLineEdit(self.setdb['stylesheet_default'])
        layout.addLayout(_makeRow(_('Default stylesheet'), self.styleLineEdit))

        self.customLineEdit = qt.QLineEdit(self.setdb['custom_default'])
        layout.addLayout(_makeRow(_('Custom definitions'), self.customLineEdit))

        layout.addWidget(_makeSection(_('Security')))
        self.securityDirList = qt.QListWidget()
        self.securityDirList.addItems(self.setdb['secure_dirs'])
        layout.addWidget(self.securityDirList)
        secrow = qt.QHBoxLayout()
        self.securityDirAdd = qt.QPushButton(_('Add…'))
        self.securityDirAdd.clicked.connect(self._securityDirAddClicked)
        self.securityDirRemove = qt.QPushButton(_('Remove'))
        self.securityDirRemove.clicked.connect(self._securityDirRemoveClicked)
        self.securityDirRemove.setEnabled(False)
        self.securityDirList.itemSelectionChanged.connect(
            lambda: self.securityDirRemove.setEnabled(
                len(self.securityDirList.selectedItems()) > 0))
        secrow.addWidget(self.securityDirAdd)
        secrow.addWidget(self.securityDirRemove)
        secrow.addStretch()
        layout.addLayout(secrow)

        layout.addStretch()
        return page

    def _buildExportPage(self):
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)

        layout.addWidget(_makeSection(_('Export Directory')))
        self.dirExportDocRadio = qt.QRadioButton(_('Same as document'))
        self.dirExportCWDRadio = qt.QRadioButton(_('Current working directory'))
        self.dirExportPrevRadio = qt.QRadioButton(_('Previous export directory'))
        {
            'doc': self.dirExportDocRadio,
            'cwd': self.dirExportCWDRadio,
            'prev': self.dirExportPrevRadio,
        }[self.setdb.get('dirname_export_location', 'doc')].setChecked(True)
        layout.addWidget(self.dirExportDocRadio)
        layout.addWidget(self.dirExportCWDRadio)
        layout.addWidget(self.dirExportPrevRadio)

        layout.addWidget(_makeSection(_('File Name Templates')))
        self.exportTemplSingleEdit = qt.QLineEdit(self.setdb['export_template_single'])
        layout.addLayout(_makeRow(_('Single page'), self.exportTemplSingleEdit,
            _('%DOCNAME% is replaced by document name')))

        self.exportTemplMultiEdit = qt.QLineEdit(self.setdb['export_template_multi'])
        layout.addLayout(_makeRow(_('Multi page'), self.exportTemplMultiEdit,
            _('%DOCNAME% and %PAGE00% are replaced')))

        # Copy as Image settings
        layout.addWidget(_makeSection(_('Copy as Image')))

        self.copyImageDpiSpin = qt.QSpinBox()
        self.copyImageDpiSpin.setRange(50, 1200)
        self.copyImageDpiSpin.setSuffix(' dpi')
        self.copyImageDpiSpin.setValue(self.setdb['copyimage_dpi'])
        layout.addLayout(_makeRow(_('Resolution'), self.copyImageDpiSpin))

        self.copyImageQualitySpin = qt.QSpinBox()
        self.copyImageQualitySpin.setRange(1, 100)
        self.copyImageQualitySpin.setSuffix(' %')
        self.copyImageQualitySpin.setValue(self.setdb['copyimage_quality'])
        layout.addLayout(_makeRow(_('JPEG quality'), self.copyImageQualitySpin))

        self.copyImageFormatCombo = qt.QComboBox()
        fmt_items = [
            ('png', 'PNG'), ('svg', 'SVG'), ('bmp', 'BMP'),
            ('jpg', 'JPEG'), ('emf', 'EMF'),
        ]
        current = self.setdb.get('copyimage_format', 'png')
        for i, (key, label) in enumerate(fmt_items):
            self.copyImageFormatCombo.addItem(label, key)
            if key == current:
                self.copyImageFormatCombo.setCurrentIndex(i)
        layout.addLayout(_makeRow(_('Format'), self.copyImageFormatCombo))

        layout.addStretch()
        return page

    def _buildPluginsPage(self):
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)

        layout.addWidget(_makeSection(_('Loaded Plugins')))
        plugins = list(self.setdb.get('plugins', []))
        self.pluginmodel = qt.QStringListModel(plugins)
        self.pluginList = qt.QListView()
        self.pluginList.setModel(self.pluginmodel)
        layout.addWidget(self.pluginList, 1)

        btnrow = qt.QHBoxLayout()
        addbtn = qt.QPushButton(_('Add…'))
        addbtn.clicked.connect(self._pluginAddClicked)
        rmbtn = qt.QPushButton(_('Remove'))
        rmbtn.clicked.connect(self._pluginRemoveClicked)
        btnrow.addWidget(addbtn)
        btnrow.addWidget(rmbtn)
        btnrow.addStretch()
        layout.addLayout(btnrow)

        layout.addStretch()
        return page

    def _buildAdvancedPage(self):
        page = qt.QWidget()
        layout = qt.QVBoxLayout(page)

        layout.addWidget(_makeSection(_('Language')))
        self.englishCheck = qt.QCheckBox(_('Force English for UI formatting'))
        self.englishCheck.setChecked(self.setdb['ui_english'])
        layout.addWidget(self.englishCheck)

        self.translationEdit = qt.QLineEdit(self.setdb['translation_file'])
        layout.addLayout(_makeRow(_('Translation file'), self.translationEdit))

        layout.addWidget(_makeSection(_('External Tools')))
        self.externalPythonPath = qt.QLineEdit(self.setdb['external_pythonpath'])
        layout.addLayout(_makeRow(_('Python path'), self.externalPythonPath,
            _('Additional directories for Python imports (colon-separated)')))

        self.externalGhostscript = qt.QLineEdit(self.setdb['external_ghostscript'])
        layout.addLayout(_makeRow(_('Ghostscript'), self.externalGhostscript,
            _('Path to Ghostscript executable (leave empty to auto-detect)')))

        layout.addWidget(_makeSection(_('Updates & Feedback')))
        self.externalNewVerCheck = qt.QCheckBox(_('Disable version checks'))
        self.externalNewVerCheck.setChecked(self.setdb['vercheck_disabled'])
        if utils.disableVersionChecks:
            self.externalNewVerCheck.setEnabled(False)
        layout.addWidget(self.externalNewVerCheck)

        self.externalFeedbackCheck = qt.QCheckBox(_('Disable anonymous feedback'))
        self.externalFeedbackCheck.setChecked(self.setdb['feedback_disabled'])
        if utils.disableFeedback:
            self.externalFeedbackCheck.setEnabled(False)
        layout.addWidget(self.externalFeedbackCheck)

        layout.addStretch()
        return page

    # ---- Actions ----

    def _applyFontLive(self, *args):
        """Apply font change immediately."""
        app = qt.QApplication.instance()
        font = qt.QFont(self.fontCombo.currentFont().family())
        font.setPointSize(self.fontSizeSpin.value())
        font.setBold(self.fontBoldCheck.isChecked())
        font.setItalic(self.fontItalicCheck.isChecked())
        app.setFont(font)

    def _onColorSchemeChanged(self, idx):
        scheme_name = color_schemes[idx][0]
        self.setdb['color_scheme'] = scheme_name
        app = qt.QApplication.instance()
        if hasattr(app, 'applyColorScheme'):
            app.applyColorScheme(scheme_name)

    def _colorButtonClicked(self, cname):
        retcolor = setting.controls._getColor(self.chosencolors[cname], self)
        if retcolor.isValid():
            self.chosencolors[cname] = retcolor
            self._updateButtonColors()

    def _updateButtonColors(self):
        for name, val in self.chosencolors.items():
            pixmap = qt.QPixmap(24, 24)
            pixmap.fill(val)
            self.colorbutton[name].setIcon(qt.QIcon(pixmap))

    def _pluginAddClicked(self):
        filename, _filt = qt.QFileDialog.getOpenFileName(
            self, _('Choose plugin'), '', _('Python scripts (*.py)'))
        if filename:
            self.pluginmodel.insertRows(0, 1)
            self.pluginmodel.setData(self.pluginmodel.index(0), filename)

    def _pluginRemoveClicked(self):
        sel = self.pluginList.selectionModel().currentIndex()
        if sel.isValid():
            self.pluginmodel.removeRow(sel.row())

    def _securityDirAddClicked(self):
        dirname = qt.QFileDialog.getExistingDirectory(
            self, _('Choose secure directory'))
        if dirname:
            self.securityDirList.addItem(dirname)

    def _securityDirRemoveClicked(self):
        for item in self.securityDirList.selectedItems():
            self.securityDirList.takeItem(self.securityDirList.row(item))

    def accept(self):
        """Save all settings."""
        setdb = self.setdb

        # Appearance
        idx = self.colorSchemeCombo.currentIndex()
        setdb['color_scheme'] = color_schemes[idx][0]
        setdb['colortheme_default'] = self.colorThemeDefCombo.currentText()

        # Font
        setdb['ui_font'] = self.fontCombo.currentFont().family()
        setdb['ui_font_size'] = self.fontSizeSpin.value()
        setdb['ui_font_bold'] = self.fontBoldCheck.isChecked()
        setdb['ui_font_italic'] = self.fontItalicCheck.isChecked()

        # Icon size
        iconsize = int(self.iconSizeCombo.currentText())
        if iconsize != setdb['toolbar_size']:
            setdb['toolbar_size'] = iconsize
            if hasattr(self.mainwindow, 'ribbon'):
                self.mainwindow.ribbon.setIconSize(iconsize)

        # UI colors
        for name, color in self.chosencolors.items():
            isdefault = self.colordefaultcheck[name].isChecked()
            setdb['color_' + name] = (isdefault, color.name())

        # Display
        setdb['plot_antialias'] = self.antialiasCheck.isChecked()
        setdb['plot_numthreads'] = self.threadSpinBox.value()
        setdb['plot_updatepolicy'] = (
            self.plotwindow.updateintervals[
                self.intervalCombo.currentIndex()][0])
        setdb['picker_to_console'] = self.pickerToConsoleCheck.isChecked()
        setdb['picker_to_clipboard'] = self.pickerToClipboardCheck.isChecked()
        setdb['picker_sig_figs'] = self.pickerSigFigs.value()

        # Canvas
        setdb['rulers_default'] = self.rulersDefaultCheck.isChecked()
        setdb['rulers_unit'] = self.rulersUnitCombo.currentText()
        setdb['guides_snap_enabled'] = self.snapEnabledCheck.isChecked()
        setdb['guides_snap_threshold'] = self.snapThresholdSpin.value()

        # Data
        setdb['dirname_usecwd'] = self.dirDocCWDRadio.isChecked()
        setdb['docfile_addimportpaths'] = self.docFileAddImportPaths.isChecked()
        setdb['stylesheet_default'] = self.styleLineEdit.text()
        setdb['custom_default'] = self.customLineEdit.text()
        setdb['secure_dirs'] = [
            self.securityDirList.item(i).text()
            for i in range(self.securityDirList.count())
        ]

        # Export
        for radio, val in (
                (self.dirExportDocRadio, 'doc'),
                (self.dirExportCWDRadio, 'cwd'),
                (self.dirExportPrevRadio, 'prev'),
        ):
            if radio.isChecked():
                setdb['dirname_export_location'] = val
        setdb['export_template_single'] = self.exportTemplSingleEdit.text().strip()
        setdb['export_template_multi'] = self.exportTemplMultiEdit.text().strip()

        # Copy as Image
        setdb['copyimage_dpi'] = self.copyImageDpiSpin.value()
        setdb['copyimage_quality'] = self.copyImageQualitySpin.value()
        setdb['copyimage_format'] = self.copyImageFormatCombo.currentData()

        # Plugins
        setdb['plugins'] = self.pluginmodel.stringList()

        # Advanced
        setdb['ui_english'] = self.englishCheck.isChecked()
        setdb['translation_file'] = self.translationEdit.text()
        setdb['external_pythonpath'] = self.externalPythonPath.text()
        setdb['external_ghostscript'] = self.externalGhostscript.text()
        setdb['vercheck_disabled'] = self.externalNewVerCheck.isChecked()
        setdb['feedback_disabled'] = self.externalFeedbackCheck.isChecked()

        self.plotwindow.updatePlotSettings()
        setdb.writeSettings()

        qt.QDialog.accept(self)
