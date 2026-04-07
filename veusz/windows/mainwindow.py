#    Copyright (C) 2003 Jeremy S. Sanders
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

"""Implements the main window of the application."""

import os
import os.path
import sys
import re
import datetime

try:
    import h5py
except ImportError:
    h5py = None

from .. import qtall as qt

from .. import document
from .. import utils
from ..utils import vzdbus
from .. import setting
from .. import plugins
from ..qtwidgets.clicklabel import ClickLabel

from . import plotwindow
from . import treeeditwindow
from . import ribbon
from .datanavigator import DataNavigatorWindow

def _(text, disambiguation=None, context='MainWindow'):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

# shortcut to this
setdb = setting.settingdb

class DBusWinInterface(vzdbus.Object):
    """Simple DBus interface to window for triggering actions."""

    interface = 'org.veusz.actions'

    def __init__(self, actions, index):
        prefix = '/Windows/%i/Actions' % index
        # possible exception in dbus means we have to check sessionbus
        if vzdbus.sessionbus is not None:
            vzdbus.Object.__init__(self, vzdbus.sessionbus, prefix)
        self.actions = actions

    @vzdbus.method(dbus_interface=interface, out_signature='as')
    def GetActions(self):
        """Get list of actions which can be activated."""
        return sorted(self.actions)

    @vzdbus.method(dbus_interface=interface, in_signature='s')
    def TriggerAction(self, action):
        """Activate action given."""
        self.actions[action].trigger()

