#    Copyright (C) 2014 Jeremy S. Sanders
#    Copyright (C) 2026 M. Ignacio Monge García (modernized dialog)
#
#    This file is part of Veusz / Plotex.
#
#    Veusz is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
##############################################################################

"""Modernized export dialog for Plotex.

Features:
 - Presets (Publication, Web, Presentation)
 - Live preview thumbnail
 - Output dimensions display
 - Copy to clipboard
 - Clean two-column layout
"""

import os

from .. import qtall as qt
from .. import setting
from .. import utils
from .. import document


def _(text, disambiguation=None, context="ExportDialog", n=-1):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation, n)


# formats which can have multiple pages
multipageformats = set(("ps", "pdf"))
bitmapformats = set(("png", "bmp", "jpg", "tiff", "xpm", "webp"))

# ── Helpers ──────────────────────────────────────────────────────


def _makeSection(text):
    """Create a styled section header label."""
    lbl = qt.QLabel(text)
    lbl.setStyleSheet(
        "font-weight: 600; font-size: 10pt; color: palette(text); margin-top: 6px;"
    )
    return lbl


def _makeRow(label_text, widget, tooltip=None):
    """Label + widget in a horizontal layout."""
    row = qt.QHBoxLayout()
    lbl = qt.QLabel(label_text)
    lbl.setMinimumWidth(90)
    if tooltip:
        lbl.setToolTip(tooltip)
        widget.setToolTip(tooltip)
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return row


# ── Dialog ───────────────────────────────────────────────────────


