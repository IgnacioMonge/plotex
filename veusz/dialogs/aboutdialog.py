# about dialog box — modern splash-style design
#
#    Copyright (C) 2006 Jeremy S. Sanders
#    Copyright (C) 2026 M. Ignacio Monge García
#
#    Licenced under the GPL (version 2 or greater)
#
##############################################################################

"""Modern about dialog matching splash screen aesthetic."""

import datetime
from .. import qtall as qt
from .. import utils
from .exceptiondialog import versionHeader

def _(text, disambiguation=None, context='AboutDialog'):
    return qt.QCoreApplication.translate(context, text, disambiguation)


class AboutDialog(qt.QDialog):
    """Modern about dialog with splash-screen style."""

    _radius = 16

    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self.setWindowFlags(
            qt.Qt.WindowType.Dialog |
            qt.Qt.WindowType.FramelessWindowHint)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(420)

        self._buildUI()

        # close on click anywhere
        self.setFocusPolicy(qt.Qt.FocusPolicy.ClickFocus)

    def paintEvent(self, event):
        p = qt.QPainter(self)
        p.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        p.setBrush(qt.QColor('#1a1a2e'))
        p.setPen(qt.QPen(qt.QColor('#2a2a4a'), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1),
                          self._radius, self._radius)
        p.end()

    def _buildUI(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 28)
        layout.setSpacing(0)

        # logo
        logo = qt.QLabel()
        pix = utils.getPixmap('plotex_logo.png')
        scaled = pix.scaled(
            120, 120,
            qt.Qt.AspectRatioMode.KeepAspectRatio,
            qt.Qt.TransformationMode.SmoothTransformation)
        logo.setPixmap(scaled)
        logo.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        layout.addSpacing(14)

        # app name
        title = qt.QLabel('Plotex')
        title.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #e0e0e0;"
            "font-size: 24px;"
            "font-weight: 600;"
            "letter-spacing: 5px;"
            "background: transparent;"
        )
        layout.addWidget(title)

        layout.addSpacing(4)

        # version
        ver = qt.QLabel('v%s' % utils.version())
        ver.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(
            "color: #6a6a8a;"
            "font-size: 12px;"
            "background: transparent;"
        )
        layout.addWidget(ver)

        layout.addSpacing(16)

        # separator
        sep = qt.QFrame()
        sep.setFrameShape(qt.QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2a2a4a; background: #2a2a4a; max-height: 1px;")
        layout.addWidget(sep)

        layout.addSpacing(14)

        # author
        author = qt.QLabel('M. Ignacio Monge Garc\u00eda')
        author.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        author.setStyleSheet(
            "color: #c0c0d8;"
            "font-size: 11px;"
            "background: transparent;"
        )
        layout.addWidget(author)

        layout.addSpacing(4)

        # credits
        credits = qt.QLabel(
            _('Based on Veusz by Jeremy Sanders'))
        credits.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        credits.setStyleSheet(
            "color: #5a5a7a;"
            "font-size: 10px;"
            "background: transparent;"
        )
        layout.addWidget(credits)

        layout.addSpacing(6)

        # build date
        builddate = qt.QLabel(
            _('Build: %s') % datetime.date.today().strftime('%Y-%m-%d'))
        builddate.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        builddate.setStyleSheet(
            "color: #4a4a6a;"
            "font-size: 9px;"
            "background: transparent;"
        )
        layout.addWidget(builddate)

        layout.addSpacing(4)

        # github link
        ghlink = qt.QLabel(
            '<a href="https://github.com/veusz/veusz"'
            ' style="color: #88c0d0; text-decoration: none;">'
            'github.com/veusz/veusz</a>')
        ghlink.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        ghlink.setOpenExternalLinks(True)
        ghlink.setStyleSheet(
            "font-size: 9px;"
            "background: transparent;"
        )
        layout.addWidget(ghlink)

        layout.addSpacing(12)

        # separator
        sep2 = qt.QFrame()
        sep2.setFrameShape(qt.QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #2a2a4a; background: #2a2a4a; max-height: 1px;")
        layout.addWidget(sep2)

        layout.addSpacing(8)

        # license
        lic = qt.QLabel(_('GNU General Public License v2+'))
        lic.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        lic.setStyleSheet(
            "color: #4a4a6a;"
            "font-size: 9px;"
            "background: transparent;"
        )
        layout.addWidget(lic)

        layout.addSpacing(16)

        # buttons row
        btnrow = qt.QHBoxLayout()
        btnrow.setSpacing(8)

        btnstyle = """
            QPushButton {
                background: #2a2a4a;
                color: #88c0d0;
                border: 1px solid #3a3a5a;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #3a3a5a;
                border-color: #88c0d0;
            }
            QPushButton:pressed {
                background: #4a4a6a;
            }
        """

        versbtn = qt.QPushButton(_('Versions'))
        versbtn.setStyleSheet(btnstyle)
        versbtn.clicked.connect(self._showVersions)
        btnrow.addWidget(versbtn)

        licbtn = qt.QPushButton(_('License'))
        licbtn.setStyleSheet(btnstyle)
        licbtn.clicked.connect(self._showLicense)
        btnrow.addWidget(licbtn)

        closestyle = """
            QPushButton {
                background: #88c0d0;
                color: #1a1a2e;
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #9dd0e0;
            }
            QPushButton:pressed {
                background: #78b0c0;
            }
        """

        closebtn = qt.QPushButton(_('Close'))
        closebtn.setStyleSheet(closestyle)
        closebtn.clicked.connect(self.accept)
        closebtn.setDefault(True)
        btnrow.addWidget(closebtn)

        layout.addLayout(btnrow)

    def _showVersions(self):
        """Show software version info."""
        text = versionHeader()
        dlg = qt.QMessageBox(self)
        dlg.setWindowTitle(_('Software Versions'))
        dlg.setText(text)
        dlg.exec()

    def _showLicense(self):
        """Show license text."""
        text = utils.getLicense()
        dlg = qt.QDialog(self)
        dlg.setWindowTitle(_('License'))
        dlg.resize(500, 400)
        lay = qt.QVBoxLayout(dlg)
        te = qt.QPlainTextEdit(dlg)
        te.setPlainText(text)
        te.setReadOnly(True)
        lay.addWidget(te)
        btn = qt.QPushButton(_('Close'))
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, alignment=qt.Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def mousePressEvent(self, event):
        """Close on click outside buttons."""
        self.accept()

    def keyPressEvent(self, event):
        """Close on Escape."""
        if event.key() == qt.Qt.Key.Key_Escape:
            self.accept()
        super().keyPressEvent(event)
