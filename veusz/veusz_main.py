#!/usr/bin/env python

#    Copyright (C) 2004 Jeremy S. Sanders
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

'''Main Plotex executable.'''

import sys
import signal
import argparse
import re
import ast

import veusz
from veusz import qtall as qt
from veusz import utils

if sys.version_info[0] < 3:
    raise RuntimeError('Plotex only supports Python 3')

copyr='''Plotex %s — a fork of Veusz

Author: M. Ignacio Monge García
Original Veusz by Jeremy Sanders 2003-2025 <jeremy@jeremysanders.net>
Licenced under the GNU General Public Licence (version 2 or greater)
'''

def _(text, disambiguation=None, context='Application'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

def handleIntSignal(signum, frame):
    '''Ask windows to close if Ctrl+C pressed.'''
    qt.QApplication.instance().closeAllWindows()

class _RoundedSplash(qt.QSplashScreen):
    """Splash screen with rounded corners."""
    _radius = 16

    def __init__(self):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        p = qt.QPainter(self)
        p.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        p.setBrush(qt.QColor('#1a1a2e'))
        p.setPen(qt.Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), self._radius, self._radius)
        p.end()

def makeSplash(app):
    '''Make a modern, minimal splash screen.'''

    splash = _RoundedSplash()
    splash.setStyleSheet("background: transparent;")

    layout = qt.QVBoxLayout(splash)
    layout.setContentsMargins(48, 42, 48, 32)
    layout.setSpacing(0)

    # logo
    logo = qt.QLabel()
    pix = utils.getPixmap('plotex_logo.png')
    scaled = pix.scaled(
        144, 144,
        qt.Qt.AspectRatioMode.KeepAspectRatio,
        qt.Qt.TransformationMode.SmoothTransformation)
    logo.setPixmap(scaled)
    logo.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(logo)

    layout.addSpacing(18)

    # app name
    title = qt.QLabel('Plotex')
    title.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet(
        "color: #e0e0e0;"
        "font-size: 27px;"
        "font-weight: 600;"
        "letter-spacing: 5px;"
        "background: transparent;"
    )
    layout.addWidget(title)

    layout.addSpacing(6)

    # version
    ver = qt.QLabel('v%s' % utils.version())
    ver.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
    ver.setStyleSheet(
        "color: #6a6a8a;"
        "font-size: 13px;"
        "background: transparent;"
    )
    layout.addWidget(ver)

    layout.addSpacing(20)

    # thin separator
    sep = qt.QFrame()
    sep.setFrameShape(qt.QFrame.Shape.HLine)
    sep.setStyleSheet(
        "color: #2a2a4a;"
        "background: #2a2a4a;"
        "max-height: 1px;"
    )
    layout.addWidget(sep)

    layout.addSpacing(14)

    # credits
    credits = qt.QLabel(
        'M. Ignacio Monge Garc\u00eda\n'
        'Based on Veusz by Jeremy Sanders')
    credits.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
    credits.setStyleSheet(
        "color: #5a5a7a;"
        "font-size: 12px;"
        "background: transparent;"
    )
    layout.addWidget(credits)

    layout.addSpacing(10)

    # progress bar
    splash._progressBar = qt.QProgressBar()
    splash._progressBar.setRange(0, 0)  # indeterminate initially
    splash._progressBar.setFixedHeight(3)
    splash._progressBar.setTextVisible(False)
    splash._progressBar.setStyleSheet('''
        QProgressBar {
            background: #2a2a4a;
            border: none;
            border-radius: 1px;
        }
        QProgressBar::chunk {
            background: #88c0d0;
            border-radius: 1px;
        }
    ''')
    layout.addWidget(splash._progressBar)

    # status label
    splash._statusLabel = qt.QLabel(_('Starting…'))
    splash._statusLabel.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
    splash._statusLabel.setStyleSheet(
        "color: #4a4a6a;"
        "font-size: 10px;"
        "background: transparent;"
    )
    layout.addWidget(splash._statusLabel)

    # fixed width, auto height
    splash.setFixedWidth(390)

    # center on screen
    screen = splash.screen().size()
    hint = layout.sizeHint()
    splash.move(
        (screen.width() - 390) // 2,
        (screen.height() - hint.height()) // 2
    )

    return splash

def excepthook(excepttype, exceptvalue, tracebackobj):
    '''Show exception dialog if an exception occurs.'''

    # exception dialog doesnt work if not in main thread, so we send
    # the exception to the application to display
    app = qt.QGuiApplication.instance()
    if app.thread is not qt.QThread.currentThread():
        app.signalException.emit(excepttype, exceptvalue, tracebackobj)
        return

    sys.setrecursionlimit(sys.getrecursionlimit()+1000)

    from veusz.dialogs.exceptiondialog import ExceptionDialog
    if not isinstance(exceptvalue, utils.IgnoreException):
        # next exception is ignored to clear out the stack frame of the
        # previous exception - yuck
        d = ExceptionDialog((excepttype, exceptvalue, tracebackobj), None)
        d.exec()