class ExportDialog(qt.QDialog):
    """Modern export dialog."""

    dialogFinished = qt.pyqtSignal(qt.QDialog)

    def __init__(self, mainwindow, doc, docfilename):
        flag = (
            qt.Qt.WindowType.Dialog
            | qt.Qt.WindowType.CustomizeWindowHint
            | qt.Qt.WindowType.WindowCloseButtonHint
            | qt.Qt.WindowType.WindowTitleHint
        )
        qt.QDialog.__init__(self, mainwindow, flag)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

        self.setWindowTitle(_("Export — Plotex"))
        self.resize(660, 540)
        self.setMinimumSize(580, 440)

        self.mainwindow = mainwindow
        self.document = doc
        self.setdb = setting.settingdb
        doc.signalModified.connect(self._onDocModified)

        if not docfilename:
            docfilename = "export"
        self.docname = os.path.splitext(os.path.basename(docfilename))[0]

        # determine export directory
        # always prefer last used directory if available
        last_dir = self.setdb.get("dirname_export", "")
        if last_dir and os.path.isdir(last_dir):
            self.dirname = last_dir
        else:
            eloc = self.setdb["dirname_export_location"]
            if eloc == "doc":
                self.dirname = os.path.dirname(os.path.abspath(docfilename))
            elif eloc == "cwd":
                self.dirname = os.getcwd()
            else:
                self.dirname = qt.QDir.homePath()

        # get available formats
        self.docfmts = set()
        for types, descr in document.AsyncExport.getFormats():
            self.docfmts.update(types)

        self.formatselected = self.setdb.get("export_format", "pdf")
        self.pageselected = self.setdb.get("export_page", "single")

        self._buildUI()
        self._connectSignals()
        self._loadSettings()
        self._updateFormatVisibility()
        self._updatePreview()
        self._updateDimensions()

    # ── Build UI ─────────────────────────────────────────────

    def _buildUI(self):
        mainlayout = qt.QVBoxLayout(self)
        mainlayout.setSpacing(8)

        # ── Presets ──────────────────────────────────────────
        presets = qt.QHBoxLayout()
        presets.addWidget(qt.QLabel(_("Quick:")))
        self.btnPublication = qt.QPushButton(_("Publication"))
        self.btnWeb = qt.QPushButton(_("Web"))
        self.btnPresentation = qt.QPushButton(_("Presentation"))
        for btn in (self.btnPublication, self.btnWeb, self.btnPresentation):
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setStyleSheet(
                "QPushButton { padding: 4px 14px; }"
                "QPushButton:checked { "
                "  background: palette(highlight); "
                "  color: palette(highlighted-text); }"
            )
            presets.addWidget(btn)
        presets.addStretch(1)
        mainlayout.addLayout(presets)

        # ── Two columns ─────────────────────────────────────
        columns = qt.QHBoxLayout()
        left = qt.QVBoxLayout()
        left.setSpacing(4)
        right = qt.QVBoxLayout()
        right.setSpacing(6)

        # ── Filename ─────────────────────────────────────────
        left.addWidget(_makeSection(_("Filename")))
        filerow = qt.QHBoxLayout()
        self.editFileName = qt.QLineEdit()
        self.editFileName.setToolTip(
            _("Use %PAGE%, %PAGE00%, %PAGE000%, %PAGENAME% for multi-file export")
        )
        self.buttonBrowse = qt.QPushButton(_("Browse…"))
        filerow.addWidget(self.editFileName, 1)
        filerow.addWidget(self.buttonBrowse)
        left.addLayout(filerow)

        # ── Format ───────────────────────────────────────────
        left.addWidget(_makeSection(_("Format")))
        self.fmtGroup = qt.QButtonGroup(self)
        self.fmtGroup.setExclusive(True)
        self.fmtButtons = {}

        fmtgrid = qt.QGridLayout()
        fmtgrid.setSpacing(2)
        fmtgrid.addWidget(qt.QLabel(_("Vector:")), 0, 0)
        fmtgrid.addWidget(qt.QLabel(_("Bitmap:")), 1, 0)

        vector_fmts = [
            ("pdf", "PDF"),
            ("eps", "EPS"),
            ("ps", "PS"),
            ("svg", "SVG"),
            ("emf", "EMF"),
        ]
        bitmap_fmts = [
            ("png", "PNG"),
            ("bmp", "BMP"),
            ("jpg", "JPG"),
            ("tiff", "TIFF"),
            ("xpm", "XPM"),
            ("webp", "WebP"),
        ]

        for col, (fmt, label) in enumerate(vector_fmts):
            btn = qt.QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(44)
            btn.setEnabled(fmt in self.docfmts)
            self.fmtGroup.addButton(btn)
            self.fmtButtons[fmt] = btn
            fmtgrid.addWidget(btn, 0, col + 1)

        for col, (fmt, label) in enumerate(bitmap_fmts):
            btn = qt.QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(44)
            btn.setEnabled(fmt in self.docfmts)
            self.fmtGroup.addButton(btn)
            self.fmtButtons[fmt] = btn
            fmtgrid.addWidget(btn, 1, col + 1)

        left.addLayout(fmtgrid)

        # ── Pages ────────────────────────────────────────────
        left.addWidget(_makeSection(_("Pages")))
        self.radioPageSingle = qt.QRadioButton(_("Current page"))
        self.radioPageAll = qt.QRadioButton(_("All pages"))
        pagesrow = qt.QHBoxLayout()
        self.radioPagePages = qt.QRadioButton(_("Pages:"))
        self.editPagePages = qt.QLineEdit()
        self.editPagePages.setFixedWidth(100)
        valre = qt.QRegularExpression(
            r"^[0-9]+(\s*-\s*[0-9]+)?"
            r"(\s*,\s*[0-9]+(\s*-\s*[0-9]+)?)*$"
        )
        self.editPagePages.setValidator(qt.QRegularExpressionValidator(valre, self))
        pagesrow.addWidget(self.radioPagePages)
        pagesrow.addWidget(self.editPagePages)
        pagesrow.addStretch(1)

        self.checkMultiPage = qt.QCheckBox(_("Multiple pages in one file"))

        left.addWidget(self.radioPageSingle)
        left.addWidget(self.radioPageAll)
        left.addLayout(pagesrow)
        left.addWidget(self.checkMultiPage)

        # ── Options ──────────────────────────────────────────
        left.addWidget(_makeSection(_("Options")))

        # DPI combos
        dpis = ("72", "75", "90", "96", "100", "150", "200", "300", "600")
        dpi_validator = qt.QIntValidator(10, 10000, self)

        self.exportDPI = qt.QComboBox()
        self.exportDPI.setEditable(True)
        self.exportDPI.addItems(dpis)
        self.exportDPI.setValidator(dpi_validator)
        self.rowDPI = _makeRow(_("DPI:"), self.exportDPI)

        self.exportDPIPDF = qt.QComboBox()
        self.exportDPIPDF.setEditable(True)
        self.exportDPIPDF.addItems(dpis)
        self.exportDPIPDF.setValidator(dpi_validator)
        self.rowDPIPDF = _makeRow(_("PDF DPI:"), self.exportDPIPDF)

        self.exportDPISVG = qt.QComboBox()
        self.exportDPISVG.setEditable(True)
        self.exportDPISVG.addItems(dpis)
        self.exportDPISVG.setValidator(dpi_validator)
        self.rowDPISVG = _makeRow(_("SVG DPI:"), self.exportDPISVG)

        self.exportAntialias = qt.QCheckBox(_("Antialiasing"))
        self.exportQuality = qt.QSpinBox()
        self.exportQuality.setRange(0, 100)
        self.rowQuality = _makeRow(_("Quality:"), self.exportQuality)

        self.exportBackgroundButton = qt.QPushButton()
        self.exportBackgroundButton.setFixedWidth(60)
        self.rowBackground = _makeRow(_("Background:"), self.exportBackgroundButton)

        self.exportColor = qt.QComboBox()
        self.exportColor.addItems([_("Color"), _("Greyscale")])
        self.rowColor = _makeRow(_("Color:"), self.exportColor)

        self.exportSVGTextAsText = qt.QCheckBox(_("Text as text"))
        self.rowSVGText = _makeRow(_("SVG:"), self.exportSVGTextAsText)

        self.checkOverwrite = qt.QCheckBox(_("Overwrite without asking"))

        # gather all option rows
        self._optRows = {
            "dpi": self.rowDPI,
            "dpipdf": self.rowDPIPDF,
            "dpisvg": self.rowDPISVG,
            "quality": self.rowQuality,
            "background": self.rowBackground,
            "color": self.rowColor,
            "svgtext": self.rowSVGText,
        }

        left.addLayout(self.rowDPI)
        left.addWidget(self.exportAntialias)
        left.addLayout(self.rowBackground)
        left.addLayout(self.rowQuality)
        left.addLayout(self.rowDPIPDF)
        left.addLayout(self.rowColor)
        left.addLayout(self.rowDPISVG)
        left.addLayout(self.rowSVGText)
        left.addWidget(self.checkOverwrite)

        left.addStretch(1)

        # ── Right column: preview + dimensions ───────────────
        self.previewLabel = qt.QLabel()
        self.previewLabel.setFixedSize(200, 200)
        self.previewLabel.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.previewLabel.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        right.addWidget(self.previewLabel)

        self.dimLabel = qt.QLabel()
        self.dimLabel.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.dimLabel.setStyleSheet("color: #666; font-size: 9pt;")
        right.addWidget(self.dimLabel)

        right.addStretch(1)

        columns.addLayout(left, 1)
        columns.addLayout(right, 0)
        mainlayout.addLayout(columns, 1)

        # ── Bottom bar ───────────────────────────────────────
        sep = qt.QFrame()
        sep.setFrameShape(qt.QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ccc;")
        mainlayout.addWidget(sep)

        bottombar = qt.QHBoxLayout()

        self.labelStatus = qt.QLabel()
        self.labelStatus.setStyleSheet("color: #666;")
        bottombar.addWidget(self.labelStatus, 1)

        self.progressBar = qt.QProgressBar()
        self.progressBar.setRange(0, 0)
        self.progressBar.setFixedWidth(120)
        self.progressBar.hide()
        bottombar.addWidget(self.progressBar)

        self.btnClipboard = qt.QPushButton(_("Clipboard"))
        self.btnClipboard.setToolTip(_("Copy current page to clipboard as image"))
        bottombar.addWidget(self.btnClipboard)

        self.btnExport = qt.QPushButton(_("Export"))
        self.btnExport.setDefault(True)
        bottombar.addWidget(self.btnExport)

        self.btnClose = qt.QPushButton(_("Close"))
        bottombar.addWidget(self.btnClose)

        mainlayout.addLayout(bottombar)

    # ── Connect signals ──────────────────────────────────────

    def _connectSignals(self):
        self.buttonBrowse.clicked.connect(self._browseClicked)
        self.btnExport.clicked.connect(self._doExport)
        self.btnClose.clicked.connect(self.close)
        self.btnClipboard.clicked.connect(self._copyToClipboard)

        self.btnPublication.clicked.connect(lambda: self._applyPreset("publication"))
        self.btnWeb.clicked.connect(lambda: self._applyPreset("web"))
        self.btnPresentation.clicked.connect(lambda: self._applyPreset("presentation"))

        for fmt, btn in self.fmtButtons.items():
            btn.clicked.connect(lambda checked, f=fmt: self._formatClicked(f))

        self.radioPageSingle.clicked.connect(lambda: self._pageClicked("single"))
        self.radioPageAll.clicked.connect(lambda: self._pageClicked("all"))
        self.radioPagePages.clicked.connect(lambda: self._pageClicked("pages"))

        self.checkMultiPage.clicked.connect(self._updateSingleMulti)
        self.exportBackgroundButton.clicked.connect(self._backgroundClicked)

        # update dimensions when DPI changes
        for combo in (self.exportDPI, self.exportDPIPDF, self.exportDPISVG):
            combo.currentTextChanged.connect(self._updateDimensions)

    # ── Load settings ────────────────────────────────────────

    def _loadSettings(self):
        s = self.setdb

        # block signals on widgets during bulk-load to prevent recursive
        # updates (setChecked/setEditText would otherwise fire slots that
        # call _loadSettings-related helpers again)
        widgets = (
            self.checkMultiPage,
            self.checkOverwrite,
            self.exportAntialias,
            self.exportQuality,
            self.exportDPI,
            self.exportDPIPDF,
            self.exportDPISVG,
            self.exportSVGTextAsText,
            self.exportColor,
        )
        prev = [w.blockSignals(True) for w in widgets]
        try:
            self.checkMultiPage.setChecked(s.get("export_multipage", True))
            self.checkOverwrite.setChecked(s.get("export_overwrite", False))
            self.exportAntialias.setChecked(s["export_antialias"])
            self.exportQuality.setValue(s["export_quality"])
            self.exportDPI.setEditText(str(s["export_DPI"]))
            self.exportDPIPDF.setEditText(str(s["export_DPI_PDF2"]))
            self.exportDPISVG.setEditText(str(s["export_DPI_SVG"]))
            self.exportSVGTextAsText.setChecked(s["export_SVG_text_as_text"])
            self.exportColor.setCurrentIndex(0 if s["export_color"] else 1)
        finally:
            for w, st in zip(widgets, prev):
                w.blockSignals(st)

        self._updateExportBackground(s["export_background"])

        # select format
        fmt = self.formatselected
        if fmt in self.fmtButtons:
            self.fmtButtons[fmt].setChecked(True)
        self._formatClicked(fmt)

        # select page mode
        {
            "single": self.radioPageSingle,
            "all": self.radioPageAll,
            "pages": self.radioPagePages,
            "range": self.radioPageSingle,
        }.get(self.pageselected, self.radioPageSingle).setChecked(True)
        self._pageClicked(self.pageselected)

        self._updatePagePages()
        self._updateSingleMulti()

    # ── Format handling ──────────────────────────────────────

    def _formatClicked(self, fmt):
        self.setdb["export_format"] = fmt
        self.formatselected = fmt
        self.checkMultiPage.setEnabled(fmt in multipageformats)
        self._updateFormatVisibility()
        self._updateSingleMulti()
        self._updateDimensions()

        # update filename extension
        fname = self.editFileName.text()
        if fname:
            fname = os.path.splitext(fname)[0] + "." + fmt
            self.editFileName.setText(fname)

    def _updateFormatVisibility(self):
        fmt = self.formatselected
        is_bmp = fmt in bitmapformats
        is_pdf = fmt in ("pdf", "ps", "eps")
        is_svg = fmt == "svg"
        is_quality = fmt in ("jpg", "webp")

        self._setRowVisible(self.rowDPI, is_bmp)
        self.exportAntialias.setVisible(is_bmp)
        self._setRowVisible(self.rowBackground, is_bmp)
        self._setRowVisible(self.rowQuality, is_quality)
        self._setRowVisible(self.rowDPIPDF, is_pdf)
        self._setRowVisible(self.rowColor, is_pdf)
        self._setRowVisible(self.rowDPISVG, is_svg)
        self._setRowVisible(self.rowSVGText, is_svg)

    def _setRowVisible(self, layout, visible):
        """Show/hide all widgets in a QHBoxLayout."""
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w:
                w.setVisible(visible)

    # ── Page handling ────────────────────────────────────────

    def _pageClicked(self, page):
        self.setdb["export_page"] = page
        self.pageselected = page
        self.editPagePages.setEnabled(page == "pages")
        self._updateSingleMulti()

    def _updatePagePages(self):
        npages = self.document.getNumberPages()
        if npages > 0:
            self.editPagePages.setText("1-%i" % npages)

    def _isMultiFile(self):
        multifile = self.pageselected != "single"
        if self.formatselected in multipageformats and self.checkMultiPage.isChecked():
            multifile = False
        return multifile

    def _updateSingleMulti(self):
        self.setdb["export_multipage"] = self.checkMultiPage.isChecked()
        multifile = self._isMultiFile()
        if multifile:
            templ = self.setdb["export_template_multi"]
        else:
            templ = self.setdb["export_template_single"]

        newfilename = os.path.join(
            self.dirname,
            templ.replace("%DOCNAME%", self.docname) + "." + self.formatselected,
        )

        if multifile is not getattr(self, "_oldmulti", None):
            self.editFileName.setText(newfilename)
            self._oldmulti = multifile

    # ── Presets ──────────────────────────────────────────────

    def _applyPreset(self, name):
        if name == "publication":
            self.fmtButtons["pdf"].setChecked(True)
            self._formatClicked("pdf")
            self.exportDPIPDF.setEditText("300")
        elif name == "web":
            self.fmtButtons["png"].setChecked(True)
            self._formatClicked("png")
            self.exportDPI.setEditText("150")
            self.exportAntialias.setChecked(True)
            self.exportQuality.setValue(85)
        elif name == "presentation":
            self.fmtButtons["svg"].setChecked(True)
            self._formatClicked("svg")
            self.exportDPISVG.setEditText("96")
            self.exportSVGTextAsText.setChecked(True)

    # ── Preview ──────────────────────────────────────────────

    def _updatePreview(self):
        """Render a small thumbnail of the current page."""
        try:
            pagenum = self.mainwindow.plot.getPageNumber()
            dpi = (72, 72)
            size = self.document.pageSize(pagenum, dpi=dpi)

            # scale to fit preview area
            maxdim = 190
            scale = min(maxdim / max(size[0], 1), maxdim / max(size[1], 1), 1.0)
            w = max(int(size[0] * scale), 1)
            h = max(int(size[1] * scale), 1)

            # use PaintHelper like the render thread does
            helper = document.PaintHelper(self.document, (w, h), scaling=scale, dpi=dpi)
            self.document.paintTo(helper, pagenum)

            img = qt.QImage(w, h, qt.QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(qt.QColor(255, 255, 255))

            painter = qt.QPainter(img)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(qt.QPainter.RenderHint.TextAntialiasing, True)
            helper.renderToPainter(painter)
            painter.end()

            pix = qt.QPixmap.fromImage(img)
            self.previewLabel.setPixmap(pix)
        except Exception:
            self.previewLabel.setText(_("Preview\nnot available"))

    def _updateDimensions(self):
        """Show output dimensions based on format and DPI."""
        try:
            pagenum = self.mainwindow.plot.getPageNumber()
            fmt = self.formatselected
            dpi = self._getEffectiveDPI()

            size = self.document.pageSize(pagenum, dpi=(dpi, dpi), integer=True)
            w_mm = size[0] / dpi * 25.4
            h_mm = size[1] / dpi * 25.4

            self.dimLabel.setText(
                "%d x %d px  (%d DPI)\n"
                "%.1f x %.1f mm" % (size[0], size[1], dpi, w_mm, h_mm)
            )
        except Exception:
            self.dimLabel.setText("")

    def _getEffectiveDPI(self):
        fmt = self.formatselected
        try:
            if fmt in bitmapformats:
                return int(self.exportDPI.currentText())
            elif fmt in ("pdf", "ps", "eps"):
                return int(self.exportDPIPDF.currentText())
            elif fmt == "svg":
                return int(self.exportDPISVG.currentText())
        except ValueError:
            pass
        return 150

    def _onDocModified(self):
        self._updatePreview()
        self._updateDimensions()
        self._updatePagePages()

    # ── Background color ─────────────────────────────────────

    def _updateExportBackground(self, colorname):
        pixmap = qt.QPixmap(16, 16)
        col = self.document.evaluate.colors.get(colorname)
        pixmap.fill(col)
        self.exportBackgroundButton.setIcon(qt.QIcon(pixmap))
        self.exportBackgroundButton.iconcolor = colorname

    def _backgroundClicked(self):
        qcolor = self.document.evaluate.colors.get(
            self.exportBackgroundButton.iconcolor
        )
        color = setting.controls._getColor(qcolor, self, _("Choose color"), alpha=True)
        if color.isValid():
            self._updateExportBackground(utils.extendedColorFromQColor(color))

    # ── Browse ───────────────────────────────────────────────

    def _browseClicked(self):
        fd = qt.QFileDialog(self, _("Export page"))
        dirname = os.path.dirname(self.editFileName.text())
        fd.setDirectory(dirname if dirname else self.dirname)
        fd.setFileMode(qt.QFileDialog.FileMode.AnyFile)
        fd.setAcceptMode(qt.QFileDialog.AcceptMode.AcceptSave)
        fd.setOptions(qt.QFileDialog.Option.DontConfirmOverwrite)

        filtertoext = {}
        exttofilter = {}
        filters = []
        validextns = []
        for extns, name in document.AsyncExport.getFormats():
            extensions = " ".join(["*." + e for e in extns])
            filterstr = "%s (%s)" % (name, extensions)
            filtertoext[filterstr] = extns
            for e in extns:
                exttofilter[e] = filterstr
            filters.append(filterstr)
            validextns += extns
        fd.setNameFilters(filters)

        if self.formatselected in exttofilter:
            fd.selectNameFilter(exttofilter[self.formatselected])

        filename = self.editFileName.text()
        dirname = os.path.dirname(os.path.abspath(filename))
        if os.path.isdir(dirname):
            fd.selectFile(filename)

        if fd.exec() == qt.QDialog.DialogCode.Accepted:
            filterused = str(fd.selectedNameFilter())
            chosenext = filtertoext[filterused][0]
            filename = fd.selectedFiles()[0]
            fileext = os.path.splitext(filename)[1][1:]
            if fileext not in validextns or fileext != chosenext:
                filename += "." + chosenext
            self.editFileName.setText(filename)
            if chosenext in self.fmtButtons:
                self.fmtButtons[chosenext].setChecked(True)
                self._formatClicked(chosenext)

    # ── Status ───────────────────────────────────────────────

    def _showMessage(self, text):
        self.labelStatus.setText(text)
        utils.safe_singleShot(4000, self, self.labelStatus.clear)

    # ── Page list ────────────────────────────────────────────

    def _getPagePages(self):
        visible = set(self.document.getVisiblePages())
        txt = self.editPagePages.text()
        pages = []
        for p in txt.split(","):
            p = p.strip()
            try:
                if "-" in p:
                    rng = p.split("-")
                    for pg in range(int(rng[0]) - 1, int(rng[1])):
                        if pg in visible:
                            pages.append(pg)
                else:
                    pg = int(p) - 1
                    if pg in visible:
                        pages.append(pg)
            except ValueError:
                raise RuntimeError(_("Error: invalid page range"))
        for pg in pages:
            if pg < 0 or pg >= self.document.getNumberPages():
                raise RuntimeError(_("Error: pages out of range"))
        return pages

    # ── Copy to clipboard ────────────────────────────────────

    def _copyToClipboard(self):
        """Export current page to clipboard as PNG."""
        try:
            pagenum = self.mainwindow.plot.getPageNumber()
            dpi_val = self._getEffectiveDPI()
            dpi = (dpi_val, dpi_val)
            size = self.document.pageSize(pagenum, dpi=dpi, integer=True)

            helper = document.PaintHelper(self.document, size, dpi=dpi)
            self.document.paintTo(helper, pagenum)

            img = qt.QImage(
                size[0], size[1], qt.QImage.Format.Format_ARGB32_Premultiplied
            )
            img.fill(qt.QColor(255, 255, 255))

            painter = qt.QPainter(img)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(qt.QPainter.RenderHint.TextAntialiasing, True)
            helper.renderToPainter(painter)
            painter.end()

            qt.QApplication.clipboard().setImage(img)
            self._showMessage(_("Copied to clipboard (%dx%d px)") % (size[0], size[1]))
        except Exception as e:
            self._showMessage(_("Error: %s") % str(e))

    # ── Export ───────────────────────────────────────────────

    def _doExport(self):
        """Main export action."""

        if not self.document.getVisiblePages():
            self._showMessage(_("Error: no visible pages"))
            return

        filename = self.editFileName.text()
        if (
            self._isMultiFile()
            and "%PAGENAME%" not in filename
            and "%PAGE%" not in filename
            and "%PAGE00%" not in filename
            and "%PAGE000%" not in filename
        ):
            self._showMessage(_("Error: multi-file needs %PAGE% or %PAGENAME% in name"))
            return

        if not os.path.splitext(filename)[1]:
            filename += "." + self.formatselected

        if self.pageselected == "single":
            pages = [self.mainwindow.plot.getPageNumber()]
        elif self.pageselected == "all":
            pages = self.document.getVisiblePages()
        elif self.pageselected == "pages":
            try:
                pages = self._getPagePages()
            except RuntimeError as e:
                self._showMessage(str(e))
                return

        s = self.setdb

        # save settings
        s["export_overwrite"] = self.checkOverwrite.isChecked()
        s["export_antialias"] = self.exportAntialias.isChecked()
        s["export_quality"] = self.exportQuality.value()
        s["export_color"] = self.exportColor.currentIndex() == 0
        s["export_background"] = self.exportBackgroundButton.iconcolor
        s["export_SVG_text_as_text"] = self.exportSVGTextAsText.isChecked()

        for combo, key in (
            (self.exportDPI, "export_DPI"),
            (self.exportDPIPDF, "export_DPI_PDF2"),
            (self.exportDPISVG, "export_DPI_SVG"),
        ):
            try:
                text = combo.currentText()
                valid = combo.validator().validate(text, 0)[0]
                if valid == qt.QValidator.State.Acceptable:
                    s[key] = int(text)
            except ValueError:
                pass

        export = document.AsyncExport(
            self.document,
            bitmapdpi=s["export_DPI"],
            pdfdpi=s["export_DPI_PDF2"],
            antialias=s["export_antialias"],
            color=s["export_color"],
            quality=s["export_quality"],
            backcolor=s["export_background"],
            svgtextastext=s["export_SVG_text_as_text"],
            svgdpi=s["export_DPI_SVG"],
        )

        def _overwriteQ(fn):
            r = qt.QMessageBox.question(
                self,
                _("Overwrite?"),
                _("'%s' exists. Overwrite?") % os.path.basename(fn),
                qt.QMessageBox.StandardButton.Save
                | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel,
            )
            return r == qt.QMessageBox.StandardButton.Save

        pagecount = [0]

        def _checkExport(fn, pgs):
            if os.path.exists(fn):
                if not s["export_overwrite"]:
                    if not _overwriteQ(fn):
                        return
            try:
                os.unlink(fn)
            except EnvironmentError:
                pass
            export.add(fn, pgs)
            pagecount[0] += len(pgs)
            ext = os.path.splitext(fn)[1]
            if ext:
                utils.feedback.exportcts[ext] += 1

        if self._isMultiFile() or len(pages) == 1:
            for page in pages:
                pagename = self.document.getPage(page).name
                pg = page + 1
                fname = filename.replace("%PAGE%", str(pg))
                fname = fname.replace("%PAGE00%", "%02i" % pg)
                fname = fname.replace("%PAGE000%", "%03i" % pg)
                fname = fname.replace("%PAGENAME%", pagename)
                _checkExport(fname, [page])
        else:
            fname = filename
            for tag in ("%PAGE%", "%PAGE00%", "%PAGE000%", "%PAGENAME%"):
                fname = fname.replace(tag, _("none"))
            _checkExport(fname, pages)

        dirname = os.path.dirname(filename)
        if dirname:
            s["dirname_export"] = dirname

        # progress
        self.progressBar.show()
        self.btnExport.setEnabled(False)
        self.btnClose.setEnabled(False)
        self._showMessage(_("Exporting…"))

        def checkDone():
            if not export.haveDone():
                return
            try:
                export.finish()
            except (RuntimeError, EnvironmentError) as e:
                msg = e.strerror if isinstance(e, EnvironmentError) else str(e)
                qt.QMessageBox.critical(
                    self,
                    _("Export error"),
                    _("Error exporting '%s'\n\n%s") % (fname, msg),
                )
            else:
                if pagecount[0] > 0:
                    self._showMessage(_("Exported %d page(s)") % pagecount[0])

            self.progressBar.hide()
            self.btnExport.setEnabled(True)
            self.btnClose.setEnabled(True)
            self.checktimer.stop()

        # Stop and tear down any previous checktimer before replacing it.
        # Without this, fast double-clicks of Export leave the old timer
        # active (the assignment below only drops the Python reference;
        # the QTimer remains parented to ``self`` and keeps firing
        # against a stale ``checkDone`` closure).
        old = getattr(self, "checktimer", None)
        if old is not None:
            try:
                old.stop()
                old.timeout.disconnect()
            except (RuntimeError, TypeError):
                pass
            old.deleteLater()

        self.checktimer = qt.QTimer(self)
        self.checktimer.timeout.connect(checkDone)
        self.checktimer.start(20)

    # ── Lifecycle ────────────────────────────────────────────

    def hideEvent(self, event):
        if not event.spontaneous():
            self.dialogFinished.emit(self)
        return qt.QDialog.hideEvent(self, event)