class MainWindow(qt.QMainWindow):
    """ The main window class for the application."""

    # this is emitted when a dialog is opened by the main window
    dialogShown = qt.pyqtSignal(qt.QWidget)
    # emitted when a document is opened
    documentOpened = qt.pyqtSignal()

    windows = []
    _untitled_counter = 0
    @classmethod
    def CreateWindow(cls, filename=None, mode='graph'):
        """Window factory function.

        If filename is given then that file is loaded into the window.
        Returns window created
        """

        # create the window, and optionally load a saved file
        win = cls()
        win.show()
        if filename:
            # load document
            win.openFileInWindow(filename)
        else:
            win.setupDefaultDoc(mode)

        # try to select first graph of first page
        win.treeedit.doInitialWidgetSelect()

        cls.windows.append(win)

        # check if tutorial wanted (only for graph mode)
        if not setting.settingdb['ask_tutorial'] and mode=='graph':
            win.askTutorial()
            # don't ask again
            setting.settingdb['ask_tutorial'] = True

        # check if version check is ok
        win.askVersionCheck()
        # periodically do the check
        win.doVersionCheck()

        # is it ok to do feedback?
        win.askFeedbackCheck()
        # periodically send feedback
        win.doFeedback()

        # show one-time hint about the console
        qt.QTimer.singleShot(
            3000,
            lambda: win.statusBar().showMessage(
                _("Tip: Python console available in View menu"), 5000))

        return win

    def __init__(self, *args):
        qt.QMainWindow.__init__(self, *args)
        self.setAcceptDrops(True)

        # icon and different size variations
        self.setWindowIcon( utils.getIcon('plotex') )

        # tab management
        self._tabs = []        # list of tab state dicts
        self._currentTab = None  # current tab state dict
        self._tabSignals = []    # connected signals for current tab

        # initial document (will be associated with first tab)
        self.document = document.Document()
        self.filename = ''
        self.updateTitlebar()

        # keep a list of references to dialogs
        self.dialogs = []

        # construct menus and toolbars
        self._defineMenus()

        # tabbed plot area
        self._tabwidget = qt.QTabWidget()
        self._tabwidget.setTabsClosable(True)
        self._tabwidget.setMovable(True)
        self._tabwidget.setDocumentMode(True)
        self._tabwidget.setAcceptDrops(True)
        self._tabwidget.dragEnterEvent = self.dragEnterEvent
        self._tabwidget.dropEvent = self.dropEvent
        self._tabwidget.tabCloseRequested.connect(self._slotCloseTab)
        # currentChanged connected later, after all widgets exist
        self.setCentralWidget(self._tabwidget)

        # make first plot window and add as tab
        self.plot = plotwindow.PlotWindow(
            self.document, self, menu=self.menus['view'])

        # likewise with the tree-editing window
        self.treeedit = treeeditwindow.TreeEditDock(self.document, self)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.LeftDockWidgetArea, self.treeedit)
        self.propdock = treeeditwindow.PropertiesDock(
            self.document, self.treeedit, self)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.LeftDockWidgetArea, self.propdock)
        self.formatdock = treeeditwindow.FormatDock(
            self.document, self.treeedit, self)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.LeftDockWidgetArea, self.formatdock)
        self.datadock = DataNavigatorWindow(self.document, self, self)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.RightDockWidgetArea, self.datadock)

        # console initialized but deferred — created just before geometry restore
        self._console = None

        # populate ribbon now that all actions exist
        self._populateRibbon()

        # rewire view actions to delegate through mainwindow
        # so they always target self.plot (which changes on tab switch)
        self._rewireViewActions()

        # register first tab
        self._addTabState(self.document, self.plot, '')

        # assemble the statusbar
        statusbar = self.statusbar = qt.QStatusBar(self)
        self.setStatusBar(statusbar)
        self.updateStatusbar(_('Ready'))

        # a label for the picker readout
        self.pickerlabel = qt.QLabel(statusbar)
        self._setPickerFont(self.pickerlabel)
        statusbar.addPermanentWidget(self.pickerlabel)
        self.pickerlabel.hide()

        # plot queue - how many plots are currently being drawn
        self.plotqueuecount = 0
        self.plotqueuelabel = qt.QLabel()
        self.plotqueuelabel.setToolTip(_("Number of rendering jobs remaining"))
        statusbar.addWidget(self.plotqueuelabel)
        self.plotqueuelabel.show()

        # a label for the cursor position readout
        self.axisvalueslabel = qt.QLabel(statusbar)
        self.axisvalueslabel.setMinimumWidth(140)
        statusbar.addPermanentWidget(self.axisvalueslabel)
        self.axisvalueslabel.show()
        self.slotUpdateAxisValues(None)

        # a label for the page number readout
        self.pagelabel = qt.QLabel(statusbar)
        self.pagelabel.setMinimumWidth(70)
        statusbar.addPermanentWidget(self.pagelabel)
        self.pagelabel.show()

        # security label
        self.securitylabel = ClickLabel(_("Untrusted mode"), statusbar)
        statusbar.addPermanentWidget(self.securitylabel)
        self.securitylabel.show()
        self.securitylabel.clicked.connect(self.slotFileTrust)

        # --- PowerPoint-style zoom controls on the right of the status bar ---
        self._buildStatusBarZoomControls(statusbar)

        # working directory - use previous one
        self.dirname = setdb.get('dirname', qt.QDir.homePath())
        if setdb['dirname_usecwd']:
            self.dirname = os.getcwd()

        # now safe to connect tab switching (all widgets exist)
        self._tabwidget.currentChanged.connect(self._slotTabChanged)
        self._connectTabSignals()

        # enable/disable undo/redo
        self.menus['edit'].aboutToShow.connect(self.slotAboutToShowEdit)

        # get the list of recently opened files
        self.populateRecentFiles()
        # create console before geometry restore (restoreState needs all docks)
        self._initConsole()
        self.setupWindowGeometry()
        self.defineViewWindowMenu()

        # add on dbus interface
        self.dbusdocinterface = document.DBusInterface(self.document)
        self.dbuswininterface = DBusWinInterface(
            self.vzactions, self.dbusdocinterface.index)

        # has the document already been setup
        self.documentsetup = False

    @property
    def console(self):
        """Lazy-create console window on first access."""
        if self._console is None:
            self._initConsole()
        return self._console

    def _initConsole(self):
        """Create the console dock widget."""
        if self._console is not None:
            return
        from . import consolewindow
        self._console = consolewindow.ConsoleWindow(
            self.document, self)
        self._console.hide()
        self.addDockWidget(
            qt.Qt.DockWidgetArea.BottomDockWidgetArea, self._console)

    @property
    def interpreter(self):
        return self.console.interpreter

    # ---- Tab management ----

    def _addTabState(self, doc, plot, filename):
        """Register a new tab and add it to the tab widget."""
        from .widgettree import WidgetTreeModel
        treemodel = WidgetTreeModel(doc)
        if filename:
            untitled_label = ''
        else:
            MainWindow._untitled_counter += 1
            untitled_label = _('Untitled %d') % MainWindow._untitled_counter
        state = {
            'document': doc,
            'plot': plot,
            'filename': filename,
            'treemodel': treemodel,
            'docsetup': False,
            'untitled_label': untitled_label,
            'split': None,
            'split_secondary': None,
            'split_dir': None,
        }
        self._tabs.append(state)
        label = os.path.basename(filename) if filename else untitled_label
        idx = self._tabwidget.addTab(plot, label)
        self._tabwidget.setCurrentIndex(idx)
        return state

    def _connectTabSignals(self):
        """Connect signals for the current document/plot."""
        self._disconnectTabSignals()

        doc = self.document
        plot = self.plot
        sigs = []

        def c(sig, slot):
            sig.connect(slot)
            sigs.append((sig, slot))

        c(plot.sigQueueChange, self.plotQueueChanged)
        c(plot.sigUpdatePage, self.slotUpdatePage)
        c(plot.sigAxisValuesFromMouse, self.slotUpdateAxisValues)
        c(plot.sigPickerEnabled, self.slotPickerEnabled)
        c(plot.sigPointPicked, self.slotUpdatePickerLabel)
        c(doc.signalModified, self.slotModifiedDoc)
        c(doc.sigSecuritySet, self.slotUpdateSecurity)
        c(doc.sigAllowedImports, self.slotAllowedImportsDoc)
        c(self.treeedit.sigPageChanged, self._delegateSetPageNumber)
        c(plot.sigWidgetClicked, self.treeedit.selectWidget)
        c(self.treeedit.widgetsSelected, self._delegateSelectedWidgets)
        c(plot.sigZoomChanged, self.slotUpdateZoom)

        self._tabSignals = sigs

        # sync zoom controls to the current tab's zoom factor
        self.slotUpdateZoom(plot.zoomfactor)

    def _disconnectTabSignals(self):
        """Disconnect all signals from the current tab."""
        for sig, slot in self._tabSignals:
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._tabSignals = []

    def _slotTabChanged(self, index):
        """User switched to a different tab."""
        if index < 0 or index >= len(self._tabs):
            return

        # save full state of outgoing tab
        if self._currentTab is not None:
            try:
                oldidx = self._tabs.index(self._currentTab)
            except ValueError:
                oldidx = -1
            if oldidx >= 0:
                self._tabs[oldidx]['zoom'] = self.plot.zoomfactor
                self._tabs[oldidx]['page'] = self.plot.pagenumber
                self._tabs[oldidx]['selwidgets'] = list(
                    self.treeedit.selwidgets)

        self._disconnectTabSignals()

        state = self._tabs[index]
        self._currentTab = state
        self.document = state['document']
        self.plot = state['plot']
        self.filename = state['filename']
        self.documentsetup = state['docsetup']

        # swap the tree model
        self.treeedit.setDocument(self.document, state['treemodel'])
        # update data navigator
        self.datadock.setDocument(self.document)

        self._connectTabSignals()
        self._reconnectViewActions()
        self.updateTitlebar()

        # invalidate dock caches so they rebuild on next selection
        self.formatdock._lastWidgetIds = None
        self.propdock._lastSetnsproxy = None

        # restore page and zoom without triggering reset
        savedPage = state.get('page', 0)
        savedZoom = state.get('zoom', None)
        self.plot.pagenumber = savedPage
        self.plot.oldpagenumber = savedPage
        if savedZoom is not None:
            self.plot.zoomfactor = savedZoom
            self.plot.oldzoom = -1  # force re-render

        # restore selection or fall back to initial
        savedSel = state.get('selwidgets', None)
        if savedSel:
            for w in savedSel:
                self.treeedit.selectWidget(w)
        else:
            self.treeedit.doInitialWidgetSelect()

        # trigger re-render with correct zoom/page
        self.plot.checkPlotUpdate()

        # sync split buttons checked state with this tab
        split_dir = state.get('split_dir')
        self.vzactions['view.splitH'].setChecked(split_dir == 'H')
        self.vzactions['view.splitV'].setChecked(split_dir == 'V')

    def _reconnectViewActions(self):
        """No-op: view actions use delegate methods below."""
        pass

    def _rewireViewActions(self):
        """Replace PlotWindow-bound view action slots with mainwindow
        delegates that always forward to self.plot (the active tab)."""
        acts = self.vzactions
        rewire = {
            'view.zoomin': self._delegateZoomIn,
            'view.zoomout': self._delegateZoomOut,
            'view.zoom11': self._delegateZoom11,
            'view.zoomwidth': self._delegateZoomWidth,
            'view.zoomheight': self._delegateZoomHeight,
            'view.zoompage': self._delegateZoomPage,
            'view.prevpage': self._delegatePrevPage,
            'view.nextpage': self._delegateNextPage,
            'view.fullscreen': self._delegateFullScreen,
        }
        for actname, delegate in rewire.items():
            if actname in acts:
                act = acts[actname]
                # disconnect the original PlotWindow slot
                try:
                    act.triggered.disconnect()
                except (TypeError, RuntimeError):
                    pass
                # connect to mainwindow delegate
                act.triggered.connect(delegate)

        # Rewire the select-mode action group to delegate through
        # MainWindow so it always targets the active PlotWindow.
        grp = acts['view.select'].actionGroup()
        if grp is not None:
            try:
                grp.triggered.disconnect()
            except (TypeError, RuntimeError):
                pass
            grp.triggered.connect(self._delegateSelectMode)

    # Delegate view actions to the current plot window.
    # These are connected once at action creation time and always
    # forward to self._activePlot(), which returns the focused
    # split pane or self.plot.
    # Tracks the last-focused split pane so that delegates still
    # target the right pane even after focus moves to the tree/docks.
    _lastFocusedSplitPane = None

    def _activePlot(self):
        """Return the PlotWindow that should receive view commands.
        In split mode, returns the last-focused pane."""
        idx = self._tabwidget.currentIndex()
        if idx >= 0 and idx < len(self._tabs):
            state = self._tabs[idx]
            sec = state.get('split_secondary')
            if sec is not None:
                # check live focus first
                fw = qt.QApplication.focusWidget()
                if fw is sec:
                    return sec
                if fw is state['plot']:
                    return state['plot']
                # fall back to last-remembered pane
                if self._lastFocusedSplitPane is sec:
                    return sec
        return self.plot

    def _delegateZoomIn(self):
        self._activePlot().slotViewZoomIn()
    def _delegateZoomOut(self):
        self._activePlot().slotViewZoomOut()
    def _delegateZoom11(self):
        self._activePlot().slotViewZoom11()
    def _delegateZoomWidth(self):
        self._activePlot().slotViewZoomWidth()
    def _delegateZoomHeight(self):
        self._activePlot().slotViewZoomHeight()
    def _delegateZoomPage(self):
        self._activePlot().slotViewZoomPage()
    def _delegatePrevPage(self):
        self._activePlot().slotViewPreviousPage()
    def _delegateNextPage(self):
        self._activePlot().slotViewNextPage()
    def _delegateFullScreen(self):
        self.plot.slotFullScreen()
    def _delegateSelectMode(self, action):
        self._activePlot().slotSelectMode(action)
    def _delegateSetPageNumber(self, page):
        self._activePlot().setPageNumber(page)
    def _delegateSelectedWidgets(self, widgets, setnsproxy=None):
        self._activePlot().selectedWidgets(widgets)

    # ── Status-bar zoom controls (PowerPoint-style) ──────────────

    def _buildStatusBarZoomControls(self, statusbar):
        """Build a PowerPoint-style zoom strip on the right of the status bar.

        Layout: [Fit page][Fit width] | [−] ══●══ [+] | 100% | [⛶]
        """
        container = qt.QWidget(statusbar)
        layout = qt.QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        iconsz = qt.QSize(16, 16)
        btnsz = 20

        def _toolbtn(icon_name, tooltip, slot):
            btn = qt.QToolButton(container)
            btn.setIcon(utils.getIcon(icon_name))
            btn.setIconSize(iconsz)
            btn.setToolTip(tooltip)
            btn.setAutoRaise(True)
            btn.setFixedSize(btnsz, btnsz)
            btn.clicked.connect(slot)
            return btn

        def _sep():
            s = qt.QFrame(container)
            s.setFrameShape(qt.QFrame.Shape.VLine)
            s.setFrameShadow(qt.QFrame.Shadow.Sunken)
            s.setFixedSize(8, 16)
            return s

        # Fit-to-width button
        layout.addWidget(_toolbtn(
            'kde-zoom-width-veuszedit', _('Zoom to width'),
            self._delegateZoomWidth))

        # Fit-to-height button
        layout.addWidget(_toolbtn(
            'kde-zoom-height-veuszedit', _('Zoom to height'),
            self._delegateZoomHeight))

        layout.addWidget(_sep())

        # Zoom-out button
        layout.addWidget(_toolbtn(
            'kde-zoom-out', _('Zoom out (Ctrl+−)'),
            self._delegateZoomOut))

        # Zoom slider  (range 10 %–800 %, stored as int percentage)
        self._sbZoomSlider = qt.QSlider(qt.Qt.Orientation.Horizontal, container)
        self._sbZoomSlider.setRange(10, 800)
        self._sbZoomSlider.setValue(100)
        self._sbZoomSlider.setSingleStep(10)
        self._sbZoomSlider.setPageStep(50)
        self._sbZoomSlider.setFixedWidth(100)
        self._sbZoomSlider.setToolTip(_('Zoom level'))
        self._sbZoomSlider.valueChanged.connect(self._slotZoomSliderChanged)
        layout.addWidget(self._sbZoomSlider)

        # Zoom-in button
        layout.addWidget(_toolbtn(
            'kde-zoom-in', _('Zoom in (Ctrl++)'),
            self._delegateZoomIn))

        layout.addWidget(_sep())

        # Percentage label (clickable → reset to 100 %)
        self._sbZoomLabel = ClickLabel('100 %', container)
        self._sbZoomLabel.setToolTip(_('Click to reset zoom to 100 %'))
        self._sbZoomLabel.setFixedWidth(42)
        self._sbZoomLabel.setAlignment(
            qt.Qt.AlignmentFlag.AlignCenter | qt.Qt.AlignmentFlag.AlignVCenter)
        f = self._sbZoomLabel.font()
        f.setPointSize(f.pointSize() - 1)
        self._sbZoomLabel.setFont(f)
        self._sbZoomLabel.clicked.connect(self._delegateZoom11)
        layout.addWidget(self._sbZoomLabel)

        layout.addWidget(_sep())

        # Fullscreen button
        layout.addWidget(_toolbtn(
            'veusz-view-fullscreen', _('Full screen (Ctrl+F11)'),
            self._delegateFullScreen))


        # fix the container size so it never shifts with status messages
        container.setSizePolicy(
            qt.QSizePolicy.Policy.Fixed, qt.QSizePolicy.Policy.Fixed)
        statusbar.addPermanentWidget(container)
        container.show()

        # guard: don't feed slider changes back into the plot while
        # we are programmatically updating the slider from the plot
        self._zoomSliderUpdating = False

    def _slotZoomSliderChanged(self, value):
        """User dragged the status-bar zoom slider."""
        if self._zoomSliderUpdating:
            return
        self._activePlot().setZoomFactor(value / 100.0)

    def slotUpdateZoom(self, zoomfactor):
        """Called when PlotWindow zoom changes – keep slider/label in sync."""
        pct = int(round(zoomfactor * 100))
        self._zoomSliderUpdating = True
        self._sbZoomSlider.setValue(pct)
        self._zoomSliderUpdating = False
        self._sbZoomLabel.setText('%d %%' % pct)

    # ── Print preview ─────────────────────────────────────────────

    def slotPrintPreview(self):
        """Show a print-preview dialog for the current document."""
        if not self.document.getVisiblePages():
            qt.QMessageBox.warning(
                self, _("Error - Plotex"), _("No pages to print"))
            return

        printer = qt.QPrinter(qt.QPrinter.PrinterMode.HighResolution)
        printer.setColorMode(qt.QPrinter.ColorMode.Color)
        if self.filename:
            printer.setDocName(self.filename)

        preview = qt.QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(_('Print Preview - Plotex'))
        preview.paintRequested.connect(self._paintPreview)
        preview.exec()

    def _paintPreview(self, printer):
        """Render all visible pages onto the printer for preview."""
        from ..document.export import printPages
        pages = list(range(self.document.getNumberPages()))
        printPages(self.document, printer, pages)

    # ── Split view ───────────────────────────────────────────────

    _splitFocusBorder = '2px solid #4a90d9'
    _splitNoBorder = '2px solid transparent'

    def slotToggleSplitH(self):
        """Toggle horizontal split (top/bottom)."""
        self._toggleSplit('H', qt.Qt.Orientation.Vertical)

    def slotToggleSplitV(self):
        """Toggle vertical split (left/right)."""
        self._toggleSplit('V', qt.Qt.Orientation.Horizontal)

    def _toggleSplit(self, direction, orientation):
        """Toggle split for direction 'H' or 'V'."""
        idx = self._tabwidget.currentIndex()
        if idx < 0 or idx >= len(self._tabs):
            return
        state = self._tabs[idx]
        current_dir = state.get('split_dir')

        if current_dir is not None:
            # already split — remove first
            self._removeSplit(idx)
            if current_dir == direction:
                # same button toggled off → done
                return

        # create the split
        self._createSplit(idx, direction, orientation)

    def _createSplit(self, idx, direction, orientation):
        """Replace the tab's PlotWindow with a QSplitter holding two views."""
        state = self._tabs[idx]
        primary = state['plot']
        label = self._tabwidget.tabText(idx)

        self._tabwidget.blockSignals(True)

        splitter = qt.QSplitter(orientation, self._tabwidget)
        splitter.addWidget(primary)
        primary.show()

        secondary = plotwindow.PlotWindow(self.document, splitter)
        secondary.vzactions = self.vzactions
        splitter.addWidget(secondary)
        splitter.setSizes([1, 1])

        self._tabwidget.removeTab(idx)
        self._tabwidget.insertTab(idx, splitter, label)
        self._tabwidget.setCurrentIndex(idx)
        self._tabwidget.blockSignals(False)

        state['split'] = splitter
        state['split_secondary'] = secondary
        state['split_dir'] = direction

        # signals
        secondary.sigZoomChanged.connect(self._onSplitPaneZoomChanged)
        secondary.sigUpdatePage.connect(self._onSplitPanePageChanged)
        primary.sigZoomChanged.connect(self._onSplitPaneZoomChanged)
        # clicking widgets in secondary updates tree/properties
        secondary.sigWidgetClicked.connect(self.treeedit.selectWidget)

        # focus feedback
        primary.setStyleSheet(
            'PlotWindow { border: %s; }' % self._splitFocusBorder)
        secondary.setStyleSheet(
            'PlotWindow { border: %s; }' % self._splitNoBorder)
        primary.installEventFilter(self)
        secondary.installEventFilter(self)

        # initial state + force render
        secondary.pagenumber = primary.pagenumber
        secondary.zoomfactor = primary.zoomfactor
        primary.oldzoom = -1
        primary.checkPlotUpdate()
        secondary.checkPlotUpdate()

        self.vzactions['view.splitH'].setChecked(direction == 'H')
        self.vzactions['view.splitV'].setChecked(direction == 'V')

    def _removeSplit(self, idx):
        """Remove the split and restore the single PlotWindow as tab."""
        state = self._tabs[idx]
        splitter = state['split']
        primary = state['plot']
        secondary = state['split_secondary']

        primary.removeEventFilter(self)
        secondary.removeEventFilter(self)
        primary.setStyleSheet('')

        for sig in (
            (secondary.sigZoomChanged, self._onSplitPaneZoomChanged),
            (secondary.sigUpdatePage, self._onSplitPanePageChanged),
            (primary.sigZoomChanged, self._onSplitPaneZoomChanged),
            (secondary.sigWidgetClicked, self.treeedit.selectWidget),
        ):
            try:
                sig[0].disconnect(sig[1])
            except (TypeError, RuntimeError):
                pass

        label = self._tabwidget.tabText(idx)
        self._tabwidget.blockSignals(True)

        primary.setParent(None)
        secondary.rendercontrol.exitThreads()
        secondary.setParent(None)
        secondary.deleteLater()
        splitter.setParent(None)
        splitter.deleteLater()

        self._tabwidget.removeTab(idx)
        self._tabwidget.insertTab(idx, primary, label)
        self._tabwidget.setCurrentIndex(idx)
        self._tabwidget.blockSignals(False)

        state['split'] = None
        state['split_secondary'] = None
        state['split_dir'] = None
        self._lastFocusedSplitPane = None

        primary.oldzoom = -1
        primary.checkPlotUpdate()

        self.vzactions['view.splitH'].setChecked(False)
        self.vzactions['view.splitV'].setChecked(False)

    def _onSplitPaneZoomChanged(self, zoomfactor):
        self._updateSplitStatusBar()

    def _onSplitPanePageChanged(self, page):
        pass

    def _updateSplitStatusBar(self):
        idx = self._tabwidget.currentIndex()
        if idx < 0 or idx >= len(self._tabs):
            return
        state = self._tabs[idx]
        if state.get('split') is None:
            return
        fw = qt.QApplication.focusWidget()
        sec = state.get('split_secondary')
        if sec is not None and fw is sec:
            self.slotUpdateZoom(sec.zoomfactor)
        else:
            self.slotUpdateZoom(state['plot'].zoomfactor)

    def eventFilter(self, obj, event):
        """Track focus changes in split panes to update border,
        status bar, and property/format docks."""
        if event.type() == qt.QEvent.Type.FocusIn:
            idx = self._tabwidget.currentIndex()
            if idx >= 0 and idx < len(self._tabs):
                state = self._tabs[idx]
                if state.get('split') is not None:
                    primary = state['plot']
                    secondary = state.get('split_secondary')
                    focused = None
                    other = None
                    if obj is primary:
                        focused, other = primary, secondary
                    elif obj is secondary:
                        focused, other = secondary, primary

                    if focused is not None:
                        # remember last-focused pane
                        self._lastFocusedSplitPane = focused
                        # visual feedback
                        focused.setStyleSheet(
                            'PlotWindow { border: %s; }'
                            % self._splitFocusBorder)
                        if other:
                            other.setStyleSheet(
                                'PlotWindow { border: %s; }'
                                % self._splitNoBorder)
                        # status bar zoom
                        self.slotUpdateZoom(focused.zoomfactor)
                        # update page display
                        self.slotUpdatePage(focused.pagenumber)
                        # sync property/format docks to focused pane's
                        # selected widgets
                        sel = focused.lastwidgetsselected
                        if sel:
                            for w in sel:
                                self.treeedit.selectWidget(w)
        return super().eventFilter(obj, event)

    def _slotCloseTab(self, index):
        """Close a tab. Ask to save if modified."""
        if index < 0 or index >= len(self._tabs):
            return

        state = self._tabs[index]
        doc = state['document']

        if doc.isModified():
            # ask to save
            name = os.path.basename(state['filename']) or state.get('untitled_label', _('Untitled'))
            retn = qt.QMessageBox.warning(
                self, _('Close tab'),
                _('Save changes to "%s"?') % name,
                qt.QMessageBox.StandardButton.Save |
                qt.QMessageBox.StandardButton.Discard |
                qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Save)
            if retn == qt.QMessageBox.StandardButton.Cancel:
                return
            if retn == qt.QMessageBox.StandardButton.Save:
                # temporarily switch to this tab to save
                old = self._tabwidget.currentIndex()
                self._tabwidget.setCurrentIndex(index)
                self.slotFileSave()
                if old != index:
                    self._tabwidget.setCurrentIndex(old)

        # clean up split view if active
        if state.get('split') is not None:
            sec = state.get('split_secondary')
            if sec is not None:
                sec.rendercontrol.exitThreads()
                sec.deleteLater()
            state['split'].deleteLater()

        state['plot'].rendercontrol.exitThreads()

        self._tabs.pop(index)
        self._tabwidget.removeTab(index)

        # if no tabs left, show empty state and clear panels
        if len(self._tabs) == 0:
            self._disconnectTabSignals()
            self._clearPanels()
            self._showEmptyState()

    def _clearPanels(self):
        """Clear all panels when no document is open."""
        # create a blank document for the tree
        blank = document.Document()
        treemodel = treeeditwindow.WidgetTreeModel(blank)
        self.treeedit.setDocument(blank, treemodel)
        # clear properties and formatting
        self.propdock._lastSetnsproxy = None
        self.propdock.proplist.updateProperties(None, showformatting=False)
        self.formatdock._lastWidgetIds = None
        if self.formatdock.tabwidget:
            old = self.formatdock.layout.takeAt(0)
            if old and old.widget():
                old.widget().deleteLater()
            self.formatdock.tabwidget = None
        # clear data navigator
        self.datadock.setDocument(blank)

    def _showEmptyState(self):
        """Show a placeholder when no tabs are open."""
        if hasattr(self, '_emptyWidget') and self._emptyWidget is not None:
            self._emptyWidget.show()
            return

        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)
        layout.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)

        # logo
        logo = qt.QLabel()
        pix = utils.getPixmap('plotex_logo.png')
        scaled = pix.scaled(
            80, 80,
            qt.Qt.AspectRatioMode.KeepAspectRatio,
            qt.Qt.TransformationMode.SmoothTransformation)
        logo.setPixmap(scaled)
        logo.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        hint = qt.QLabel(
            _('Create or open a document to get started\n'
              'or drag a .vsz file here'))
        hint.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet('color: #888; font-size: 12px;')
        layout.addWidget(hint)

        w.setStyleSheet('background-color: #e8e8e8;')
        w.setAcceptDrops(True)
        w.dragEnterEvent = self.dragEnterEvent
        w.dropEvent = self.dropEvent
        self._emptyWidget = w
        self._tabwidget.addTab(w, '')
        self._tabwidget.setTabsClosable(False)

    def _hideEmptyState(self):
        """Remove the empty placeholder if present."""
        if hasattr(self, '_emptyWidget') and self._emptyWidget is not None:
            idx = self._tabwidget.indexOf(self._emptyWidget)
            if idx >= 0:
                self._tabwidget.removeTab(idx)
            self._emptyWidget = None
            self._tabwidget.setTabsClosable(True)

    def _newTab(self, filename=None, mode='graph'):
        """Create a new tab with a fresh document."""
        self._hideEmptyState()
        doc = document.Document()
        # only pass menu for the very first PlotWindow (avoids duplicating
        # menu items when opening additional tabs)
        first = len(self._tabs) == 0
        plot = plotwindow.PlotWindow(
            doc, self, menu=self.menus['view'] if first else None)
        state = self._addTabState(doc, plot, filename or '')

        if filename:
            # load file into the new tab's document
            self.openFileInWindow(filename)
        else:
            state['docsetup'] = False
            self.documentsetup = False
            self.setupDefaultDoc(mode)
            state['docsetup'] = True

        self.treeedit.doInitialWidgetSelect()

    def _updateTabLabel(self):
        """Update the current tab's label from filename."""
        idx = self._tabwidget.currentIndex()
        if idx >= 0 and idx < len(self._tabs):
            state = self._tabs[idx]
            name = os.path.basename(state['filename']) or state.get('untitled_label', _('Untitled'))
            if self.document.isModified():
                name = '* ' + name
            self._tabwidget.setTabText(idx, name)

    def updateStatusbar(self, text):
        '''Display text for a set period.'''
        self.statusBar().showMessage(text, 2000)

    def dragEnterEvent(self, event):
        """Check whether event is valid to be dropped."""
        if event.mimeData().hasUrls() and self._getPlotexDropFiles(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Respond to a drop event on the current window."""
        if event.mimeData().hasUrls():
            files = self._getPlotexDropFiles(event)
            for filename in files:
                self.openFile(filename)

    def _getPlotexDropFiles(self, event):
        """Return a list of Plotex files from a drag/drop event containing a
        text/uri-list"""

        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        else:
            # get list of supported files dropped
            urls = [u.toLocalFile() for u in mime.urls()]
            supported = {'.vsz', '.vszh5', '.h5', '.hdf5', '.he5'}
            urls = [u for u in urls
                    if os.path.splitext(u)[1].lower() in supported]
            return urls

    def setupDefaultDoc(self, mode):
        """Setup default document."""

        if not self.documentsetup:
            # add page and default graph
            self.document.makeDefaultDoc(mode)

            # set color theme
            self.document.basewidget.settings.get(
                'colorTheme').set(setting.settingdb['colortheme_default'])

            # load defaults if set
            self.loadDefaultStylesheet()
            self.loadDefaultCustomDefinitions()

            # done setup
            self.documentsetup = True

    def loadDefaultStylesheet(self):
        """Loads the default stylesheet for the new document."""
        filename = setdb['stylesheet_default']
        if filename:
            try:
                self.document.applyOperation(
                    document.OperationLoadStyleSheet(filename) )
            except EnvironmentError as e:
                qt.QMessageBox.warning(
                    self, _("Error - Plotex"),
                    _("Unable to load default stylesheet '%s'\n\n%s") %
                    (filename, e.strerror))
            else:
                # reset any modified flag
                self.document.setModified(False)
                self.document.changeset = 0

    def loadDefaultCustomDefinitions(self):
        """Loads the custom definitions for the new document."""
        filename = setdb['custom_default']
        if filename:
            try:
                self.document.applyOperation(
                    document.OperationLoadCustom(filename) )
            except EnvironmentError as e:
                qt.QMessageBox.warning(
                    self, _("Error - Plotex"),
                    _("Unable to load custom definitions '%s'\n\n%s") %
                    (filename, e.strerror))
            else:
                # reset any modified flag
                self.document.setModified(False)
                self.document.changeset = 0

    def slotAboutToShowEdit(self):
        """Enable/disable undo/redo menu items."""

        # enable distable, and add appropriate text to describe
        # the operation being undone/redone
        canundo = self.document.canUndo()
        undotext = _('Undo')
        if canundo:
            undotext = "%s %s" % (undotext, self.document.historyundo[-1].descr)
        self.vzactions['edit.undo'].setText(undotext)
        self.vzactions['edit.undo'].setEnabled(canundo)

        canredo = self.document.canRedo()
        redotext = _('Redo')
        if canredo:
            redotext = "%s %s" % (redotext, self.document.historyredo[-1].descr)
        self.vzactions['edit.redo'].setText(redotext)
        self.vzactions['edit.redo'].setEnabled(canredo)

    def slotEditUndo(self):
        """Undo the previous operation"""
        if self.document.canUndo():
            self.document.undoOperation()
        self.treeedit.checkWidgetSelected()

    def slotEditRedo(self):
        """Redo the previous operation"""
        if self.document.canRedo():
            self.document.redoOperation()

    def slotEditPreferences(self):
        from ..dialogs.preferences import PreferencesDialog
        dialog = PreferencesDialog(self)
        dialog.exec()

    def slotEditStylesheet(self):
        from ..dialogs.stylesheet import StylesheetDialog
        dialog = StylesheetDialog(self, self.document)
        self.showDialog(dialog)
        return dialog

    def slotEditCustom(self):
        from ..dialogs.custom import CustomDialog
        dialog = CustomDialog(self, self.document)
        self.showDialog(dialog)
        return dialog

    def slotCopyAsPNG(self):
        """Copy current page as PNG bitmap to clipboard."""
        if self.plot.painthelper is None:
            return
        pixmap = self.plot.pixmapitem.pixmap()
        if not pixmap.isNull():
            qt.QApplication.clipboard().setPixmap(pixmap)

    def definePlugins(self, pluginlist, actions, menuname):
        """Create menu items and actions for plugins.

        pluginlist: list of plugin classes
        actions: dict of actions to add new actions to
        menuname: string giving prefix for new menu entries (inside actions)
        """

        def getLoadDialog(pluginkls):
            def _loadPlugin():
                from ..dialogs.plugin import handlePlugin
                handlePlugin(self, self.document, pluginkls)
            return _loadPlugin

        menu = []
        for pluginkls in pluginlist:
            actname = menuname + '.' + '.'.join(pluginkls.menu)
            text = pluginkls.menu[-1]
            if pluginkls.has_parameters:
                text += '…'
            actions[actname] = utils.makeAction(
                self,
                pluginkls.description_short,
                text,
                getLoadDialog(pluginkls))

            # build up menu from tuple of names
            menulook = menu
            namebuild = [menuname]
            for cmpt in pluginkls.menu[:-1]:
                namebuild.append(cmpt)
                name = '.'.join(namebuild)

                for c in menulook:
                    if c[0] == name:
                        menulook = c[2]
                        break
                else:
                    menulook.append( [name, cmpt, []] )
                    menulook = menulook[-1][2]

            menulook.append(actname)

        return menu

    def _defineMenus(self):
        """Initialise the menus and toolbar."""

        # these are actions for main menu toolbars and menus
        a = utils.makeAction
        self.vzactions = {
            'file.new.menu':
                a(self, _('New document'), _('New'),
                  None,
                  icon='kde-document-new'),
            'file.new.graph':
                a(self,
                  _('New graph document'),
                  _('&New graph document'),
                  self.slotFileNewGraph,
                  icon='kde-document-new-graph', key='Ctrl+N'),
            'file.new.polar':
                a(self,
                  _('New polar plot document'),
                  _('New polar document'),
                  self.slotFileNewPolar,
                  icon='kde-document-new-polar'),
            'file.new.ternary':
                a(self,
                  _('New ternary plot document'),
                  _('New ternary document'),
                  self.slotFileNewTernary,
                  icon='kde-document-new-ternary'),
            'file.new.graph3d':
                a(self,
                  _('New 3D plot document'),
                  _('New 3D document'),
                  self.slotFileNewGraph3D,
                  icon='kde-document-new-graph3d'),

            'file.open':
                a(self, _('Open a document'), _('&Open…'),
                  self.slotFileOpen,
                  icon='kde-document-open', key='Ctrl+O'),
            'file.reload':
                a(self, _('Reload document from saved version'),
                  _('Reload…'), self.slotFileReload),
            'file.save':
                a(self, _('Save the document'), _('&Save'),
                  self.slotFileSave,
                  icon='kde-document-save', key='Ctrl+S'),
            'file.saveas':
                a(self, _('Save the current document under a new name'),
                  _('Save &As…'), self.slotFileSaveAs,
                  icon='kde-document-save-as'),
            'file.trust':
                a(self, _('Trust document contents'), _('Trust…'),
                  self.slotFileTrust),
            'file.print':
                a(self, _('Print the document'), _('&Print…'),
                  self.slotFilePrint,
                  icon='kde-document-print', key='Ctrl+P'),
            'file.export':
                a(self, _('Export to graphics formats'), _('&Export…'),
                  self.slotFileExport,
                  icon='kde-document-export', key='Ctrl+Shift+E'),
            'file.close':
                a(self, _('Close current window'), _('Close Window'),
                  self.slotFileClose,
                  icon='kde-window-close', key='Ctrl+W'),
            'file.quit':
                a(self, _('Exit the program'), _('&Quit'),
                  self.slotFileQuit,
                  icon='kde-application-exit', key='Ctrl+Q'),

            'edit.undo':
                a(self, _('Undo the previous operation'), _('Undo'),
                  self.slotEditUndo,
                  icon='kde-edit-undo',  key='Ctrl+Z'),
            'edit.redo':
                a(self, _('Redo the previous operation'), _('Redo'),
                  self.slotEditRedo,
                  icon='kde-edit-redo', key='Ctrl+Shift+Z'),
            'edit.prefs':
                a(self, _('Edit preferences'), _('&Preferences…'),
                  self.slotEditPreferences,
                  icon='veusz-preferences', key='Ctrl+,'),
            'edit.custom':
                a(self,
                  _('Edit custom functions, constants, colors and colormaps'),
                  _('Custom definitions…'),
                  self.slotEditCustom,
                  icon='veusz-edit-custom'),

            'edit.stylesheet':
                a(self,
                  _('Edit stylesheet to change default widget settings'),
                  _('Default styles…'),
                  self.slotEditStylesheet, icon='veusz-styles'),

            'edit.copy_as_png':
                a(self, _('Copy current page as PNG bitmap (for PowerPoint)'),
                  _('Copy as &PNG'),
                  self.slotCopyAsPNG,
                  icon='kde-edit-copy', key='Ctrl+Shift+C'),

            'view.edit':
                a(self, _('Show or hide edit window'), _('Edit window'),
                  None, checkable=True),
            'view.props':
                a(self, _('Show or hide property window'), _('Properties window'),
                  None, checkable=True),
            'view.format':
                a(self, _('Show or hide formatting window'), _('Formatting window'),
                  None, checkable=True),
            'view.console':
                a(self, _('Show or hide console window'), _('Console'),
                  None, icon='veusz-console', checkable=True),
            'view.datanav':
                a(self, _('Show or hide data navigator window'), _('Data navigator window'),
                  None, checkable=True),

            'view.ribbon':
                a(self, _('Show or hide ribbon'), _('Ribbon'),
                  None, checkable=True),

            'view.guides':
                a(self, _('Show or hide alignment guides'), _('Show guides'),
                  self.slotToggleGuides, icon='guide_show', checkable=True),
            'view.addHGuide':
                a(self, _('Add horizontal guide at page center'),
                  _('Add H guide'), self.slotAddHGuide, icon='guide_addh'),
            'view.addVGuide':
                a(self, _('Add vertical guide at page center'),
                  _('Add V guide'), self.slotAddVGuide, icon='guide_addv'),
            'view.clearGuides':
                a(self, _('Reset guides to center cross'), _('Reset guides'),
                  self.slotClearGuides, icon='guide_clear'),
            'view.rulers':
                a(self, _('Show or hide rulers'), _('Rulers'),
                  self.slotToggleRulers, icon='veusz-ruler', checkable=True),
            'view.importColormap':
                a(self, _('Import colormap from file (.txt, .gpl, .cpt)'),
                  _('Import colormap…'), self.slotImportColormap),
            'view.resetlayout':
                a(self, _('Reset dock panels to default layout'),
                  _('Reset Window Layout'), self.slotResetLayout),

            'view.printpreview':
                a(self, _('Preview the document before printing'),
                  _('Print preview'), self.slotPrintPreview,
                  icon='veusz-print-preview'),
            'view.splitH':
                a(self, _('Split view horizontally (top/bottom)'),
                  _('Horizontal'), self.slotToggleSplitH,
                  icon='veusz-split-horizontal', checkable=True),
            'view.splitV':
                a(self, _('Split view vertically (left/right)'),
                  _('Vertical'), self.slotToggleSplitV,
                  icon='veusz-split-vertical', checkable=True),

            'data.import':
                a(self, _('Import data into Plotex'), _('&Import…'),
                  self.slotDataImport, icon='kde-vzdata-import', key='Ctrl+I'),
            'data.edit':
                a(self, _('Edit and enter new datasets'), _('&Editor…'),
                  lambda: self.slotDataEdit(), icon='kde-edit-veuszedit', key='Ctrl+E'),
            'data.create':
                a(self, _('Create new datasets using ranges, parametrically or as functions of existing datasets'), _('&Create…'),
                  self.slotDataCreate, icon='kde-dataset-new-veuszedit'),
            'data.create2d':
                a(self, _('Create new 2D datasets from existing datasets, or as a function of x and y'), _('Create &2D…'),
                  self.slotDataCreate2D, icon='kde-dataset2d-new-veuszedit'),
            'data.capture':
                a(self, _('Capture remote data'), _('Ca&pture…'),
                  self.slotDataCapture, icon='veusz-capture-data'),
            'data.filter':
                a(self, _('Filter data'), _('&Filter…'),
                  self.slotDataFilter, icon='kde-filter'),
            'data.histogram':
                a(self, _('Histogram data'), _('&Histogram…'),
                  self.slotDataHistogram, icon='button_bar'),
            'data.reload':
                a(self, _('Reload linked datasets'), _('&Reload'),
                  self.slotDataReload, icon='kde-view-refresh', key='F5'),

            'help.home':
                a(self, _('Go to the Plotex home page on the internet'),
                  _('Home page'), self.slotHelpHomepage,
                  icon='kde-go-next'),
            'help.bug':
                a(self, _('Report a bug on the internet'),
                  _('Report bug'), self.slotHelpBug,
                  icon='kde-edit'),
            'help.update':
                a(self, _('Check for updates'),
                  _('Updates'), self.slotHelpUpdate,
                  icon='kde-go-down'),

            'help.tutorial':
                a(self, _('An interactive Plotex tutorial'),
                  _('Tutorial'), self.slotHelpTutorial,
                  icon='veusz-tutorial'),
            'help.about':
                a(self, _('Displays information about the program'), _('About'),
                  self.slotHelpAbout, icon='plotex'),
            'help.examples':
                a(self, _('Open example documents'),
                  _('Examples'), self.slotHelpExamples,
                  icon='kde-document-open'),

            'edit.commandpalette':
                a(self, _('Search and run any command'),
                  _('Command Palette'), self.slotCommandPalette,
                  key='Ctrl+K'),
        }

        # create menu group for file→new dropdown
        utils.makeMenuGroupSaved(
            'file.new.menu', self, self.vzactions, (
                'file.new.graph', 'file.new.graph3d',
                'file.new.polar', 'file.new.ternary',
            )
        )

        # create ribbon bar (populated later in _populateRibbon)
        self.ribbon = ribbon.RibbonBar(self)
        self._ribbon_toolbar = qt.QToolBar(_("Ribbon"), self)
        self._ribbon_toolbar.setObjectName('plotex_ribbon')
        self._ribbon_toolbar.setMovable(False)
        self._ribbon_toolbar.addWidget(self.ribbon)
        self.addToolBar(qt.Qt.ToolBarArea.TopToolBarArea, self._ribbon_toolbar)

        # menu structure — reorganized for clarity
        filemenu = [
            [
                'file.new', _('New'),
                [
                    'file.new.graph', 'file.new.graph3d', 'file.new.polar',
                    'file.new.ternary'
                ]
            ],
            'file.open',
            [
                'file.filerecent', _('Open &Recent'), []
            ],
            '',
            'file.save', 'file.saveas',
            '',
            'file.print', 'file.export',
            '',
            'edit.prefs',
            '',
            'file.close', 'file.quit'
        ]
        editmenu = [
            'edit.undo', 'edit.redo',
            '',
            'edit.commandpalette',
            '',
            ['edit.select', _('&Select'), []],
            '',
            'edit.custom', 'edit.stylesheet',
        ]
        viewmenu = [
            ['view.panels', _('&Panels'), [
                'view.edit', 'view.props', 'view.format',
                'view.console', 'view.datanav',
                '', 'view.ribbon',
            ]],
            ['view.splitmenu', _('&Split'), [
                'view.splitH', 'view.splitV',
            ]],
            ['view.guidesmenu', _('&Guides'), [
                'view.rulers',
                '', 'view.guides',
                'view.addHGuide', 'view.addVGuide', 'view.clearGuides',
            ]],
            '',
            'view.printpreview',
            'view.importColormap',
            '',
            'view.resetlayout',
        ]
        insertmenu = []  # populated later in _populateInsertMenu

        # load dataset plugins and create menu
        datapluginsmenu = self.definePlugins(
            plugins.datasetpluginregistry,
            self.vzactions, 'data.ops'
        )

        datamenu = [
            'data.import', 'data.edit', 'data.create',
            'data.create2d',
            '',
            'data.filter', 'data.histogram',
            '',
            'data.capture', 'data.reload',
            '',
            [
                'data.ops', _('&Plugins'), datapluginsmenu
            ],
        ]

        # load tools plugins and create menu
        toolsmenu = self.definePlugins(
            plugins.toolspluginregistry,
            self.vzactions, 'tools')

        helpmenu = [
            'help.tutorial',
            [
                'help.examples', _('&Example documents'), []
            ],
            '',
            'help.home', 'help.bug', 'help.update',
            '',
            'help.about'
        ]

        menus = [
            ['file', _('&File'), filemenu],
            ['edit', _('&Edit'), editmenu],
            ['view', _('&View'), viewmenu],
            ['insert', _('&Insert'), insertmenu],
            ['data', _('&Data'), datamenu],
            ['tools', _('&Tools'), toolsmenu],
            ['help', _('&Help'), helpmenu],
        ]

        self.menus = {}
        utils.constructMenus(self.menuBar(), self.menus, menus, self.vzactions)

        # set icon for File->New
        self.menus['file.new'].setIcon(utils.getIcon('kde-document-new'))

        # add color scheme submenu to View
        self._buildThemeMenu()
        self._buildPlotThemeMenu()

        self.populateExamplesMenu()

    def _buildThemeMenu(self):
        """Build theme submenu in View menu."""
        from ..dialogs.preferences import color_schemes
        thememenu = qt.QMenu(_('&Theme'), self)
        themegroup = qt.QActionGroup(self)
        current = setdb['color_scheme']
        for name, usertext in color_schemes:
            act = thememenu.addAction(usertext)
            act.setCheckable(True)
            act.setChecked(name == current)
            act.setData(name)
            themegroup.addAction(act)
        themegroup.triggered.connect(self._onThemeAction)
        self.menus['view'].addMenu(thememenu)

    def _onThemeAction(self, action):
        """Apply theme from View menu."""
        scheme = action.data()
        setdb['color_scheme'] = scheme
        app = qt.QApplication.instance()
        if hasattr(app, 'applyColorScheme'):
            app.applyColorScheme(scheme)

    def _buildPlotThemeMenu(self):
        """Build plot theme submenu for graph styling."""
        from ..utils.plotthemes import getThemeNames, applyTheme

        plotthememenu = qt.QMenu(_('Plot &Style'), self)

        for key, name, descr in getThemeNames():
            act = plotthememenu.addAction(name)
            act.setToolTip(descr)
            act.setStatusTip(descr)
            act.setData(key)

        def _onPlotTheme(action):
            applyTheme(self.document, action.data())

        plotthememenu.triggered.connect(_onPlotTheme)
        self.menus['view'].addMenu(plotthememenu)
        self._plotThemeMenu = plotthememenu

    def _populateRibbon(self):
        """Populate the ribbon bar with actions from all components."""
        acts = self.vzactions

        # --- Start (quick-access workflow tab) ---
        start = self.ribbon.addTab(_('Start'), 'start')

        g = start.addGroup(_('File'))
        g.addLargeButton(acts['file.new.menu'])
        openBtn = g.addLargeButton(acts['file.open'])
        if hasattr(openBtn, 'setMenu'):
            openBtn.setMenu(self.menus.get('file.filerecent'))
            openBtn.setPopupMode(
                qt.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        g.addLargeButton(acts['file.save'])
        g.addSmallColumn([acts['file.saveas'], acts['edit.prefs']])

        g = start.addGroup(_('Data'))
        g.addLargeButton(acts['data.import'])
        g.addSmallColumn([acts['data.reload']])

        g = start.addGroup(_('Create'))
        g.addLargeButton(acts['add.graph'])
        g.addSmallColumn([acts['add.page'], acts['add.grid']])

        g = start.addGroup(_('Plots'))
        g.addLargeButton(acts['add.xy'])
        g.addSmallColumn([
            acts['add.bar'], acts['add.histo'],
            acts['add.function']])
        g.addSmallColumn([
            acts['add.boxplot'], acts['add.fit'],
            acts['add.violin']])

        g = start.addGroup(_('Edit'))
        g.addLargeButton(acts['edit.undo'])
        g.addLargeButton(acts['edit.redo'])
        self._undoAction = acts['edit.undo']
        self._redoAction = acts['edit.redo']

        g = start.addGroup(_('Output'))
        g.addLargeButton(acts['file.export'])
        g.addSmallColumn([
            acts['file.print'], acts['edit.copy_as_image'],
            acts['edit.copy_as_png']])

        # --- Edit (clipboard, widgets, annotations, style) ---
        edit = self.ribbon.addTab(_('Edit'), 'edit')

        g = edit.addGroup(_('Clipboard'))
        g.addLargeButton(acts['edit.cut'])
        g.addLargeButton(acts['edit.copy'])
        g.addLargeButton(acts['edit.paste'])

        g = edit.addGroup(_('Widgets'))
        g.addSmallColumn([acts['edit.delete'], acts['edit.rename'],
                          acts['edit.show']])
        g.addSmallColumn([acts['edit.moveup'], acts['edit.movedown'],
                          acts['edit.hide']])

        g = edit.addGroup(_('Style'))
        g.addLargeButton(acts['edit.stylesheet'])
        plotStyleBtn = qt.QPushButton(_('Plot Style'))
        plotStyleBtn.setMenu(self._plotThemeMenu)
        plotStyleBtn.setIcon(utils.getIcon('veusz-styles'))
        g.layout().addWidget(plotStyleBtn)

        # --- Insert ---
        ins = self.ribbon.addTab(_('Insert'), 'insert')

        g = ins.addGroup(_('Layout'))
        g.addSmallColumn([
            acts['add.page'], acts['add.grid'], acts['add.graph']])

        g = ins.addGroup(_('Plots'))
        g.addLargeButton(acts['add.xy'])
        g.addSmallColumn([
            acts['add.bar'], acts['add.histo'],
            acts['add.function']])
        g.addSmallColumn([
            acts['add.boxplot'], acts['add.violin'],
            acts['add.fit']])
        g.addSmallColumn([
            acts['add.piechart'], acts['add.heatmap'],
            acts['add.image']])

        g = ins.addGroup(_('Statistics'))
        g.addSmallColumn([
            acts['add.pareto'], acts['add.qqplot'],
            acts['add.ridgeline']])

        g = ins.addGroup(_('Clinical'))
        g.addSmallColumn([
            acts['add.blandaltman'], acts['add.kaplanmeier'],
            acts['add.roccurve']])
        g.addSmallColumn([
            acts['add.polartrending'], acts['add.covariance'],
            acts['add.contour']])

        g = ins.addGroup(_('More'))
        g.addSmallColumn([
            acts['add.polar'], acts['add.ternary'],
            acts['add.vectorfield']])
        g.addSmallColumn([
            acts['add.scene3d'], acts['add.graph3d'],
            acts['add.nonorthpoint']])

        g = ins.addGroup(_('Annotations'))
        g.addSmallColumn([
            acts['add.key'], acts['add.label'],
            acts['add.colorbar']])
        g.addSmallColumn([
            acts['add.bracket'], acts['add.axismenu'],
            acts['add.shapemenu']])

        # --- Data ---
        data = self.ribbon.addTab(_('Data'), 'data')

        g = data.addGroup(_('Import'))
        g.addLargeButton(acts['data.import'])
        g.addLargeButton(acts['file.print'])

        g = data.addGroup(_('Datasets'))
        g.addLargeButton(acts['data.edit'])
        g.addLargeButton(acts['data.create'])
        g.addSmallColumn([acts['data.create2d']])

        g = data.addGroup(_('Analysis'))
        g.addLargeButton(acts['data.filter'])
        g.addLargeButton(acts['data.histogram'])

        g = data.addGroup(_('Live'))
        g.addLargeButton(acts['data.capture'])
        g.addLargeButton(acts['data.reload'])

        # --- View ---
        view = self.ribbon.addTab(_('View'), 'view')

        g = view.addGroup(_('Interact'))
        g.addLargeButton(acts['view.select'])
        g.addLargeButton(acts['view.pick'])

        g = view.addGroup(_('Graph Axes'))
        g.addLargeButton(acts['view.graphzoom'])
        g.addLargeButton(acts['view.graphzoomout'])
        g.addSmallColumn([
            acts['view.graphrecenter'],
            acts['view.graphreset']])

        g = view.addGroup(_('Pages'))
        g.addLargeButton(acts['view.prevpage'])
        g.addLargeButton(acts['view.nextpage'])
        g.addLargeButton(acts['view.printpreview'])

        g = view.addGroup(_('Split'))
        g.addLargeButton(acts['view.splitH'])
        g.addLargeButton(acts['view.splitV'])

        g = view.addGroup(_('Guides'))
        g.addLargeButton(acts['view.rulers'])
        g.addSmallColumn([
            acts['view.guides'], acts['view.addHGuide'],
            acts['view.addVGuide']])
        g.addSmallColumn([acts['view.clearGuides']])

        g = view.addGroup(_('Panels'))
        g.addLargeButton(acts['view.console'])
        g.addSmallColumn([
            acts['view.datanav'],
            acts['view.resetlayout']])

        # --- Help ---
        hlp = self.ribbon.addTab(_('Help'), 'help')

        g = hlp.addGroup(_('Learn'))
        g.addLargeButton(acts['help.about'])
        g.addLargeButton(acts['help.tutorial'])
        g.addLargeButton(acts['help.examples'])

        g = hlp.addGroup(_('Online'))
        g.addSmallColumn([acts['help.home'], acts['help.bug'],
                          acts['help.update']])

    def _setPickerFont(self, label):
        f = label.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.2)
        label.setFont(f)

    def populateExamplesMenu(self):
        """Add examples to help menu, grouped by category."""

        examples = [
            os.path.join(utils.exampleDirectory, f)
            for f in os.listdir(str(utils.exampleDirectory))
            if os.path.splitext(f)[1] == ".vsz"
        ]

        # categorize examples by name patterns
        categories = {
            _('Statistical'): {
                'boxplot', 'violin_plot', 'histo', 'histo_widget',
                'histogramming', 'pareto', 'qqplot', 'ridgeline',
                'heatmap', 'fit',
            },
            _('Clinical'): {
                'FDR_example', 'bland_altman', 'roc_curve',
                'kaplan_meier',
            },
            _('3D'): {
                '3d_errors', '3d_function', '3d_points',
                '3d_surface', '3d_volume',
            },
            _('Special'): {
                'polar', 'ternary', 'contour', 'contour_labels',
                'vectorfield', 'piechart', 'starchart',
            },
            _('Data & Import'): {
                'example_csv', 'example_import', 'dataset_operations',
                'dsexpressions', 'linked_datasets', 'filtered',
                'custom_definitions', 'nd',
            },
        }

        # build reverse map: filename → category
        file_to_cat = {}
        for cat, names in categories.items():
            for n in names:
                file_to_cat[n] = cat

        menu = self.menus["help.examples"]
        submenus = {}
        uncategorized = []

        for ex in sorted(examples):
            name = os.path.splitext(os.path.basename(ex))[0]

            def _openexample(ex=ex):
                self.openFile(ex)

            cat = file_to_cat.get(name)
            if cat:
                if cat not in submenus:
                    submenus[cat] = menu.addMenu(cat)
                a = submenus[cat].addAction(name, _openexample)
            else:
                uncategorized.append((name, _openexample))

        # add uncategorized under "Basic" or directly
        if uncategorized:
            sub = menu.addMenu(_('Basic'))
            for name, fn in uncategorized:
                sub.addAction(name, fn)

    def defineViewWindowMenu(self):
        """Setup View -> Window menu."""

        def viewHideWindow(window):
            """Toggle window visibility."""
            w = window
            def f():
                w.setVisible(not w.isVisible())
            return f

        # set whether windows are visible and connect up to toggle windows
        self._initConsole()
        self.viewwinfns = []
        for win, act in (
                (self.treeedit, 'view.edit'),
                (self.propdock, 'view.props'),
                (self.formatdock, 'view.format'),
                (self._console, 'view.console'),
                (self.datadock, 'view.datanav'),
                (self._ribbon_toolbar, 'view.ribbon'),
        ):

            a = self.vzactions[act]
            fn = viewHideWindow(win)
            self.viewwinfns.append( (win, a, fn) )
            a.triggered.connect(fn)

        # needs to update state every time menu is shown
        self.menus['view'].aboutToShow.connect(
            self.slotAboutToShowViewWindow)

    def slotAboutToShowViewWindow(self):
        """Enable/disable View->Window item check boxes."""

        for win, act, fn in self.viewwinfns:
            act.setChecked(not win.isHidden())

    def showDialog(self, dialog):
        """Show dialog given."""
        dialog.dialogFinished.connect(self.deleteDialog)
        self.dialogs.append(dialog)
        dialog.show()
        self.dialogShown.emit(dialog)

    def deleteDialog(self, dialog):
        """Remove dialog from list of dialogs."""
        try:
            idx = self.dialogs.index(dialog)
            del self.dialogs[idx]
        except ValueError:
            pass

    def slotDataImport(self):
        """Display the import data dialog."""
        from ..dialogs import importdialog
        dialog = importdialog.ImportDialog(self, self.document)
        self.showDialog(dialog)
        return dialog

    def slotDataEdit(self, editdataset=None):
        """Edit existing datasets.

        If editdataset is set to a dataset name, edit this dataset
        """
        from ..dialogs import dataeditdialog
        dialog = dataeditdialog.DataEditDialog(self, self.document)
        self.showDialog(dialog)
        if editdataset is not None:
            dialog.selectDataset(editdataset)
        return dialog

    def slotDataCreate(self):
        """Create new datasets."""
        from ..dialogs.datacreate import DataCreateDialog
        dialog = DataCreateDialog(self, self.document)
        self.showDialog(dialog)
        return dialog

    def slotDataCreate2D(self):
        """Create new datasets."""
        from ..dialogs.datacreate2d import DataCreate2DDialog
        dialog = DataCreate2DDialog(self, self.document)
        self.showDialog(dialog)
        return dialog

    def slotDataCapture(self):
        """Capture remote data."""
        from ..dialogs.capturedialog import CaptureDialog
        dialog = CaptureDialog(self.document, self)
        self.showDialog(dialog)
        return dialog

    def slotDataFilter(self):
        """Filter datasets."""
        from ..dialogs.filterdialog import FilterDialog
        dialog = FilterDialog(self, self.document)
        self.showDialog(dialog)
        return dialog

    def slotDataHistogram(self):
        """Histogram data."""
        from ..dialogs.histodata import HistoDataDialog
        dialog = HistoDataDialog(self, self.document)
        self.showDialog(dialog)
        return dialog

    def slotDataReload(self):
        """Reload linked datasets."""
        from ..dialogs.reloaddata import ReloadData
        dialog = ReloadData(self.document, self)
        self.showDialog(dialog)
        return dialog

    def slotHelpExamples(self):
        """Show examples menu as a popup at the ribbon button."""
        menu = self.menus.get("help.examples")
        if menu:
            menu.exec(qt.QCursor.pos())

    def slotHelpHomepage(self):
        """Go to the veusz homepage."""
        qt.QDesktopServices.openUrl(qt.QUrl('https://veusz.github.io/'))

    def slotHelpBug(self):
        """Go to the veusz bug page."""
        qt.QDesktopServices.openUrl(
            qt.QUrl('https://github.com/veusz/veusz/issues') )

    def askTutorial(self):
        """Ask if tutorial wanted."""
        retn = qt.QMessageBox.question(
            self, _("Plotex Tutorial"),
            _("Plotex includes a tutorial to help get you started.\n"
              "Would you like to start the tutorial now?\n"
              "If not, you can access it later through the Help menu."),
            qt.QMessageBox.StandardButton.Yes |
            qt.QMessageBox.StandardButton.No
        )

        if retn == qt.QMessageBox.StandardButton.Yes:
            self.slotHelpTutorial()

    def slotHelpTutorial(self):
        """Show a Plotex tutorial."""
        if self.document.isBlank():
            # run the tutorial
            from .tutorial import TutorialDock
            tutdock = TutorialDock(self.document, self, self)
            self.addDockWidget(
                qt.Qt.DockWidgetArea.RightDockWidgetArea, tutdock)
            tutdock.show()
        else:
            # open up a blank window for tutorial
            win = self.CreateWindow()
            win.slotHelpTutorial()

    def slotCommandPalette(self):
        """Open command palette for quick action access."""
        from .commandpalette import CommandPalette
        # merge mainwindow actions with treeedit actions
        allactions = dict(self.vzactions)
        palette = CommandPalette(allactions, self)
        palette.exec()

    def slotHelpAbout(self):
        """Show about dialog."""
        from ..dialogs.aboutdialog import AboutDialog
        AboutDialog(self).exec()

    def askVersionCheck(self, mininterval=2):
        """Check with user whether to do version checks.

        This is only done after the user has been using the program
        for mininterval days

        """

        dayssinceinstall = (
            datetime.date.today() -
            datetime.date(*setting.settingdb['install_date'])).days
        if ( dayssinceinstall<mininterval or
             setting.settingdb['vercheck_asked_user'] or
             setting.settingdb['vercheck_disabled'] or
             utils.disableVersionChecks ):
            return

        retn = qt.QMessageBox.question(
            self, _("Version check"),
            _("Plotex will periodically check for new versions and\n"
              "let you know if there is a new one available.\n\n"
              "Is this ok? This choice can be changed in Preferences."),
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
            qt.QMessageBox.StandardButton.Yes
        )

        setting.settingdb['vercheck_disabled'] = retn==qt.QMessageBox.StandardButton.No
        setting.settingdb['vercheck_asked_user'] = True

    def doVersionCheck(self):
        """Check whether there is a new version.
        """
        self.vzactions['help.update'].setVisible(False)

        # check is done asynchronously
        thread = utils.VersionCheckThread(self)
        thread.newversion.connect(self.slotNewVersion)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def askFeedbackCheck(self, mininterval=3):
        """Check with user whether to do feedback.

        This is only done after the user has been using the program
        for mininterval days

        """

        dayssinceinstall = (
            datetime.date.today() -
            datetime.date(*setting.settingdb['install_date'])).days
        if ( dayssinceinstall<mininterval or
             setting.settingdb['feedback_asked_user'] or
             setting.settingdb['feedback_disabled'] or
             utils.disableFeedback ):
            return

        retn = qt.QMessageBox.question(
            self, _("Send automatic anonymous feedback"),
            _("Plotex can automatically send anonymous feedback "
              "to the developers, with information about the version "
              "of software dependencies, the computer language and how "
              "often features are used.\n\n"
              "Is this ok? This choice can be changed in Preferences."),
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
            qt.QMessageBox.StandardButton.Yes
        )

        setting.settingdb['feedback_disabled'] = retn==qt.QMessageBox.StandardButton.No
        setting.settingdb['feedback_asked_user'] = True

    def doFeedback(self):
        """Give feedback."""
        thread = utils.FeedbackCheckThread(self)
        thread.start()

    def slotNewVersion(self, ver):
        """Called when there is a new version."""
        msg = _('Plotex %s is available for download - see Help menu') % ver
        self.statusBar().showMessage(msg, 5000)
        self.vzactions['help.update'].setText(
            _('Download new Plotex %s') % ver)
        self.vzactions['help.update'].setVisible(True)

    def slotHelpUpdate(self):
        """Open web page to update."""
        qt.QDesktopServices.openUrl(qt.QUrl(
            'https://veusz.github.io/download/'))

    def queryOverwrite(self):
        """Do you want to overwrite the current document.

        Returns qt.QMessageBox.(Yes,No,Cancel)."""

        # include filename in mesage box if we can
        filetext = ''
        if self.filename:
            filetext = " '%s'" % os.path.basename(self.filename)

        return qt.QMessageBox.warning(
            self,
            _("Save file?"),
            _("Document%s was modified. Save first?") % filetext,
            qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard |
            qt.QMessageBox.StandardButton.Cancel
        )

    def closeEvent(self, event):
        """Before closing, check all tabs for unsaved changes."""

        discard_all = False
        for i, state in enumerate(self._tabs):
            doc = state['document']
            if doc.isModified() and not discard_all:
                name = os.path.basename(state['filename']) or state.get('untitled_label', _('Untitled'))
                msgbox = qt.QMessageBox(
                    qt.QMessageBox.Icon.Warning,
                    _('Close'),
                    _('Save changes to "%s"?') % name,
                    qt.QMessageBox.StandardButton.Save |
                    qt.QMessageBox.StandardButton.Discard |
                    qt.QMessageBox.StandardButton.Cancel,
                    self)
                msgbox.setDefaultButton(
                    qt.QMessageBox.StandardButton.Save)
                # count remaining unsaved tabs
                unsaved = sum(
                    1 for s in self._tabs[i:]
                    if s['document'].isModified())
                if unsaved > 1:
                    discard_all_btn = msgbox.addButton(
                        _('Discard all'), qt.QMessageBox.ButtonRole.DestructiveRole)
                else:
                    discard_all_btn = None
                v = msgbox.exec()
                clicked = msgbox.clickedButton()
                if clicked is discard_all_btn:
                    discard_all = True
                elif v == qt.QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
                elif v == qt.QMessageBox.StandardButton.Save:
                    old = self._tabwidget.currentIndex()
                    self._tabwidget.setCurrentIndex(i)
                    self.slotFileSave()
                    if old != i:
                        self._tabwidget.setCurrentIndex(old)

        # store working directory
        setdb['dirname'] = self.dirname

        # store the current geometry in the settings database
        setdb['geometry_maximized'] = self.isMaximized()
        if not self.isMaximized():
            geometry = ( self.x(), self.y(), self.width(), self.height() )
            setdb['geometry_mainwindow'] = geometry

        # store docked windows (base64 for reliable QSettings storage)
        import base64
        data = self.saveState().data()
        setdb['geometry_mainwindowstate_b64'] = base64.b64encode(
            bytes(data)).decode('ascii')

        # save current setting db
        setdb.writeSettings()

        event.accept()

    def _centerOnScreen(self):
        """Center the window on the current screen."""
        screen = self.screen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2)

    def setupWindowGeometry(self):
        """Restoring window geometry if possible."""

        # count number of main windows shown
        nummain = 0
        for w in qt.QGuiApplication.topLevelWindows():
            if isinstance(w, qt.QMainWindow):
                nummain += 1

        # if we can restore the geometry, do so
        if 'geometry_mainwindow' in setdb:
            geometry = setdb['geometry_mainwindow']
            self.resize( qt.QSize(geometry[2], geometry[3]) )
            if nummain <= 1:
                geomrect = self.screen().geometry()
                newpos = qt.QPoint(geometry[0], geometry[1])
                if geomrect.contains(newpos):
                    self.move(newpos)
                else:
                    self._centerOnScreen()
        else:
            self.resize(1200, 800)
            self._centerOnScreen()

        # restore maximized state, or maximize by default on first run
        if setdb.get('geometry_maximized', True):
            self.showMaximized()

        # restore docked window geometry
        import base64
        state_data = None
        if 'geometry_mainwindowstate_b64' in setdb:
            try:
                state_data = base64.b64decode(
                    setdb['geometry_mainwindowstate_b64'])
            except Exception:
                pass
        elif 'geometry_mainwindowstate' in setdb:
            # legacy fallback
            try:
                state_data = setdb['geometry_mainwindowstate']
            except Exception:
                pass
        if state_data is not None:
            try:
                self.restoreState(qt.QByteArray(state_data))
            except Exception:
                pass

    def _ensureCenterGuides(self, pw):
        """Ensure the center cross guides exist."""
        if pw.painthelper:
            cx = pw.painthelper.pagesize[0] / 2
            cy = pw.painthelper.pagesize[1] / 2
            if not pw.guides:
                pw.guides.append(('h', cy))
                pw.guides.append(('v', cx))

    def slotToggleRulers(self, checked):
        """Toggle ruler visibility on the current plot window."""
        pw = self._currentPlotWindow()
        if pw:
            pw.rulers_visible = checked
            pw.viewport().update()
            # also apply to secondary split pane
            idx = self._tabwidget.currentIndex()
            if idx >= 0 and idx < len(self._tabs):
                sec = self._tabs[idx].get('split_secondary')
                if sec is not None:
                    sec.rulers_visible = checked
                    sec.viewport().update()

    def slotToggleGuides(self, checked):
        """Toggle guide visibility. Preserves guide positions."""
        pw = self._currentPlotWindow()
        if pw:
            pw.guides_visible = checked
            if checked:
                self._ensureCenterGuides(pw)
            pw.updateGuideItems()

    def slotAddHGuide(self, checked=False):
        """Add horizontal guide offset from center."""
        pw = self._currentPlotWindow()
        if pw and pw.painthelper:
            ph = pw.painthelper.pagesize[1]
            # count existing H guides to offset each new one
            nh = sum(1 for o, _ in pw.guides if o == 'h')
            cy = ph * (0.25 + 0.1 * (nh - 1)) if nh > 0 else ph / 2
            pw.guides.append(('h', cy))
            pw.guides_visible = True
            self.vzactions['view.guides'].setChecked(True)
            pw.updateGuideItems()

    def slotAddVGuide(self, checked=False):
        """Add vertical guide offset from center."""
        pw = self._currentPlotWindow()
        if pw and pw.painthelper:
            pgw = pw.painthelper.pagesize[0]
            nv = sum(1 for o, _ in pw.guides if o == 'v')
            cx = pgw * (0.25 + 0.1 * (nv - 1)) if nv > 0 else pgw / 2
            pw.guides.append(('v', cx))
            pw.guides_visible = True
            self.vzactions['view.guides'].setChecked(True)
            pw.updateGuideItems()

    def slotClearGuides(self, checked=False):
        """Reset guides to center cross (if visible) or clear all."""
        pw = self._currentPlotWindow()
        if pw:
            pw.guides.clear()
            if pw.guides_visible:
                # reset to center cross
                self._ensureCenterGuides(pw)
            pw.updateGuideItems()

    def _currentPlotWindow(self):
        """Get PlotWindow of current tab."""
        idx = self._tabwidget.currentIndex()
        if idx >= 0 and idx < len(self._tabs):
            return self._tabs[idx].get('plot')
        return None

    def slotImportColormap(self, checked=False):
        """Import a colormap from file."""
        from ..utils.colormap import importColormapFromFile

        fd = qt.QFileDialog(self, _('Import colormap'))
        fd.setFileMode(qt.QFileDialog.FileMode.ExistingFiles)
        fd.setNameFilters([
            _('All supported (*.txt *.csv *.gpl *.cpt)'),
            _('RGB text (*.txt *.csv)'),
            _('GIMP palette (*.gpl)'),
            _('GMT color table (*.cpt)'),
            _('All files (*)'),
        ])

        if fd.exec() != qt.QDialog.DialogCode.Accepted:
            return

        imported = []
        for filepath in fd.selectedFiles():
            try:
                name, cmap = importColormapFromFile(filepath)
                self.document.evaluate.colormaps[name] = cmap
                imported.append(name)
            except Exception as e:
                qt.QMessageBox.warning(
                    self, _('Import colormap'),
                    _('Error importing %s:\n%s') % (filepath, str(e)))

        if imported:
            qt.QMessageBox.information(
                self, _('Import colormap'),
                _('Imported colormaps: %s') % ', '.join(imported))

    def slotResetLayout(self):
        """Reset dock panels to default layout."""
        # remove any existing dock state
        for dock in [self.treeedit, self.propdock, self.formatdock,
                     self.datadock, self._console]:
            self.removeDockWidget(dock)

        # re-add in default positions
        self.addDockWidget(
            qt.Qt.DockWidgetArea.LeftDockWidgetArea, self.treeedit)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.LeftDockWidgetArea, self.propdock)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.LeftDockWidgetArea, self.formatdock)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.RightDockWidgetArea, self.datadock)
        self.addDockWidget(
            qt.Qt.DockWidgetArea.BottomDockWidgetArea, self._console)

        # show main panels, hide console
        for dock in [self.treeedit, self.propdock, self.formatdock,
                     self.datadock]:
            dock.show()
        self._console.hide()

    def slotFileNewGraph(self):
        """New file (graph) in new tab."""
        self._newTab(mode='graph')

    def slotFileNewPolar(self):
        """New file (polar) in new tab."""
        self._newTab(mode='polar')

    def slotFileNewTernary(self):
        """New file (ternary) in new tab."""
        self._newTab(mode='ternary')

    def slotFileNewGraph3D(self):
        """New file (graph3d) in new tab."""
        self._newTab(mode='graph3d')

    def slotFileSave(self):
        """Save file."""

        if self.filename == '':
            self.slotFileSaveAs()
        else:
            try:
                with utils.OverrideCursor():
                    ext = os.path.splitext(self.filename)[1]
                    mode = 'hdf5' if ext == '.vszh5' else 'vsz'
                    self.document.save(self.filename, mode)
                    self.updateStatusbar(_("Saved to %s") % self.filename)
            except EnvironmentError as e:
                qt.QMessageBox.critical(
                    self, _("Error - Plotex"),
                    _("Unable to save document as '%s'\n\n%s") %
                    (self.filename, e.strerror))

    def updateTitlebar(self):
        """Put the filename into the title bar."""
        if not hasattr(self, '_tabwidget'):
            self.setWindowTitle(_('Plotex'))
            return
        if self.filename == '':
            idx = self._tabwidget.currentIndex()
            if idx >= 0 and idx < len(self._tabs):
                label = self._tabs[idx].get('untitled_label', _('Untitled'))
            else:
                label = _('Untitled')
            self.setWindowTitle(_('%s - Plotex') % label)
        else:
            self.setWindowTitle(
                _("%s - Plotex") % os.path.basename(self.filename))

    def plotQueueChanged(self, incr):
        self.plotqueuecount += incr
        text = '•' * self.plotqueuecount
        self.plotqueuelabel.setText(text)

    def fileSaveDialog(self, filters, dialogtitle):
        """A generic file save dialog for exporting / saving.

        filters: list of filters
        """

        fd = qt.QFileDialog(self, dialogtitle)
        fd.setDirectory(self.dirname)
        fd.setFileMode(qt.QFileDialog.FileMode.AnyFile)
        fd.setAcceptMode(qt.QFileDialog.AcceptMode.AcceptSave)
        fd.setNameFilters(filters)

        # selected filetype is saved under a key constructed here
        filetype_re = re.compile(r'.*\(\*\.([a-z0-9]+)\)')
        filtertypes = [filetype_re.match(f).group(1) for f in filters]
        filterkey = '_'.join(['filterdefault'] + filtertypes)
        if filterkey in setting.settingdb:
            filter = setting.settingdb[filterkey]
            if filter in filters:
                fd.selectNameFilter(filter)

        # okay was selected (and is okay to overwrite if it exists)
        if fd.exec() == qt.QDialog.DialogCode.Accepted:
            # save directory for next time
            self.dirname = fd.directory().absolutePath()
            # update the edit box
            filename = fd.selectedFiles()[0]
            filetype = filetype_re.match(fd.selectedNameFilter()).group(1)
            if os.path.splitext(filename)[1][1:] != filetype:
                filename += '.' + filetype
            setting.settingdb[filterkey] = fd.selectedNameFilter()
            return filename

        return None

    def fileOpenDialog(self, filters, dialogtitle):
        """Display an open dialog and return a filename.

        filters: list of filters in format "Filetype (*.vsz)"
        """

        fd = qt.QFileDialog(self, dialogtitle)
        fd.setDirectory(self.dirname)
        fd.setFileMode( qt.QFileDialog.FileMode.ExistingFile )
        fd.setAcceptMode( qt.QFileDialog.AcceptMode.AcceptOpen )
        fd.setNameFilters(filters)

        # if the user chooses a file
        if fd.exec() == qt.QDialog.DialogCode.Accepted:
            # save directory for next time
            self.dirname = fd.directory().absolutePath()

            filename = fd.selectedFiles()[0]
            try:
                with open(filename):
                    pass
            except EnvironmentError as e:
                qt.QMessageBox.critical(
                    self, _("Error - Plotex"),
                    _("Unable to open '%s'\n\n%s") %
                    (filename, e.strerror))
                return None
            return filename
        return None

    def slotFileSaveAs(self):
        """Save As file."""

        filters = [_('Plotex document files (*.vsz)')]
        if h5py is not None:
            filters += [_('Plotex HDF5 document files (*.vszh5)')]
        filename = self.fileSaveDialog(filters, _('Save as'))
        if filename:
            self.filename = filename
            idx = self._tabwidget.currentIndex()
            if 0 <= idx < len(self._tabs):
                self._tabs[idx]['filename'] = filename
            self._updateTabLabel()
            self.updateTitlebar()

            self.slotFileSave()

    def openFile(self, filename):
        """Open file in current tab (if blank) or in a new tab.

        If the file is already open in a tab, switch to that tab.
        """

        # check if file is already open in a tab
        absname = os.path.abspath(filename)
        for i, state in enumerate(self._tabs):
            if state['filename'] and os.path.abspath(
                    state['filename']) == absname:
                self._tabwidget.setCurrentIndex(i)
                return

        # if in empty state (no tabs), create a new tab
        if len(self._tabs) == 0:
            self._newTab(filename=filename)
        elif self.document.isBlank():
            self.openFileInWindow(filename)
        else:
            self._newTab(filename=filename)

    def loadDocument(self, filename):
        """Load a Plotex document.
        Return True if loaded ok
        """

        def _callbackunsafe():
            """Callback when loading document to ask whether ok to continue loading
            if unsafe commands are found."""
            return self.checkUnsafe()

        def _callbackimporterror(filename, error):
            """Ask user if they want to give a new filename in case of import
            error.
            """
            with utils.OverrideCursor(qt.Qt.CursorShape.ArrowCursor):
                msgbox = qt.QMessageBox(self)
                msgbox.setWindowTitle(_("Import error"))
                msgbox.setText(
                    _("Could not import data from file '%s':\n\n %s") % (
                        filename, error))
                msgbox.setInformativeText(_("Do you want to look for another file?"))
                msgbox.setStandardButtons(
                    qt.QMessageBox.StandardButton.Yes |
                    qt.QMessageBox.StandardButton.Cancel )
                msgbox.addButton(qt.QMessageBox.StandardButton.Ignore)
                filename = None
                res = msgbox.exec()
                if res == qt.QMessageBox.StandardButton.Yes:
                    filename, _filter = qt.QFileDialog.getOpenFileName(
                        self, _("Choose data file"))
                    filename = filename or None
                elif res == qt.QMessageBox.StandardButton.Ignore:
                    filename = False
            return filename

        # save stdout and stderr, then redirect to console
        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout = self.console.con_stdout
        sys.stderr = self.console.con_stderr

        try:
            # get loading mode
            ext = os.path.splitext(filename)[1].lower()
            if ext in ('.vsz', '.py'):
                mode = 'vsz'
            elif ext in ('.h5', '.hdf5', '.he5', '.vszh5'):
                mode = 'hdf5'
            else:
                raise document.LoadError(
                    _("Did not recognise file type '%s'") % ext)

            # show progress in statusbar during loading
            basename = os.path.basename(filename)
            statusbar = self.statusbar
            loadlabel = qt.QLabel(_("Loading %s...") % basename)
            progressbar = qt.QProgressBar()
            progressbar.setMaximumWidth(200)
            progressbar.setMaximum(0)  # indeterminate
            statusbar.addPermanentWidget(loadlabel)
            statusbar.addPermanentWidget(progressbar)
            loadlabel.show()
            progressbar.show()
            # Only process paint/timer events — exclude user input to
            # prevent destructive actions while loading.
            _safeflags = qt.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            qt.QApplication.processEvents(_safeflags)

            def _onprogress(current, total, phase_msg):
                if phase_msg is not None:
                    loadlabel.setText(
                        "%s \u2014 %s" % (basename, phase_msg))
                    progressbar.setMaximum(0)  # indeterminate for phases
                else:
                    loadlabel.setText(
                        _("Loading %s... (%d%%)") % (
                            basename, int(100*current/max(total,1))))
                    progressbar.setMaximum(max(total, 1))
                    progressbar.setValue(current)
                qt.QApplication.processEvents(_safeflags)

            try:
                # do the actual loading
                self.document.load(
                    filename,
                    mode=mode,
                    callbackunsafe=_callbackunsafe,
                    callbackimporterror=_callbackimporterror,
                    callbackprogress=_onprogress)
            finally:
                statusbar.removeWidget(loadlabel)
                statusbar.removeWidget(progressbar)
                loadlabel.deleteLater()
                progressbar.deleteLater()

        except document.LoadError as e:
            from ..dialogs.errorloading import ErrorLoadingDialog
            if e.backtrace:
                d = ErrorLoadingDialog(self, filename, str(e), e.backtrace)
                d.exec()
            else:
                qt.QMessageBox.critical(
                    self, _("Error opening %s - Plotex") % filename,
                    str(e))
            return False
        finally:
            # always restore stdout, stderr even after LoadError
            sys.stdout, sys.stderr = stdout, stderr

        self.documentsetup = True
        return True

    def openFileInWindow(self, filename):
        """Actually do the work of loading a new document.
        """

        ok = self.loadDocument(filename)
        if not ok:
            return

        # remember file for recent list
        self.addRecentFile(filename)

        # let the main window know
        self.filename = filename
        # update tab state
        idx = self._tabwidget.currentIndex()
        if 0 <= idx < len(self._tabs):
            self._tabs[idx]['filename'] = filename
        self._updateTabLabel()
        self.updateTitlebar()
        self.updateStatusbar(_("Opened %s") % filename)

        # use current directory of file if not using cwd mode
        if not setdb['dirname_usecwd']:
            self.dirname = os.path.dirname( os.path.abspath(filename) )

        # notify cmpts which need notification that doc has finished opening
        self.documentOpened.emit()

        # force render of first page after loading
        self.plot.pagenumber = 0
        self.plot.oldpagenumber = -1
        self.plot.docchangeset = -100
        self.plot.checkPlotUpdate()

        # zoom to page after first render completes
        qt.QTimer.singleShot(200, self.plot.slotViewZoomPage)

    def addRecentFile(self, filename):
        """Add a file to the recent files list."""

        recent = setdb['main_recentfiles']
        filename = os.path.abspath(filename)

        if filename in recent:
            del recent[recent.index(filename)]
        recent.insert(0, filename)
        setdb['main_recentfiles'] = recent[:10]
        self.populateRecentFiles()

    def slotFileOpen(self):
        """Open an existing file in a new window."""

        filters = ['*.vsz']
        if h5py is not None:
            filters.append('*.vszh5')

        filename = self.fileOpenDialog(
            [_('Plotex document files (%s)') % ' '.join(filters)],
            _('Open'))
        if filename:
            self.openFile(filename)

    def populateRecentFiles(self):
        """Populate the recently opened files menu with a list of
        recently opened files"""

        def opener(path):
            def _fileOpener():
                self.openFile(path)
            return _fileOpener

        menu = self.menus["file.filerecent"]
        menu.clear()

        if setdb['main_recentfiles']:
            files = [
                f for f in setdb['main_recentfiles'] if os.path.isfile(f)]

            # add each recent file to menu
            newmenuitems = []
            for i, path in enumerate(files):
                newmenuitems.append(
                    ('filerecent%i' % i,_('Open File %s') % path,
                     os.path.basename(path),
                     'file.filerecent', opener(path),
                     '', False, ''))

            menu.setEnabled(True)
            self.recentFileActions = utils.populateMenuToolbars(
                newmenuitems, self._ribbon_toolbar, self.menus)
        else:
            menu.setEnabled(False)

    def slotFileReload(self):
        """Reload document from saved version."""

        retn = qt.QMessageBox.warning(
            self,
            _("Reload file"),
            _("Reload document from file, losing any changes?"),
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel
        )
        if retn == qt.QMessageBox.StandardButton.Yes:
            if not os.path.exists(self.filename):
                qt.QMessageBox.critical(
                    self,
                    _("Reload file"),
                    _("File %s no longer exists") % self.filename)
            else:
                self.openFileInWindow(self.filename)

    def slotFileExport(self):
        """Export the graph."""
        from ..dialogs.export import ExportDialog
        dialog = ExportDialog(self, self.document, self.filename)
        self.showDialog(dialog)
        return dialog

    def slotFilePrint(self):
        """Print the document."""
        document.printDialog(self, self.document, filename=self.filename)

    def slotModifiedDoc(self, ismodified):
        """Disable certain actions if document is not modified."""

        # enable/disable file, save menu item
        self.vzactions['file.save'].setEnabled(ismodified)

        # enable/disable reloading from saved document
        self.vzactions['file.reload'].setEnabled(
            bool(self.filename) and ismodified)

        # update tab label with modified indicator
        self._updateTabLabel()

        # update undo/redo tooltips with operation description
        self._updateUndoRedoTooltips()

    def _updateUndoRedoTooltips(self):
        """Update undo/redo button tooltips with the operation description."""
        if self.document.canUndo():
            descr = self.document.historyundo[-1].descr
            self._undoAction.setToolTip(_("Undo: %s") % descr)
        else:
            self._undoAction.setToolTip(_("Undo"))
        if self.document.canRedo():
            descr = self.document.historyredo[-1].descr
            self._redoAction.setToolTip(_("Redo: %s") % descr)
        else:
            self._redoAction.setToolTip(_("Redo"))

    def slotFileClose(self):
        """Close current tab (or window if last tab)."""
        idx = self._tabwidget.currentIndex()
        self._slotCloseTab(idx)

    def slotFileQuit(self):
        """File quit chosen."""
        qt.QApplication.instance().closeAllWindows()

    def slotUpdatePage(self, number):
        """Update page number when the plot window says so."""

        nump = self.document.getNumberPages()
        if nump == 0:
            self.pagelabel.setText(_("No pages"))
        else:
            self.pagelabel.setText(_("Page %i/%i") % (number+1, nump))

    def slotUpdateAxisValues(self, values):
        """Update the position where the mouse is relative to the axes."""

        if values:
            # construct comma separated text representing axis values
            valitems = [
                '%s=%#.4g' % (name, values[name])
                for name in sorted(values) ]
            self.axisvalueslabel.setText(', '.join(valitems))
        else:
            self.axisvalueslabel.setText(_('No position'))

    def slotPickerEnabled(self, enabled):
        if enabled:
            self.pickerlabel.setText(_('No point selected'))
            self.pickerlabel.show()
        else:
            self.pickerlabel.hide()

    def slotUpdatePickerLabel(self, info):
        """Display the picked point"""
        xv, yv = info.coords
        xn, yn = info.labels
        xt, yt = info.displaytype
        ix = str(info.index)
        if ix:
            ix = '[' + ix + ']'

        # format values for display
        def fmt(val, dtype):
            if dtype == 'date':
                return utils.dateFloatToString(val)
            elif dtype == 'numeric':
                fmt = '%.'+str(setting.settingdb['picker_sig_figs'])+'g'
                return fmt % val
            elif dtype == 'text':
                return val
            else:
                raise RuntimeError

        xtext = fmt(xv, xt)
        ytext = fmt(yv, yt)

        t = '%s: %s%s = %s, %s%s = %s' % (
            info.widget.name, xn, ix, xtext, yn, ix, ytext)
        self.pickerlabel.setText(t)
        if setdb['picker_to_console']:
            self.console.appendOutput(t + "\n", 'error')
        if setdb['picker_to_clipboard']:
            clipboard = qt.QApplication.clipboard()
            if clipboard.mimeData().hasText():
                clipboard.setText(clipboard.text()+"\n"+t)
            else:
                qt.QApplication.clipboard().setText(t)

    def checkUnsafe(self):
        """Ask user if code should be unsafe."""

        # we shouldn't allow these places to be added to allowed safe directories
        badlocs = (
            qt.QStandardPaths.standardLocations(qt.QStandardPaths.StandardLocation.DownloadLocation) +
            qt.QStandardPaths.standardLocations(qt.QStandardPaths.StandardLocation.TempLocation)
        )
        fname = self.document.filename
        absfile = os.path.abspath(fname)
        filedir = '' if not fname else os.path.dirname(absfile)
        isbadloc = False
        if not filedir:
            # shouldn't get here, but don't allow empty dir to be added
            isbadloc = True
        for path in badlocs:
            if absfile.startswith(os.path.abspath(path) + os.sep):
                isbadloc = True
        # don't allow plain home directory
        if filedir == qt.QStandardPaths.standardLocations(
                qt.QStandardPaths.StandardLocation.HomeLocation)[0]:
            isbadloc = True

        msgbox = qt.QMessageBox(
            qt.QMessageBox.Icon.Warning,
            _("Potentially unsafe code in document"),
            _(
                "<p><b>The document '%s' contains potentially unsafe code</b></p>"
                "<p>Directory: '%s'</p>"
                "<p>This file could damage your computer or data "
                "as it can contain arbitrary code. "
                "Please check "
                "that the file was made by you or a trusted source.</p>"
            ) % (
                os.path.basename(absfile) if fname else "",
                filedir if fname else "",
            ),
            qt.QMessageBox.StandardButton.NoButton,
            self,
        )
        allow = msgbox.addButton(_("Allow"), qt.QMessageBox.ButtonRole.AcceptRole)
        addloc = msgbox.addButton(_("Add to trusted locations"), qt.QMessageBox.ButtonRole.AcceptRole)
        addloc.setEnabled(not isbadloc)
        stop = msgbox.addButton(_("Skip"), qt.QMessageBox.ButtonRole.RejectRole)

        msgbox.setDefaultButton(stop)

        # we enter here with a busy cursor often, so set back to arrow temporarily
        with utils.OverrideCursor(qt.Qt.CursorShape.ArrowCursor):
            msgbox.exec()

        clicked = msgbox.clickedButton()
        if clicked is addloc:
            with utils.OverrideCursor(qt.Qt.CursorShape.ArrowCursor):
                button = qt.QMessageBox.warning(
                    self, _("Are you sure?"),
                    _("Are you really sure that you want to add directory '%s' to the "
                      "list of trusted locations. Any file loaded from this directory "
                      "will be trusted.") % filedir,
                    qt.QMessageBox.StandardButton.Yes |
                    qt.QMessageBox.StandardButton.No,
                    qt.QMessageBox.StandardButton.No,
                )
            if button == qt.QMessageBox.StandardButton.Yes:
                setting.settingdb['secure_dirs'].append(filedir)
                return True
            else:
                return False

        return clicked is allow

    def slotUpdateSecurity(self, secure):
        """Show or hide security label and trust menu based on security"""
        self.securitylabel.setVisible(not secure)
        self.vzactions['file.trust'].setVisible(not secure)

    def slotAllowedImportsDoc(self):
        """Are allowed imports?"""
        if self.checkUnsafe():
            self.document.evaluate.setSecurity(True)

    def slotFileTrust(self):
        """User requests that document should be trusted."""
        button = qt.QMessageBox.warning(
            self, _("Are you sure?"),
            _("Are you sure that you want to trust the document contents, "
              "including any potentially dangerous code? Only trust "
              "documents with a trusted source."),
            qt.QMessageBox.StandardButton.Yes |
            qt.QMessageBox.StandardButton.No,
            qt.QMessageBox.StandardButton.No,
        )
        if button == qt.QMessageBox.StandardButton.Yes:
            self.document.evaluate.setSecurity(True)
            # force redraw of document
            self.plot.actionForceUpdate()