def listen(docs, quiet):
    '''For running with --listen option.'''
    from veusz.veusz_listen import openWindow
    openWindow(docs, quiet=quiet)

def _parseExportOption(option):
    """Parse a single --export-option key=value pair safely."""

    try:
        parsed = ast.parse(option, mode='exec')
    except SyntaxError as exc:
        raise ValueError("Invalid export option %r: %s" % (option, exc)) from exc

    if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.Assign):
        raise ValueError(
            "Invalid export option %r: expected key=value" % option)

    assign = parsed.body[0]
    if len(assign.targets) != 1 or not isinstance(assign.targets[0], ast.Name):
        raise ValueError(
            "Invalid export option %r: expected simple keyword name" % option)

    try:
        value = ast.literal_eval(assign.value)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(
            "Invalid export option %r: value must be a literal" % option) from exc

    return assign.targets[0].id, value

def _parseExportOptions(options):
    """Parse --export-option values into keyword arguments."""

    out = {}
    for option in options or ():
        name, value = _parseExportOption(option)
        out[name] = value
    return out

def export(exports, docs, options):
    '''A shortcut to load a set of files and export them.'''
    from veusz import document

    optargs = _parseExportOptions(options)

    for expfn, vsz in zip(exports, docs):
        doc = document.Document()
        ci = document.CommandInterpreter(doc)
        ci.Load(vsz)
        ci.runCommand('Export', (expfn,), optargs)

def convertArgsUnicode(args):
    '''Convert set of arguments to unicode (for Python 2).
    Arguments in argv use current file system encoding
    '''
    enc = sys.getfilesystemencoding()
    # bail out if not supported
    if enc is None:
        return args
    out = []
    for a in args:
        if isinstance(a, bytes):
            out.append(a.decode(enc))
        else:
            out.append(a)
    return out

class ImportThread(qt.QThread):
    '''Do import of main code within another thread.
    Main application runs when this is done
    '''
    progressMsg = qt.pyqtSignal(str, int)

    def run(self):
        self.progressMsg.emit(_('Loading settings…'), 20)
        from veusz import setting
        self.progressMsg.emit(_('Loading widgets…'), 50)
        from veusz import widgets
        self.progressMsg.emit(_('Loading data import…'), 80)
        from veusz import dataimport
        self.progressMsg.emit(_('Ready'), 100)

class PlotexApp(qt.QApplication):
    """Event which can open mac files."""

    signalException = qt.pyqtSignal(object, object, object)

    def __init__(self):
        qt.QApplication.__init__(self, sys.argv)

        self.lastWindowClosed.connect(self.quit)
        self.signalException.connect(self.showException)

        # modern flat style
        self.setStyle("fusion")
        self._applyModernTheme()

        # Bind desktop file to display icon in wayland
        qt.QGuiApplication.setDesktopFileName("plotex")

        # register a signal handler to catch ctrl+C
        signal.signal(signal.SIGINT, handleIntSignal)

        # parse command line options
        parser = argparse.ArgumentParser(
            description='Plotex scientific plotting package')
        parser.add_argument(
            '--version', action='version',
            version=copyr % utils.version())
        parser.add_argument(
            '--unsafe-mode',
            action='store_true',
            help='disable safety checks when running documents'
            ' or scripts')
        parser.add_argument(
            '--listen',
            action='store_true',
            help='read and execute Plotex commands from stdin,'
            ' replacing veusz_listen')
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='if in listening mode, do not open a window but'
            ' execute commands quietly')
        parser.add_argument(
            '--export', action='append', metavar='FILE',
            help='export the next document to this'
            ' output image file, exiting when finished')
        parser.add_argument(
            '--export-option', action='append', metavar='VAL',
            help='add option when exporting file')
        parser.add_argument(
            '--embed-remote',
            action='store_true',
            help='(internal - not for external use)')
        parser.add_argument(
            '--veusz-plugin', action='append', metavar='FILE',
            help='load the plugin from the file given for '
            'the Plotex session')
        parser.add_argument(
            '--translation', metavar='FILE',
            help='load the translation .qm file given')
        parser.add_argument(
            'docs', metavar='FILE', nargs='*',
            help='document to load')

        self.args = args = parser.parse_args()

        args.docs = convertArgsUnicode(args.docs)

        # export files to make images
        if args.export:
            if len(args.export) != len(args.docs):
                parser.error(
                    'export option needs same number of documents and '
                    'output files')
            args.export = convertArgsUnicode(args.export)

        self.openeventfiles = []
        self.startupdone = False
        self.splash = None
        self.trans = None

    def _applyModernTheme(self):
        """Apply modern flat stylesheet."""
        import os
        qssfile = os.path.join(
            os.path.dirname(__file__), 'ui', 'modern_style.qss')
        try:
            with open(qssfile, 'r') as f:
                sheet = f.read()
        except (IOError, OSError):
            sheet = ''

        # append focus indicators for accessibility
        sheet += """
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
        border: 1.5px solid #4A90D9;
    }
"""
        self.setStyleSheet(sheet)

    def applyUIFont(self):
        """Apply saved UI font settings."""
        from veusz import setting
        fontname = setting.settingdb.get('ui_font', '')
        fontsize = setting.settingdb.get('ui_font_size', 9)
        fontbold = setting.settingdb.get('ui_font_bold', False)
        fontitalic = setting.settingdb.get('ui_font_italic', False)
        font = self.font()
        if fontname:
            font.setFamily(fontname)
        font.setPointSize(fontsize)
        font.setBold(fontbold)
        font.setItalic(fontitalic)
        self.setFont(font)

    def applyColorScheme(self, scheme=None):
        """Apply color scheme live, without restart."""
        from veusz import setting, utils

        if scheme is None:
            scheme = setting.settingdb['color_scheme']

        hascolorscheme = hasattr(self.styleHints(), 'setColorScheme')

        if scheme == 'default':
            if hascolorscheme:
                self.styleHints().setColorScheme(qt.Qt.ColorScheme.Unknown)
            self.setPalette(self.style().standardPalette())
        elif scheme == 'system-light' and hascolorscheme:
            self.styleHints().setColorScheme(qt.Qt.ColorScheme.Light)
            self.setPalette(self.style().standardPalette())
        elif scheme == 'system-dark' and hascolorscheme:
            self.styleHints().setColorScheme(qt.Qt.ColorScheme.Dark)
            self.setPalette(self.style().standardPalette())
        else:
            pal = utils.getPalette(scheme)
            if pal is not None:
                self.setPalette(pal)

        self._applyModernTheme()

    def openMainWindow(self, docs):
        """Open the main window with any loaded files."""
        from veusz.windows.mainwindow import MainWindow
        from veusz.document import Document, PluginLoadError

        emptywins = []
        for w in self.topLevelWidgets():
            if isinstance(w, MainWindow) and w.document.isBlank():
                emptywins.append(w)

        if docs:
            # load in filenames given
            for filename in docs:
                if not emptywins:
                    MainWindow.CreateWindow(filename)
                elif filename:
                    emptywins[0].openFile(filename)
        else:
            # create blank window
            MainWindow.CreateWindow()

    def openPendingFiles(self):
        """If startup complete, open any files."""
        if self.startupdone:
            self.openMainWindow([None] + self.openeventfiles)
            del self.openeventfiles[:]
        else:
            qt.QTimer.singleShot(100, self.openPendingFiles)

    def _onNewConnection(self):
        """Another instance sent us filenames to open."""
        server = self._localServer
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            if conn.waitForReadyRead(1000):
                data = bytes(conn.readAll())
                try:
                    import json
                    files = json.loads(data.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    files = []
                conn.close()

                # open files in existing window as new tabs
                if files:
                    from veusz.windows.mainwindow import MainWindow
                    mainwin = None
                    for w in self.topLevelWidgets():
                        if isinstance(w, MainWindow):
                            mainwin = w
                            break
                    if mainwin:
                        for f in files:
                            if f:
                                mainwin.openFile(f)
                        mainwin.raise_()
                        mainwin.activateWindow()
                        # on Windows, raise alone may not work
                        mainwin.setWindowState(
                            mainwin.windowState() & ~qt.Qt.WindowState.WindowMinimized)
                        mainwin.show()
                    else:
                        self.openMainWindow(files)

    def event(self, event):
        """Handle events. This is the only way to get the FileOpen event.
        FileOpen is used by MacOS to open files.
        """
        if event.type() == qt.QEvent.Type.FileOpen:
            self.openeventfiles.append(event.file())
            # need to wait until startup has finished
            qt.QTimer.singleShot(100, self.openPendingFiles)
            return True
        return qt.QApplication.event(self, event)

    def startup(self):
        """Do startup."""

        if not (self.args.listen or self.args.export):
            # show the splash screen on normal start
            self.splash = makeSplash(self)
            self.splash.resize(self.splash.sizeHint())
            self.splash.show()
            self.splash.raise_()
            # force paint so splash is visible immediately
            self.processEvents()

        self.thread = ImportThread()
        self.thread.finished.connect(self.slotStartApplication)
        if self.splash is not None:
            self.thread.progressMsg.connect(self._splashProgress)
        self.thread.start()

    def _splashProgress(self, msg, pct):
        """Update splash screen progress."""
        if self.splash is not None:
            self.splash._statusLabel.setText(msg)
            self.splash._progressBar.setRange(0, 100)
            self.splash._progressBar.setValue(pct)
            self.processEvents()

    def slotStartApplication(self):
        """Start app, after modules imported."""

        args = self.args

        from veusz.utils import vzdbus, vzsamp
        vzdbus.setup()
        vzsamp.setup()

        # add text if we want to display an error after startup
        startuperrors = []

        from veusz import document
        from veusz import setting

        # install exception hook after thread has finished
        global defaultexcepthook
        defaultexcepthook = sys.excepthook
        sys.excepthook = excepthook

        # for people who want to run any old script
        setting.transient_settings['unsafe_mode'] = bool(
            args.unsafe_mode)

        # optionally load a translation
        txfile = args.translation or setting.settingdb['translation_file']
        if txfile:
            self.trans = qt.QTranslator()
            if self.trans.load(txfile):
                self.installTranslator(self.trans)
            else:
                startuperrors.append(
                    'Error loading translation "%s"' % txfile)

        # add directories to path
        if setting.settingdb['external_pythonpath']:
            # We want a list of items separated by colons
            # Unfortunately on windows there can be a colon and drive letter,
            # so we avoid splitting colons which look like a:\foo or B:/bar
            parts = re.findall(
                r'[A-Za-z]:[\\/][^:]+|[^:]+',
                setting.settingdb['external_pythonpath'])
            sys.path += list(parts)

        try:
            # load plugins from settings
            document.Document.loadPlugins()
            if args.veusz_plugin:
                # load plugins on command line
                document.Document.loadPlugins(pluginlist=args.veusz_plugin)
        except document.PluginLoadError as e:
            startuperrors.append(str(e))

        # color theme - apply live
        self.applyColorScheme()
        self.applyUIFont()

        if self.splash is not None:
            self._splashProgress(_('Opening window…'), 95)

        # different modes
        if args.listen:
            # listen to incoming commands
            listen(args.docs, quiet=args.quiet)
        elif args.export:
            export(args.export, args.docs, args.export_option)
            self.quit()
            sys.exit(0)
        else:
            # standard start main window
            self.openMainWindow(args.docs)
            self.startupdone = True

        # clear splash when startup done
        if self.splash is not None:
            self.splash.finish(self.topLevelWidgets()[0])

        # this has to be displayed after the main window is created,
        # otherwise it never gets shown
        for error in startuperrors:
            qt.QMessageBox.critical(None, _("Error starting - Plotex"), error)

    def showException(self, excepttype, exceptvalue, tracebackobj):
        """Show an exception dialog (raised from another thread)."""
        from veusz.dialogs.exceptiondialog import ExceptionDialog
        if not isinstance(exceptvalue, utils.IgnoreException):
            # next exception is ignored to clear out the stack frame of the
            # previous exception - yuck
            d = ExceptionDialog((excepttype, exceptvalue, tracebackobj), None)
            d.exec()

def run():
    '''Run the main application.'''

    # high DPI support
    try:
        qt.QApplication.setHighDpiScaleFactorRoundingPolicy(
            qt.QApplication.highDpiScaleFactorRoundingPolicy().PassThrough)
    except AttributeError:
        # old qt versions
        pass

    # jump to the embedding client entry point if required
    if len(sys.argv) == 2 and sys.argv[1] == '--embed-remote':
        from veusz.embed_remote import runremote
        runremote()
        return

    # start me up
    app = PlotexApp()

    # single-instance: if another Plotex is running, send files and exit
    from PyQt6.QtNetwork import QLocalSocket, QLocalServer
    _server_name = 'plotex-single-instance'

    # skip single-instance for --listen, --export, --embed-remote
    if not (app.args.listen or app.args.export):
        socket = QLocalSocket()
        socket.connectToServer(_server_name)
        if socket.waitForConnected(1000):
            # another instance is running — send filenames and exit
            import json
            files = [os.path.abspath(f) for f in (app.args.docs or [])]
            msg = json.dumps(files).encode('utf-8')
            socket.write(msg)
            socket.flush()
            socket.waitForBytesWritten(3000)
            socket.disconnectFromServer()
            socket.waitForDisconnected(1000)
            sys.exit(0)
        socket.close()

        # first instance: set up server
        app._localServer = QLocalServer(app)
        QLocalServer.removeServer(_server_name)
        if not app._localServer.listen(_server_name):
            # retry once
            QLocalServer.removeServer(_server_name)
            app._localServer.listen(_server_name)
        app._localServer.newConnection.connect(app._onNewConnection)

    app.startup()
    app.exec()

# if ran as a program
if __name__ == '__main__':
    #import cProfile
    #cProfile.run('run()', 'outprofile.dat')
    run()
