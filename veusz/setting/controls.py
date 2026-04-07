#    Copyright (C) 2005 Jeremy S. Sanders
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

"""Module for creating QWidgets for the settings, to enable their values
   to be changed.

    These widgets emit settingChanged(control, setting, val) when the setting is
    changed. The creator should use this to change the setting.
"""

import re
import numpy as N

from .. import qtall as qt
from .settingdb import settingdb
from .. import utils

def _(text, disambiguation=None, context="Setting"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

def styleClear(widget):
    """Return widget to default"""
    widget.setStyleSheet("")
    if hasattr(widget, '_origTooltip'):
        widget.setToolTip(widget._origTooltip)
        del widget._origTooltip

def styleError(widget, message=None):
    """Show error state on widget."""
    widget.setStyleSheet(
        "background-color: " + settingdb.color('error').name() )
    if message:
        widget._origTooltip = getattr(widget, '_origTooltip', widget.toolTip())
        widget.setToolTip(message)

class _CustomSlotFilter(qt.QObject):
    """Event filter that prevents custom-color slot clicks from
    changing the working color in QColorDialog."""

    def __init__(self, dlg):
        super().__init__(dlg)
        self._dlg = dlg
        self._color_before_click = None

    def eventFilter(self, obj, event):
        if event.type() == qt.QEvent.Type.MouseButtonPress:
            # Snapshot the current color before Qt changes it
            self._color_before_click = self._dlg.currentColor()
        elif event.type() == qt.QEvent.Type.MouseButtonRelease:
            if self._color_before_click is not None:
                saved = self._color_before_click
                self._color_before_click = None
                # Restore after Qt has processed the click
                qt.QTimer.singleShot(0, lambda: self._dlg.setCurrentColor(saved))
        return False


def _getColor(initial, parent, title="Choose color", alpha=False):
    """Open QColorDialog with 'Alpha' renamed to 'Transparencia'
    and custom-color slot behavior fixed so selecting a slot
    does not overwrite the working color."""
    dlg = qt.QColorDialog(initial, parent)
    dlg.setWindowTitle(title)
    if alpha:
        dlg.setOption(qt.QColorDialog.ColorDialogOption.ShowAlphaChannel)

    # Rename "Alpha" label → "Transparencia"
    for label in dlg.findChildren(qt.QLabel):
        if label.text().lower() in ('alpha channel:', 'alpha:', 'alpha'):
            label.setText('Transparencia:')
            break

    # Fix custom-color slot: install event filter only on the
    # custom-color grid (2 rows × 8 cols), not the basic-color grid.
    filt = _CustomSlotFilter(dlg)
    for view in dlg.findChildren(qt.QAbstractItemView):
        model = view.model()
        if (model is not None and
                model.rowCount() == 2 and model.columnCount() == 8):
            view.viewport().installEventFilter(filt)
            break

    if dlg.exec() == qt.QDialog.DialogCode.Accepted:
        return dlg.currentColor()
    return qt.QColor()  # invalid


class DotDotButton(qt.QPushButton):
    """A button for opening up more complex editor."""
    def __init__(self, tooltip=None, checkable=True):
        qt.QPushButton.__init__(
            self, "..", flat=True, checkable=checkable,
            minimumWidth=24, minimumHeight=24,
            maximumWidth=24, maximumHeight=24)
        if tooltip:
            self.setToolTip(tooltip)
        self.setSizePolicy(qt.QSizePolicy.Policy.Maximum, qt.QSizePolicy.Policy.Maximum)
        self.setStyleSheet('QPushButton { padding: 0; }')

class AddButton(qt.QPushButton):
    """A button to add item."""
    def __init__(self):
        qt.QPushButton.__init__(self, "+", flat=True)
        self.setFixedWidth(24)
        self.setToolTip(_('Add another item'))
        self.setStyleSheet('QPushButton { padding: 0; }')

class SubButton(qt.QPushButton):
    """A button to subtract item."""
    def __init__(self):
        qt.QPushButton.__init__(self, "-", flat=True)
        self.setFixedWidth(24)
        self.setToolTip(_('Remove item'))
        self.setStyleSheet('QPushButton { padding: 0; }')

class Edit(qt.QLineEdit):
    """Main control for editing settings which are text."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        """Initialise the setting widget."""

        qt.QLineEdit.__init__(self, parent)
        self.setting = setting

        self.setText( setting.toUIText() )
        self.editingFinished.connect(self.validateAndSet)
        self.returnPressed.connect(self._advanceFocus)
        self.setting.setOnModified(self.onModified)

        if setting.readonly:
            self.setReadOnly(True)

    def focusInEvent(self, event):
        """Save original text when gaining focus."""
        self._originalText = self.text()
        qt.QLineEdit.focusInEvent(self, event)

    def keyPressEvent(self, event):
        """Restore original text on Escape."""
        if event.key() == qt.Qt.Key.Key_Escape:
            self.setText(self._originalText)
            styleClear(self)
            self.clearFocus()
        else:
            qt.QLineEdit.keyPressEvent(self, event)

    def _advanceFocus(self):
        """Move focus to next control on Enter."""
        self.focusNextChild()

    def validateAndSet(self):
        """Check the text is a valid setting and update it."""

        text = self.text()
        try:
            val = self.setting.fromUIText(text)
            styleClear(self)
            self.sigSettingChanged.emit(self, self.setting, val)

        except utils.InvalidType:
            styleError(self, _("Invalid value"))

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.setText( self.setting.toUIText() )

class _EditBox(qt.QTextEdit):
    """A popup edit box to support editing long text sections.

    Emits closing(text) when the box closes
    """

    closing = qt.pyqtSignal(str)

    def __init__(self, origtext, readonly, parent):
        """Make a popup, framed widget containing a text editor."""

        qt.QTextEdit.__init__(self, parent)
        self.setWindowFlags(qt.Qt.WindowType.Popup)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

        self.spacing = self.fontMetrics().height()

        self.origtext = origtext
        self.setPlainText(origtext)

        cursor = self.textCursor()
        cursor.movePosition(qt.QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

        if readonly:
            self.setReadOnly(True)

        utils.positionFloatingPopup(self, parent)

        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Grab clicks outside this window to close it."""
        if ( isinstance(event, qt.QMouseEvent) and
             event.buttons() != qt.Qt.MouseButton.NoButton ):
            frame = qt.QRect(0, 0, self.width(), self.height())
            if not frame.contains(event.pos()):
                self.close()
                return True
        return qt.QTextEdit.eventFilter(self, obj, event)

    def keyPressEvent(self, event):
        """Close if escape or return is pressed."""
        qt.QTextEdit.keyPressEvent(self, event)

        key = event.key()
        if key == qt.Qt.Key.Key_Escape:
            # restore original content
            self.setPlainText(self.origtext)
            self.close()
        elif key == qt.Qt.Key.Key_Return:
            # keep changes
            self.close()

    def sizeHint(self):
        """A reasonable size for the text editor."""
        return qt.QSize(self.spacing*40, self.spacing*3)

    def closeEvent(self, event):
        """Tell the calling widget that we are closing, and provide
        the new text."""

        text = self.toPlainText()
        text = text.replace('\n', '')
        self.closing.emit(text)
        event.accept()

class String(qt.QWidget):
    """A line editor which allows editting in a larger popup window."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        qt.QWidget.__init__(self, parent)
        self.setting = setting

        layout = qt.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)

        self.edit = qt.QLineEdit()
        layout.addWidget(self.edit)

        b = self.button = DotDotButton(tooltip="Edit text")
        layout.addWidget(b)

        # set the text of the widget to the
        self.edit.setText( setting.toUIText() )

        self.edit.editingFinished.connect(self.validateAndSet)
        self.edit.returnPressed.connect(self._advanceFocus)
        b.toggled.connect(self.buttonToggled)

        self.setting.setOnModified(self.onModified)

        if setting.readonly:
            self.edit.setReadOnly(True)

        # install escape handler on internal edit
        self._originalText = self.edit.text()
        self.edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle focus-in and Escape on internal edit."""
        if obj is self.edit:
            if event.type() == qt.QEvent.Type.FocusIn:
                self._originalText = self.edit.text()
            elif event.type() == qt.QEvent.Type.KeyPress:
                if event.key() == qt.Qt.Key.Key_Escape:
                    self.edit.setText(self._originalText)
                    styleClear(self.edit)
                    self.edit.clearFocus()
                    return True
        return qt.QWidget.eventFilter(self, obj, event)

    def _advanceFocus(self):
        """Move focus to next control on Enter."""
        self.focusNextChild()

    def buttonToggled(self, on):
        """Button is pressed to bring popup up / down."""

        # if button is down and there's no existing popup, bring up a new one
        if on:
            e = _EditBox(
                self.edit.text(), self.setting.readonly, self.button)

            # we get notified with text when the popup closes
            e.closing.connect(self.boxClosing)
            e.show()

    def boxClosing(self, text):
        """Called when the popup edit box closes."""

        # update the text if we can
        if not self.setting.readonly:
            self.edit.setText(text)
            self.edit.setFocus()
            self.parentWidget().setFocus()
            self.edit.setFocus()

        self.button.setChecked(False)

    def validateAndSet(self):
        """Check the text is a valid setting and update it."""

        text = self.edit.text()
        try:
            val = self.setting.fromUIText(text)
            styleClear(self.edit)
            self.sigSettingChanged.emit(self, self.setting, val)

        except utils.InvalidType:
            styleError(self.edit, _("Invalid value"))

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.edit.setText( self.setting.toUIText() )

class Int(qt.QSpinBox):
    """A control for changing an integer."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        qt.QSpinBox.__init__(self, parent)

        self.ignorechange = False
        self.setting = setting
        self.setMinimum(setting.minval)
        self.setMaximum(setting.maxval)
        self.setValue(setting.val)

        self.valueChanged[int].connect(self.slotChanged)
        self.setting.setOnModified(self.onModified)

        if setting.readonly:
            self.setEnabled(False)

    def keyPressEvent(self, event):
        """Advance focus on Enter."""
        if event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter):
            self.focusNextChild()
        else:
            qt.QSpinBox.keyPressEvent(self, event)

    def slotChanged(self, value):
        """If check box changes."""
        # this is emitted by setValue, so ignore onModified doing this
        if not self.ignorechange:
            self.sigSettingChanged.emit(self, self.setting, value)

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.ignorechange = True
        self.setValue( self.setting.val )
        self.ignorechange = False

class FloatSlider(qt.QWidget):
    """A slider control for a numerical value.
    Note: QSlider is integer only, so dragging slider makes values integers
    """

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        qt.QWidget.__init__(self, parent)
        self.setting = setting
        self.setting.setOnModified(self.onModified)

        layout = qt.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        s = self.slider = qt.QSlider(qt.Qt.Orientation.Horizontal)
        s.setMinimum(int(setting.minval/setting.scale))
        s.setMaximum(int(setting.maxval/setting.scale))
        s.setPageStep(int(setting.step/setting.scale))
        s.setTickInterval(int(setting.tick/setting.scale))
        s.setTickPosition(qt.QSlider.TickPosition.TicksAbove)
        layout.addWidget(self.slider)

        self.edit = qt.QLineEdit()
        layout.addWidget(self.edit)

        self.edit.editingFinished.connect(self.validateAndSet)
        self.edit.returnPressed.connect(self._advanceFocus)
        self.slider.valueChanged.connect(self.movedPosition)

        self.onModified()

        # install escape handler on internal edit
        self._originalText = self.edit.text()
        self.edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle focus-in and Escape on internal edit."""
        if obj is self.edit:
            if event.type() == qt.QEvent.Type.FocusIn:
                self._originalText = self.edit.text()
            elif event.type() == qt.QEvent.Type.KeyPress:
                if event.key() == qt.Qt.Key.Key_Escape:
                    self.edit.setText(self._originalText)
                    styleClear(self.edit)
                    self.edit.clearFocus()
                    return True
        return qt.QWidget.eventFilter(self, obj, event)

    def _advanceFocus(self):
        """Move focus to next control on Enter."""
        self.focusNextChild()

    def validateAndSet(self):
        """Validate text is numeric."""
        try:
            val = self.setting.fromUIText(self.edit.text())
            styleClear(self.edit)
            self.sigSettingChanged.emit(self, self.setting, val)

        except utils.InvalidType:
            styleError(self.edit, _("Invalid value"))

    def movedPosition(self, val):
        """Someone dragged the slider."""
        self.sigSettingChanged.emit(
            self, self.setting, float(val)*self.setting.scale)

    @qt.pyqtSlot()
    def onModified(self):
        self.edit.setText(self.setting.toUIText())
        self.slider.setValue(int(round(
            self.setting.get()/self.setting.scale)))

class Bool(qt.QCheckBox):
    """A check box for changing a bool setting."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        qt.QCheckBox.__init__(self, parent)

        self.setSizePolicy( qt.QSizePolicy(
            qt.QSizePolicy.Policy.MinimumExpanding, qt.QSizePolicy.Policy.Fixed) )

        self.ignorechange = False
        self.setting = setting
        self.setChecked(setting.val)

        # we get a signal when the button is toggled
        self.toggled.connect(self.slotToggled)

        self.setting.setOnModified(self.onModified)

        if setting.readonly:
            self.setEnabled(False)

    def slotToggled(self, state):
        """Emitted when checkbox toggled."""
        # this is emitted by setChecked, so ignore onModified doing this
        if not self.ignorechange:
            self.sigSettingChanged.emit(self, self.setting, state)

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.ignorechange = True
        self.setChecked( self.setting.val )
        self.ignorechange = False

class BoolSwitch(Bool):
    """Bool for switching off/on other settings."""

    def showEvent(self, event):
        Bool.showEvent(self, event)
        self.updateState()

    def slotToggled(self, state):
        Bool.slotToggled(self, state)
        self.updateState()

    def updateState(self):
        """Set hidden state of settings."""
        s1, s2 = self.setting.strue, self.setting.sfalse
        if self.setting.val:
            show, hide = s1, s2
        else:
            show, hide = s2, s1

        if hasattr(self.parent(), 'showHideSettings'):
            self.parent().showHideSettings(show, hide)

class Choice(qt.QComboBox):
    """For choosing between a set of values."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, iseditable, vallist, parent, icons=None,
                 uilist=None,
                 descriptions=None):
        qt.QComboBox.__init__(self, parent)

        self.setting = setting
        self.vallist = vallist
        self.uilist = uilist
        self.setEditable(iseditable)

        # stops combobox readjusting in size to fit contents
        self.setSizeAdjustPolicy(
            qt.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

        # whether to show ui text to replace some items
        toadd = uilist if uilist is not None else vallist

        if icons is None:
            # add items to list (text only)
            self.addItems( list(toadd) )
        else:
            # add pixmaps and text to list
            for icon, text in zip(icons, toadd):
                self.addItem(icon, text)

        # use tooltip descriptions if requested
        if descriptions is not None:
            for i, descr in enumerate(descriptions):
                self.setItemData(i, descr, qt.Qt.ItemDataRole.ToolTipRole)

        # choose the correct setting
        try:
            index = list(vallist).index(setting.toUIText())
            self.setCurrentIndex(index)
        except ValueError:
            # for cases when this is editable
            # set the text of the widget to the setting
            assert iseditable
            self.setEditText( setting.toUIText() )

        # if a different item is selected
        self.textActivated[str].connect(self.slotActivated)

        self.setting.setOnModified(self.onModified)

        if setting.readonly:
            self.setEnabled(False)

        # make completion case sensitive (to help fix case typos)
        if self.completer():
            self.completer().setCaseSensitivity(qt.Qt.CaseSensitivity.CaseSensitive)

    def keyPressEvent(self, event):
        """Advance focus on Enter (when not showing popup)."""
        if (event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter)
                and not self.view().isVisible()):
            self.focusNextChild()
        else:
            qt.QComboBox.keyPressEvent(self, event)

    def focusOutEvent(self, *args):
        """Allows us to check the contents of the widget."""
        qt.QComboBox.focusOutEvent(self, *args)
        self.slotActivated('')

    def slotActivated(self, val):
        """If a different item is chosen."""

        text = self.currentText()

        # convert to ui text if set
        if self.uilist is not None:
            idx = self.uilist.index(text)
            if idx >= 0:
                text = self.vallist[idx]

        try:
            val = self.setting.fromUIText(text)
            styleClear(self)
            self.sigSettingChanged.emit(self, self.setting, val)

        except utils.InvalidType:
            styleError(self, _("Invalid value"))

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        text = self.setting.toUIText()

        # convert to ui text
        if self.uilist is not None:
            idx = self.vallist.index(text)
            if idx >= 0:
                text = self.uilist[idx]

        index = self.findText(text)
        if index >= 0:
            self.setCurrentIndex(index)
        if self.isEditable():
            self.setEditText(text)

class ChoiceSwitch(Choice):
    """Show or hide other settings based on value."""

    def showEvent(self, event):
        Choice.showEvent(self, event)
        self.updateState()

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        Choice.onModified(self)
        self.updateState()

    def updateState(self):
        """Set hidden state of settings."""
        show, hide = self.setting.showfn(self.setting.val)
        if hasattr(self.parent(), 'showHideSettings'):
            self.parent().showHideSettings(show, hide)

class FillStyleExtended(ChoiceSwitch):
    """Extended fill style list."""

    _icons = None

    def __init__(self, setting, parent):
        if self._icons is None:
            self._generateIcons()

        ChoiceSwitch.__init__(
            self, setting, False,
            utils.extfillstyles, parent,
            icons=self._icons
        )

    @classmethod
    def _generateIcons(cls):
        """Generate a list of pixmaps for drop down menu."""

        from .. import document
        from . import collections
        brush = collections.BrushExtended("")
        brush.color = 'black'
        brush.patternspacing = '5pt'
        brush.linewidth = '0.5pt'

        size = 12
        cls._icons = icons = []

        path = qt.QPainterPath()
        path.addRect(0, 0, size, size)

        doc = document.Document()
        phelper = document.PaintHelper(doc, (1,1))

        for f in utils.extfillstyles:
            pix = qt.QPixmap(size, size)
            pix.fill()
            painter = document.DirectPainter(pix)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.updateMetaData(phelper)
            brush.style = f
            utils.brushExtFillPath(painter, brush, path)
            painter.end()
            icons.append(qt.QIcon(pix))

class MultiLine(qt.QTextEdit):
    """For editting multi-line settings."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        """Initialise the widget."""

        qt.QTextEdit.__init__(self, parent)
        self.setting = setting

        self.setWordWrapMode(qt.QTextOption.WrapMode.NoWrap)
        self.setTabChangesFocus(True)

        # set the text of the widget to the
        self.setPlainText( setting.toUIText() )

        self.setting.setOnModified(self.onModified)

        if setting.readonly:
            self.setReadOnly(True)

        self.document().contentsChanged.connect(self.onSizeChange)
        self.document().documentLayout().documentSizeChanged.connect(
            self.onSizeChange)

        self.heightmin = 0
        self.heightmax = 2048

        # recalculate size of document to fix size
        self.document().adjustSize()
        self.onSizeChange()

    def onSizeChange(self):
        """Make size match content size."""
        m = self.contentsMargins()
        docheight = self.document().size().height() + m.top() + m.bottom()
        docheight = min(self.heightmax, max(self.heightmin, docheight))
        self.setFixedHeight(int(docheight))

    def focusOutEvent(self, *args):
        """Allows us to check the contents of the widget."""
        qt.QTextEdit.focusOutEvent(self, *args)

        text = self.toPlainText()
        try:
            val = self.setting.fromUIText(text)
            styleClear(self)
            self.sigSettingChanged.emit(self, self.setting, val)

        except utils.InvalidType:
            styleError(self)

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.setPlainText( self.setting.toUIText() )

class Notes(MultiLine):
    """For editing notes."""

    def __init__(self, setting, parent):
        MultiLine.__init__(self, setting, parent)
        self.setWordWrapMode(qt.QTextOption.WrapMode.WordWrap)

class Distance(Choice):
    """For editing distance settings."""

    # used to remove non-numerics from the string
    # we also remove X/ from X/num
    stripnumre = re.compile(r"[0-9]*/|[^0-9.,]")

    # remove spaces
    stripspcre = re.compile(r"\s")

    def __init__(self, setting, parent, allowauto=False, physical=False):
        '''Initialise with blank list, then populate with sensible units.'''
        Choice.__init__(self, setting, True, [], parent)
        self.allowauto = allowauto
        self.physical = physical
        self.updateComboList()
        self.lineEdit().setPlaceholderText("e.g. 1cm, 10pt")

    def updateComboList(self):
        '''Populates combo list with sensible list of other possible units.'''

        # turn off signals, so our modifications don't create more signals
        self.blockSignals(True)

        # get current text
        text = self.currentText()

        # get rid of non-numeric things from the string
        num = self.stripnumre.sub('', text)

        # here are a list of possible different units the user can choose
        # between. should this be in utils?
        newitems = [ num+'pt', num+'cm', num+'mm',
                     num+'in' ]
        if not self.physical:
            newitems += [ num+'%', '1/'+num ]

        if self.allowauto:
            newitems.insert(0, 'Auto')

        # if we're already in this list, we position the current selection
        # to the correct item (up and down keys work properly then)
        # spaces are removed to make sure we get sensible matches
        spcfree = self.stripspcre.sub('', text)
        try:
            index = newitems.index(spcfree)
        except ValueError:
            index = 0
            newitems.insert(0, text)

        # get rid of existing items in list (clear doesn't work here)
        for i in range(self.count()):
            self.removeItem(0)

        # put new items in and select the correct option
        self.addItems(newitems)
        self.setCurrentIndex(index)

        # must remember to do this!
        self.blockSignals(False)

    def slotActivated(self, val):
        '''Populate the drop down list before activation.'''
        self.updateComboList()
        Choice.slotActivated(self, val)

class DistancePt(Choice):
    """For editing distances with defaults in points."""

    points = (
        '0pt', '0.25pt', '0.5pt', '1pt', '1.5pt', '2pt', '3pt',
        '4pt', '5pt', '6pt', '8pt', '10pt', '12pt', '14pt', '16pt',
        '18pt', '20pt', '22pt', '24pt', '26pt', '28pt', '30pt',
        '34pt', '40pt', '44pt', '50pt', '60pt', '70pt'
    )

    def __init__(self, setting, parent, allowauto=False):
        '''Initialise with blank list, then populate with sensible units.'''
        Choice.__init__(self, setting, True, DistancePt.points, parent)

class DisplacementPt(DistancePt):
    """For editing displacements with defaults in points."""

    def __init__(self, setting, parent, allowauto=False):
        '''Initialise with blank list, then populate with sensible units.'''
        Choice.__init__(self, setting, True, DisplacementPt.points, parent)

class Dataset(qt.QWidget):
    """Allow the user to choose between the possible datasets."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)
    sigSettingChangedIteratively = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, document, dimensions, datatype, parent):
        """Initialise the combobox. The list is populated with datasets.

        dimensions specifies the dimension of the dataset to list

        Changes on the document refresh the list of datasets."""

        qt.QWidget.__init__(self, parent)

        self.choice = Choice(setting, True, [], None)
        self.choice.sigSettingChanged.connect(self.sigSettingChanged)

        b = self.button = DotDotButton(tooltip=_("Select using dataset browser"))
        b.toggled.connect(self.slotButtonToggled)

        self.document = document
        self.dimensions = dimensions
        self.datatype = datatype
        self.lastdatasets = None
        self._populateEntries()
        document.signalModified.connect(self.slotModified)

        layout = qt.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.choice)
        layout.addWidget(b)
        self.setLayout(layout)

    def _populateEntries(self):
        """Put the list of datasets into the combobox."""

        # get datasets of the correct dimension
        datasets = []
        for name, ds in self.document.data.items():
            okdims = (
                ds.dimensions == self.dimensions or
                self.dimensions == 'all'
            )
            oktype = (
                ds.datatype == self.datatype or
                self.datatype == 'all' or
                ds.datatype in self.datatype
            )

            if okdims and oktype:
                datasets.append(name)

        datasets.sort()

        if datasets != self.lastdatasets:
            utils.populateCombo(self.choice, datasets)
            self.lastdatasets = datasets

    @qt.pyqtSlot(int)
    def slotModified(self, modified):
        """Update the list of datasets if the document is modified."""
        self._populateEntries()

    def slotButtonToggled(self, on):
        """Bring up list of datasets."""
        if on:
            from ..qtwidgets.datasetbrowser import DatasetBrowserPopup
            d = DatasetBrowserPopup(
                self.document,
                self.choice.currentText(),
                self.button,
                filterdims=set((self.dimensions,)),
                filterdtype=set((self.datatype,)) )
            d.closing.connect(self.boxClosing)
            d.newdataset.connect(self.newDataset)
            d.newdatasets.connect(self.newDatasets)
            d.show()

    def boxClosing(self):
        """Called when the popup edit box closes."""
        self.button.setChecked(False)

    def newDataset(self, dsname):
        """New dataset selected."""
        self.sigSettingChanged.emit(self, self.choice.setting, dsname)

    def newDatasets(self, dsnames):
        """New datasets selected."""
        self.sigSettingChangedIteratively.emit(self, self.choice.setting, dsnames)

class DatasetOrString(Dataset):
    """Allow use to choose a dataset or enter some text."""

    def __init__(self, setting, document, parent):
        Dataset.__init__(self, setting, document, 1, 'all', parent)

        b = self.textbutton = DotDotButton()
        self.layout().addWidget(b)
        b.toggled.connect(self.textButtonToggled)

    def textButtonToggled(self, on):
        """Button is pressed to bring popup up / down."""

        # if button is down and there's no existing popup, bring up a new one
        if on:
            e = _EditBox(
                self.choice.currentText(),
                self.choice.setting.readonly, self.textbutton)

            # we get notified with text when the popup closes
            e.closing.connect(self.textBoxClosing)
            e.show()

    def textBoxClosing(self, text):
        """Called when the popup edit box closes."""

        self.textbutton.setChecked(False)

        # update the text if we can
        if not self.choice.setting.readonly:
            self.choice.setEditText(text)
            self.choice.setFocus()
            self.parentWidget().setFocus()
            self.choice.setFocus()

class FillStyle(Choice):
    """For choosing between fill styles."""

    _icons = None
    _fills = None
    _fillcnvt = None

    def __init__(self, setting, parent):
        if self._icons is None:
            self._generateIcons()

        Choice.__init__(
            self, setting, False,
            self._fills, parent,
            icons=self._icons
        )

    @classmethod
    def _generateIcons(cls):
        """Generate a list of pixmaps for drop down menu."""

        size = 12
        icons = []
        c = qt.QColor('grey')
        for f in cls._fills:
            pix = qt.QPixmap(size, size)
            pix.fill()
            painter = qt.QPainter(pix)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            brush = qt.QBrush(c, cls._fillcnvt[f])
            painter.fillRect(0, 0, size, size, brush)
            painter.end()
            icons.append( qt.QIcon(pix) )

        cls._icons = icons

class Marker(Choice):
    """A control to let the user choose a marker."""

    _icons = None

    def __init__(self, setting, parent):
        if self._icons is None:
            self._generateIcons()

        Choice.__init__(
            self, setting, False,
            utils.MarkerCodes, parent,
            icons=self._icons
        )

    @classmethod
    def _generateIcons(cls):
        size = 16
        icons = []
        brush = qt.QBrush( qt.QColor('darkgrey') )
        pen = qt.QPen( qt.QBrush(qt.Qt.GlobalColor.black), 1. )
        for marker in utils.MarkerCodes:
            pix = qt.QPixmap(size, size)
            pix.fill()
            painter = qt.QPainter(pix)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.setBrush(brush)
            painter.setPen(pen)
            utils.plotMarker(painter, size*0.5, size*0.5, marker, size*0.33)
            painter.end()
            icons.append( qt.QIcon(pix) )

        cls._icons = icons

class Arrow(Choice):
    """A control to let the user choose an arrowhead."""

    _icons = None

    def __init__(self, setting, parent):
        if self._icons is None:
            self._generateIcons()

        Choice.__init__(
            self, setting, False,
            utils.ArrowCodes, parent,
            icons=self._icons
        )

    @classmethod
    def _generateIcons(cls):
        size = 16
        icons = []
        brush = qt.QBrush(qt.Qt.GlobalColor.black)
        pen = qt.QPen( qt.QBrush(qt.Qt.GlobalColor.black), 1. )
        for arrow in utils.ArrowCodes:
            pix = qt.QPixmap(size, size)
            pix.fill()
            painter = qt.QPainter(pix)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
            painter.setBrush(brush)
            painter.setPen(pen)
            utils.plotLineArrow(
                painter, size*0.4, size*0.5,
                size*2, 0.,
                arrowsize=size*0.2,
                arrowleft=arrow, arrowright=arrow)
            painter.end()
            icons.append( qt.QIcon(pix) )

        cls._icons = icons

class LineStyle(Choice):
    """For choosing between line styles."""

    _icons = None
    _lines = None
    _linecnvt = None

    size = (24, 8)

    def __init__(self, setting, parent):
        if self._icons is None:
            self._generateIcons()

        Choice.__init__(
            self, setting, False,
            self._lines, parent,
            icons=self._icons
        )
        self.setIconSize( qt.QSize(*self.size) )

    @classmethod
    def _generateIcons(cls):
        """Generate a list of icons for drop down menu."""

        # import later for dependency issues
        from . import collections
        from .. import document

        icons = []
        size = cls.size
        setn = collections.Line('temp')
        setn.get('color').set('black')
        setn.get('width').set('1pt')

        doc = document.Document()
        for lstyle in cls._lines:
            pix = qt.QPixmap(*size)
            pix.fill()

            painter = document.DirectPainter(pix)
            painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)

            phelper = document.PaintHelper(doc, (1, 1))
            painter.updateMetaData(phelper)

            setn.get('style').set(lstyle)

            painter.setPen( setn.makeQPen(painter) )
            painter.drawLine(
                int(size[0]*0.1), size[1]//2,
                int(size[0]*0.9), size[1]//2)
            painter.end()
            icons.append( qt.QIcon(pix) )

        cls._icons = icons

class _ColNotifier(qt.QObject):
    sigNewColor = qt.pyqtSignal(str)


class _ColorPopup(qt.QFrame):
    """Popup panel showing palette, colormaps, and basic colors."""

    colorSelected = qt.pyqtSignal(str)

    _COLS = 8
    _SWATCH = 22
    _BASIC = [
        'black', 'darkred', 'darkgreen', 'darkblue',
        'darkcyan', 'darkmagenta', 'grey', 'white',
        'red', 'green', 'blue', 'cyan',
        'magenta', 'yellow', 'foreground', 'background',
    ]
    _SKIP_CMAPS = {'blank', 'none', 'transblack'}
    _LABEL_CSS = (
        'color: #777; font-size: 11px; border: none; '
        'padding: 0; margin-bottom: 2px;')

    def __init__(self, parent, colors, colormaps, current_val):
        super().__init__(
            parent,
            qt.Qt.WindowType.Popup | qt.Qt.WindowType.FramelessWindowHint)
        self.colors = colors
        self.colormaps = colormaps
        self.current_val = current_val
        self.setAttribute(qt.Qt.WidgetAttribute.WA_WindowPropagation)
        self.setStyleSheet(
            'QFrame { background: white; border: 1px solid #bbb; }')
        self._build()

    def _build(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # palette section
        theme = self.colors.colortheme
        if self.colors.themenames:
            lbl = qt.QLabel(_('Palette') + ' \u2014 %s' % theme)
            lbl.setStyleSheet(self._LABEL_CSS)
            layout.addWidget(lbl)
            layout.addLayout(
                self._makeGrid(self.colors.themenames))
            layout.addSpacing(4)

        # basic colors
        lbl2 = qt.QLabel(_('Basic'))
        lbl2.setStyleSheet(self._LABEL_CSS)
        layout.addWidget(lbl2)
        layout.addLayout(self._makeGrid(self._BASIC))
        layout.addSpacing(4)

        # colormap section
        lbl3 = qt.QLabel(_('Colormap'))
        lbl3.setStyleSheet(self._LABEL_CSS)
        layout.addWidget(lbl3)

        self._cmap_combo = qt.QComboBox()
        self._cmap_combo.setStyleSheet(
            'border: 1px solid #ccc; padding: 2px;')
        self._populateCmapCombo()
        self._cmap_combo.currentTextChanged.connect(self._onCmapChanged)
        layout.addWidget(self._cmap_combo)

        self._cmap_grid_widget = qt.QWidget()
        self._cmap_grid_widget.setStyleSheet('border: none;')
        self._cmap_grid_layout = qt.QVBoxLayout(self._cmap_grid_widget)
        self._cmap_grid_layout.setContentsMargins(0, 2, 0, 0)
        layout.addWidget(self._cmap_grid_widget)

        # select a good default colormap
        default_cmap = 'cb-set1'
        idx = self._cmap_combo.findText(default_cmap)
        if idx >= 0:
            self._cmap_combo.setCurrentIndex(idx)
        self._onCmapChanged(self._cmap_combo.currentText())

        layout.addSpacing(4)

        # hex input + more button
        row = qt.QHBoxLayout()
        row.setSpacing(4)
        self._hex = qt.QLineEdit()
        self._hex.setPlaceholderText('#RRGGBB')
        self._hex.setFixedWidth(80)
        self._hex.setStyleSheet('border: 1px solid #ccc; padding: 2px;')
        self._hex.returnPressed.connect(self._onHexEnter)
        row.addWidget(self._hex)

        more = qt.QPushButton(_('More\u2026'))
        more.setFlat(True)
        more.setStyleSheet(
            'color: #555; font-size: 11px; border: none; padding: 2px;')
        more.clicked.connect(self._onMore)
        row.addWidget(more)
        row.addStretch()
        layout.addLayout(row)

    _DISCRETE_CMAPS = [
        'cb-set1', 'cb-set2', 'cb-dark2', 'cb-paired',
        'npg', 'nejm', 'lancet', 'jama', 'aaas', 'okabe-ito',
    ]

    def _populateCmapCombo(self):
        combo = self._cmap_combo
        available = set(self.colormaps.maps.keys())
        for cname in self._DISCRETE_CMAPS:
            if cname in available:
                combo.addItem(cname)

    def _onCmapChanged(self, name):
        """Update colormap swatches when combo changes."""
        from ..utils.colormap import getColormapArray
        import numpy as N

        # clear previous swatches
        old = self._cmap_grid_widget.layout()
        while old.count():
            item = old.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clearLayout(item.layout())

        try:
            cmap = self.colormaps[name]
        except KeyError:
            return

        arr = N.array(cmap)
        is_stepped = len(arr) > 0 and arr[0][0] < 0
        ncolors = (len(arr) - 1) if is_stepped else min(len(arr), 12)
        if ncolors < 1:
            return
        ncolors = min(ncolors, 16)

        rgba = getColormapArray(cmap, ncolors)
        grid = qt.QGridLayout()
        grid.setSpacing(2)
        for i in range(ncolors):
            r, g, b, a = int(rgba[i][0]), int(rgba[i][1]), int(rgba[i][2]), int(rgba[i][3])
            hexc = '#%02x%02x%02x' % (r, g, b)
            btn = self._makeHexSwatch(hexc, '%s [%d]' % (name, i+1))
            grid.addWidget(btn, i // self._COLS, i % self._COLS)

        container = qt.QWidget()
        container.setStyleSheet('border: none;')
        container.setLayout(grid)
        old.addWidget(container)

    def _clearLayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                self._clearLayout(item.layout())

    def _makeGrid(self, names):
        grid = qt.QGridLayout()
        grid.setSpacing(2)
        for i, name in enumerate(names):
            btn = self._makeSwatch(name)
            grid.addWidget(btn, i // self._COLS, i % self._COLS)
        return grid

    def _makeSwatch(self, colorname):
        btn = qt.QPushButton()
        btn.setFixedSize(self._SWATCH, self._SWATCH)
        qcolor = self.colors.get(colorname)
        hexc = qcolor.name()

        is_current = (
            colorname == self.current_val or
            hexc == self.colors.get(self.current_val).name()
            if self.current_val else False)
        border = '2px solid #333' if is_current else '1px solid #ccc'

        btn.setStyleSheet(
            'background-color: %s; border: %s; border-radius: 2px;'
            % (hexc, border))
        btn.setToolTip('%s  (%s)' % (colorname, hexc))
        btn.setCursor(qt.Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(
            lambda checked, n=colorname: self._select(n))
        return btn

    def _makeHexSwatch(self, hexcolor, tooltip):
        btn = qt.QPushButton()
        btn.setFixedSize(self._SWATCH, self._SWATCH)

        cur_hex = (
            self.colors.get(self.current_val).name()
            if self.current_val else '')
        border = (
            '2px solid #333' if hexcolor == cur_hex
            else '1px solid #ccc')

        btn.setStyleSheet(
            'background-color: %s; border: %s; border-radius: 2px;'
            % (hexcolor, border))
        btn.setToolTip('%s  (%s)' % (tooltip, hexcolor))
        btn.setCursor(qt.Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(
            lambda checked, h=hexcolor: self._select(h))
        return btn

    def _select(self, name):
        self.colorSelected.emit(name)
        self.close()

    def _onHexEnter(self):
        text = self._hex.text().strip()
        if text:
            self.colorSelected.emit(text)
            self.close()

    def _onMore(self):
        self.hide()
        parent = self.parent()
        cur = (self.colors.get(self.current_val)
               if self.current_val else qt.QColor())
        col = _getColor(cur, parent)
        if col.isValid():
            self.colorSelected.emit(col.name())
        self.close()


class Color(qt.QWidget):
    """A control which lets the user choose a color.

    A drop down list and a button to bring up a dialog are used
    """

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        qt.QWidget.__init__(self, parent)

        self.setting = setting
        self.document = setting.getDocument()
        self.colors = self.document.evaluate.colors

        # combo box
        c = self.combo = qt.QComboBox()
        c.setEditable(True)
        c.textActivated[str].connect(self.slotActivated)

        # button for selecting colors
        b = self.button = qt.QPushButton()
        b.setFlat(True)
        b.setSizePolicy(qt.QSizePolicy.Policy.Maximum, qt.QSizePolicy.Policy.Maximum)
        b.setMaximumHeight(24)
        b.setMaximumWidth(24)
        b.clicked.connect(self.slotButtonClicked)

        c.setModel(self.colors.model)
        self.setColor(self.setting.val)

        if setting.readonly:
            c.setEnabled(False)
            b.setEnabled(False)

        layout = qt.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(c)
        layout.addWidget(b)

        self.setColor(setting.toUIText())
        self.setLayout(layout)
        self.setting.setOnModified(self.onModified)

    def slotButtonClicked(self):
        """Open color popup panel."""
        colormaps = self.document.evaluate.colormaps
        popup = _ColorPopup(
            self, self.colors, colormaps, self.setting.val)
        popup.colorSelected.connect(self._onPopupColor)

        # measure size without showing visibly: move offscreen, show, measure
        popup.move(-9999, -9999)
        popup.show()
        popup.adjustSize()
        pw = popup.sizeHint().width()
        ph = popup.sizeHint().height()
        if pw < 50:
            pw = popup.width()
        if ph < 50:
            ph = popup.height()

        # desired position: below the button
        pos = self.button.mapToGlobal(
            qt.QPoint(0, self.button.height()))
        screen = self.screen().availableGeometry()

        # shift left if it goes off the right edge
        if pos.x() + pw > screen.right():
            pos.setX(screen.right() - pw)
        # shift up if it goes off the bottom edge
        if pos.y() + ph > screen.bottom():
            pos.setY(self.button.mapToGlobal(
                qt.QPoint(0, 0)).y() - ph)
        # clamp within screen
        pos.setX(min(max(pos.x(), screen.left()), screen.right() - pw))
        pos.setY(min(max(pos.y(), screen.top()), screen.bottom() - ph))
        popup.move(pos)

    def _onPopupColor(self, color):
        """Handle color selected from popup."""
        self.sigSettingChanged.emit(self, self.setting, color)

    def slotActivated(self, text):
        """A different value is selected."""
        val = self.setting.fromUIText(text)
        self.sigSettingChanged.emit(self, self.setting, val)

    def setColor(self, color):
        """Update control with color given."""

        index = self.combo.findText(color)
        if index < 0:
            # add text to combo if not there
            self.combo.addItem(color)
            index = self.combo.findText(color)

        self.combo.setCurrentIndex(index)

        icon = self.combo.itemData(index, qt.Qt.ItemDataRole.DecorationRole)
        self.button.setIcon(icon)

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.setColor( self.setting.toUIText() )

class WidgetSelector(Choice):
    """For choosing from a list of widgets."""

    def __init__(self, setting, document, parent):
        """Initialise and populate combobox."""

        Choice.__init__(self, setting, True, [], parent)
        self.document = document
        document.signalModified.connect(self.slotModified)

    def _populateEntries(self):
        pass

    @qt.pyqtSlot(int)
    def slotModified(self, modified):
        """Update list of axes."""
        self._populateEntries()

class WidgetChoice(WidgetSelector):
    """Choose a widget."""

    def __init__(self, setting, document, parent):
        """Initialise and populate combobox."""

        WidgetSelector.__init__(self, setting, document, parent)
        self._populateEntries()

    def _populateEntries(self):
        """Build up a list of widgets for combobox."""

        widgets = self.setting.getWidgetList()

        # we only need the list of names
        names = list(widgets.keys())
        names.sort()

        utils.populateCombo(self, names)

class Axis(WidgetSelector):
    """Choose an axis to plot against."""

    def __init__(self, setting, document, direction, parent):
        """Initialise and populate combobox."""

        WidgetSelector.__init__(self, setting, document, parent)
        self.direction = direction
        self._populateEntries()

    def _populateEntries(self):
        """Build up a list of possible axes."""

        # get parent widget
        widget = self.setting.parent
        while not widget.iswidget and widget is not None:
            widget = widget.parent

        # get list of axis widgets up the tree
        axes = set()
        while widget is not None:
            for w in widget.children:
                if ( w.isaxis and (
                        self.direction == 'both' or
                        w.settings.direction == self.direction) ):
                    axes.add(w.name)
            widget = widget.parent

        names = sorted(axes)
        utils.populateCombo(self, names)

class ListSet(qt.QFrame):
    """A widget for constructing settings which are lists of other
    properties.

    This code is pretty nasty and horrible, so we abstract it in this
    base widget
    """

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    pixsize = 12

    def __init__(self, defaultval, setting, parent):
        """Initialise this base widget.

        defaultval is the default entry to add if add is clicked with
        no current entries

        setting is the setting this widget corresponds to

        parent is the parent widget.
        """

        qt.QFrame.__init__(self, parent)
        self.setFrameStyle(qt.QFrame.Shape.Box)
        self.defaultval = defaultval
        self.setting = setting
        self.controls = []
        self.layout = qt.QGridLayout(self)
        s = self.layout.contentsMargins().left()//2
        self.layout.setContentsMargins(s,s,s,s)
        self.layout.setSpacing( self.layout.spacing()//4 )

        self.doneinit = False
        self.onModified()
        self.setting.setOnModified(self.onModified)

    def populateRow(self, row):
        """Populate the row in the control.

        Returns a list of the widgets created.
        """
        return []

    def updateRow(self, cntrls, val):
        """Set controls on row, given values for row, val."""
        pass

    def populate(self):
        """Construct the list of controls."""

        if len(self.setting.val) == len(self.controls) and self.doneinit:
            # no change in number of controls
            return
        self.doneinit = True   # we need to add the add/remove buttons below

        # delete all children in case of refresh
        self.controls = []
        for c in self.children():
            if isinstance(c, qt.QWidget):
                self.layout.removeWidget(c)
                c.deleteLater()
        c = None

        # iterate over each row
        row = -1
        for row, val in enumerate(self.setting.val):
            cntrls = self.populateRow(row)
            self.updateRow(cntrls, val)
            for col in range(len(cntrls)):
                self.layout.addWidget(cntrls[col], row, col)
            for c in cntrls:
                c.show()
            self.controls.append(cntrls)

        # buttons at end
        bbox = qt.QWidget()
        h = qt.QHBoxLayout(bbox)
        h.setContentsMargins(0,0,0,0)
        bbox.setLayout(h)
        self.layout.addWidget(bbox, row+1, 0, 1, -1)

        # a button to add a new entry
        b = qt.QPushButton(_('Add'))
        h.addWidget(b)
        b.clicked.connect(self.onAddClicked)
        b.show()

        # a button to delete the last entry
        b = qt.QPushButton(_('Delete'))
        h.addWidget(b)
        b.clicked.connect(self.onDeleteClicked)
        b.setEnabled(len(self.setting.val) > 0)
        b.show()

    def onAddClicked(self):
        """Add a line style to the list given."""

        rows = list(self.setting.val)
        if len(rows) != 0:
            rows.append(rows[-1])
        else:
            rows.append(self.defaultval)
        self.sigSettingChanged.emit(self, self.setting, rows)

    def onDeleteClicked(self):
        """Remove final entry in settings list."""

        rows = list(self.setting.val)[:-1]
        self.sigSettingChanged.emit(self, self.setting, rows)

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.populate()
        for cntrls, row in zip(self.controls, self.setting.val):
            self.updateRow(cntrls, row)

    def identifyPosn(self, widget):
        """Identify the position this widget is in.

        Returns (row, col) or (None, None) if not found.
        """

        for row, cntrls in enumerate(self.controls):
            for col, cntrl in enumerate(cntrls):
                if cntrl == widget:
                    return (row, col)
        return (None, None)

    def addColorButton(self, tooltip):
        """Add a color button to the list at the position specified."""
        wcolor = qt.QPushButton()
        wcolor.setFlat(True)
        wcolor.setSizePolicy(qt.QSizePolicy.Policy.Maximum, qt.QSizePolicy.Policy.Maximum)
        wcolor.setMaximumHeight(24)
        wcolor.setMaximumWidth(24)
        wcolor.setToolTip(tooltip)
        wcolor.clicked.connect(self.onColorClicked)
        return wcolor

    def updateColorButton(self, cntrl, color):
        """Given color control, update color."""

        pix = qt.QPixmap(self.pixsize, self.pixsize)
        qcolor = self.setting.getDocument().evaluate.colors.get(color)
        pix.fill(qcolor)
        cntrl.setIcon(qt.QIcon(pix))

    def addToggleButton(self, tooltip):
        """Make a toggle button."""
        wtoggle = qt.QCheckBox()
        wtoggle.setToolTip(tooltip)
        wtoggle.toggled.connect(self.onToggled)
        return wtoggle

    def updateToggleButton(self, cntrl, val):
        """Update toggle with value."""
        cntrl.setChecked(val)

    def addCombo(self, tooltip, values, icons, texts):
        """Make an enumeration combo - choose from a set of icons."""

        wcombo = qt.QComboBox()
        wcombo.setToolTip(tooltip)
        wcombo.activated[int].connect(self.onComboChanged)

        if texts is None:
            for icon in icons:
                wcombo.addItem(icon, "")
        else:
            for text, icon in zip(texts, icons):
                wcombo.addItem(icon, text)

        wcombo._vz_values = values
        return wcombo

    def updateCombo(self, cntrl, val):
        """Update selected item in combo."""
        cntrl.setCurrentIndex(cntrl._vz_values.index(val))

    def _updateRowCol(self, row, col, val):
        """Update value on row and column."""
        rows = list(self.setting.val)
        items = list(rows[row])
        items[col] = val
        rows[row] = tuple(items)
        self.sigSettingChanged.emit(self, self.setting, rows)

    def onToggled(self, on):
        """Checkbox toggled."""
        row, col = self.identifyPosn(self.sender())
        if row is not None:
            self._updateRowCol(row, col, on)

    def onComboChanged(self, val):
        """Update the setting if the combo changes."""
        sender = self.sender()
        row, col = self.identifyPosn(sender)
        if row is not None:
            self._updateRowCol(row, col, sender._vz_values[val])

    def onColorClicked(self):
        """Color button clicked for line."""
        sender = self.sender()
        row, col = self.identifyPosn(sender)

        rows = self.setting.val
        qcolor = self.setting.getDocument().evaluate.colors.get(
            rows[row][col])
        color = _getColor(qcolor, self, "Choose color", alpha=True)
        if color.isValid():
            # change setting
            # this is a bit irritating, as have to do lots of
            # tedious conversions
            color = utils.extendedColorFromQColor(color)
            self._updateRowCol(row, col, color)

            # change the color
            pix = qt.QPixmap(self.pixsize, self.pixsize)
            qcolor = self.setting.getDocument().evaluate.colors.get(color)
            pix.fill(qcolor)
            sender.setIcon(qt.QIcon(pix))

class LineSet(ListSet):
    """A list of line styles.
    """

    def __init__(self, setting, parent):
        ListSet.__init__(
            self, ('solid', '1pt', 'black', False), setting, parent)

    def populateRow(self, row):
        """Add the widgets for the row given."""

        # create line icons if not already created
        if LineStyle._icons is None:
            LineStyle._generateIcons()

        # make line style selector
        wlinestyle = self.addCombo(
            _('Line style'), LineStyle._lines, LineStyle._icons, None)

        # make line width edit box
        wwidth = qt.QLineEdit()
        wwidth.setToolTip(_('Line width'))
        wwidth.editingFinished.connect(self.onWidthChanged)

        # make color selector button
        wcolor = self.addColorButton(_('Line color'))

        # make hide checkbox
        whide = self.addToggleButton( _('Hide line'))

        # return created controls
        return [wlinestyle, wwidth, wcolor, whide]

    def updateRow(self, cntrls, val):
        """Update controls with row settings."""
        self.updateCombo(cntrls[0], val[0])
        cntrls[1].setText(val[1])
        self.updateColorButton(cntrls[2], val[2])
        self.updateToggleButton(cntrls[3], val[3])

    def onWidthChanged(self):
        """Width has changed - validate."""

        sender = self.sender()
        row, col = self.identifyPosn(sender)

        text = sender.text()
        from . import setting
        if setting.Distance.isDist(text):
            # valid distance
            styleClear(sender)
            self._updateRowCol(row, col, text)
        else:
            # invalid distance
            styleError(sender)

class _FillBox(qt.QScrollArea):
    """Pop up box for extended fill settings."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)
    closing = qt.pyqtSignal(int)

    def __init__(self, doc, thesetting, row, button, parent):
        """Initialse widget. This is based on a PropertyList widget.

        FIXME: we have to import at runtime, so we should improve
        the inheritance here. Is using PropertyList window a hack?
        """

        qt.QScrollArea.__init__(self, parent)
        self.setWindowFlags(qt.Qt.WindowType.Popup)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.parent = parent
        self.row = row
        self.setting = thesetting

        self.extbrush = thesetting.returnBrushExtended(row)

        # need to add a real parent, so that the colors can be resolved
        self.extbrush.parent = thesetting.parent

        from ..windows.treeeditwindow import SettingsProxySingle, PropertyList

        fbox = self
        class DirectSetProxy(SettingsProxySingle):
            """Class to intercept changes of settings from UI."""
            def onSettingChanged(self, control, setting, val):
                # set value in setting
                setting.val = val
                # tell box to update setting
                fbox.onSettingChanged()

        # actual widget for changing the fill
        plist = PropertyList(doc)
        plist.updateProperties( DirectSetProxy(doc, self.extbrush) )
        self.setWidget(plist)

        utils.positionFloatingPopup(self, button)
        self.installEventFilter(self)

    def onSettingChanged(self):
        """Called when user changes a fill property."""

        # get value of brush and get data for row
        e = self.extbrush
        rowdata = [e.style, e.color, e.hide]
        if e.style != 'solid' or e.transparency > 0:
            rowdata += [
                e.transparency, e.linewidth, e.linestyle,
                e.patternspacing, e.backcolor,
                e.backtransparency, e.backhide ]
        rowdata = tuple(rowdata)

        if self.setting.val[self.row] != rowdata:
            # if row different, send update signal
            val = list(self.setting.val)
            val[self.row] = rowdata
            self.sigSettingChanged.emit(self, self.setting, val)

    def eventFilter(self, obj, event):
        """Grab clicks outside this window to close it."""
        if ( isinstance(event, qt.QMouseEvent) and
             event.buttons() != qt.Qt.MouseButton.NoButton ):
            frame = qt.QRect(0, 0, self.width(), self.height())
            if not frame.contains(event.pos()):
                self.close()
                return True
        return qt.QScrollArea.eventFilter(self, obj, event)

    def keyPressEvent(self, event):
        """Close if escape or return is pressed."""
        qt.QScrollArea.keyPressEvent(self, event)

        key = event.key()
        if key == qt.Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        """Tell the calling widget that we are closing, and provide
        the new text."""

        self.closing.emit(self.row)
        qt.QScrollArea.closeEvent(self, event)

class FillSet(ListSet):
    """A list of fill settings."""

    def __init__(self, setting, parent):
        ListSet.__init__(
            self, ('solid', 'black', False), setting, parent)

    def populateRow(self, row):
        """Add the widgets for the row given."""

        # construct fill icons if not already done
        if FillStyleExtended._icons is None:
            FillStyleExtended._generateIcons()

        # make fill style selector
        wfillstyle = self.addCombo(
            _("Fill style"),
            utils.extfillstyles, FillStyleExtended._icons, utils.extfillstyles)
        wfillstyle.setMinimumWidth(self.pixsize)

        # make color selector button
        wcolor = self.addColorButton(_("Fill color"))

        # make hide checkbox
        whide = self.addToggleButton(_("Hide fill"))

        # extended options
        wmore = DotDotButton(tooltip=_("More options"))
        wmore.toggled.connect(lambda on, row=row: self.editMore(on, row))

        # return widgets
        return [wfillstyle, wcolor, whide, wmore]

    def updateRow(self, cntrls, val):
        self.updateCombo(cntrls[0], val[0])
        self.updateColorButton(cntrls[1], val[1])
        self.updateToggleButton(cntrls[2], val[2])

    def buttonAtRow(self, row):
        """Get .. button on row."""
        return self.layout.itemAtPosition(row, 3).widget()

    def editMore(self, on, row):
        if on:
            fb = _FillBox(
                self.setting.getDocument(), self.setting,
                row, self.buttonAtRow(row), self.parent())
            fb.closing.connect(self.boxClosing)
            fb.sigSettingChanged.connect(self.sigSettingChanged)
            fb.show()

    def boxClosing(self, row):
        """Called when the popup edit box closes."""
        # uncheck the .. button
        self.buttonAtRow(row).setChecked(False)

class MultiSettingWidget(qt.QWidget):
    """A widget for storing multiple values in a tuple,
    with + and - signs by each entry."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, doc, *args):
        """Construct widget as combination of LineEdit and PushButton
        for browsing."""

        qt.QWidget.__init__(self, *args)
        self.setting = setting
        self.document = doc

        self.grid = layout = qt.QGridLayout()
        layout.setHorizontalSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)

        self.last = ()
        self.controls = []
        self.setting.setOnModified(self.onModified)

    def makeRow(self):
        """Make new row at end"""
        row = len(self.controls)
        cntrl = self.makeControl(row)
        cntrl.installEventFilter(self)
        addbutton = AddButton()
        subbutton = SubButton()

        self.controls.append((cntrl, addbutton, subbutton))

        self.grid.addWidget(cntrl, row, 0)
        self.grid.addWidget(addbutton, row, 1)
        self.grid.addWidget(subbutton, row, 2)

        addbutton.clicked.connect(lambda: self.addPressed(row))
        subbutton.clicked.connect(lambda: self.subPressed(row))

        if len(self.controls) == 2:
            # enable first subtraction button
            self.controls[0][2].setEnabled(True)
        elif len(self.controls) == 1:
            # or disable
            self.controls[0][2].setEnabled(False)

    def eventFilter(self, obj, event):
        """Capture loss of focus by controls."""
        if event.type() == qt.QEvent.Type.FocusOut:
            for row, c in enumerate(self.controls):
                if c[0] is obj:
                    self.dataChanged(row)
                    break
        return qt.QWidget.eventFilter(self, obj, event)

    def deleteRow(self):
        """Remove last row"""
        for w in self.controls[-1]:
            self.grid.removeWidget(w)
            w.deleteLater()
        self.controls.pop(-1)

        # disable first subtraction button
        if len(self.controls) == 1:
            self.controls[0][2].setEnabled(False)

    def addPressed(self, row):
        """User adds a new row."""
        val = list(self.setting.val)
        val.insert(row+1, '')
        self.sigSettingChanged.emit(self, self.setting, tuple(val))

    def subPressed(self, row):
        """User deletes a row."""
        val = list(self.setting.val)
        val.pop(row)
        self.sigSettingChanged.emit(self, self.setting, tuple(val))

    @qt.pyqtSlot()
    def onModified(self):
        """Called when the setting is changed remotely,
        or when control is opened"""

        s = self.setting

        if self.last == s.val:
            return
        self.last = s.val

        # update number of rows
        while len(self.setting.val) > len(self.controls):
            self.makeRow()
        while len(self.setting.val) < len(self.controls):
            self.deleteRow()

        # update values
        self.updateControls()

    def makeControl(self, row):
        """Override this to make an editing widget."""
        return None

    def updateControls(self):
        """Override this to update values in controls."""
        pass

    def readControl(self, cntrl):
        """Read value from control."""
        return None

    def dataChanged(self, row):
        """Update row of setitng with new data"""
        val = list(self.setting.val)
        val[row] = self.readControl( self.controls[row][0] )
        self.sigSettingChanged.emit(self, self.setting, tuple(val))

class Datasets(MultiSettingWidget):
    """A control for editing a list of datasets."""

    def __init__(self, setting, doc, dimensions, datatype, *args):
        """Contruct set of comboboxes"""

        MultiSettingWidget.__init__(self, setting, doc, *args)
        self.dimensions = dimensions
        self.datatype = datatype

        self.lastdatasets = []
        # force updating to initialise
        self.onModified()

    def makeControl(self, row):
        """Make QComboBox edit widget."""
        combo = qt.QComboBox()
        combo.setEditable(True)
        combo.lineEdit().editingFinished.connect(lambda: self.dataChanged(row))
        # if a different item is selected
        combo.textActivated[str].connect(lambda x: self.dataChanged(row))
        utils.populateCombo(combo, self.getDatasets())
        return combo

    def readControl(self, control):
        """Get text for control."""
        return control.lineEdit().text()

    def getDatasets(self):
        """Get applicable datasets (sorted)."""
        datasets = []
        for name, ds in self.document.data.items():
            if (ds.dimensions == self.dimensions and
                ds.datatype == self.datatype):
                datasets.append(name)
        datasets.sort()
        return datasets

    def updateControls(self):
        """Set values of controls."""
        for cntrls, val in zip(self.controls, self.setting.val):
            cntrls[0].lineEdit().setText(val)

    @qt.pyqtSlot()
    def onModified(self):
        """Called when the setting is changed remotely,
        or when control is opened"""

        MultiSettingWidget.onModified(self)

        datasets = self.getDatasets()

        if self.lastdatasets == datasets:
            return
        self.lastdatasets = datasets

        # update list of datasets
        for cntrls in self.controls:
            utils.populateCombo(cntrls[0], datasets)

class Strings(MultiSettingWidget):
    """A list of strings."""

    def __init__(self, setting, doc, *args):
        """Construct widget as combination of LineEdit and PushButton
        for browsing."""

        MultiSettingWidget.__init__(self, setting, doc, *args)
        self.onModified()

    def makeControl(self, row):
        """Make edit widget."""
        lineedit = qt.QLineEdit()
        lineedit.editingFinished.connect(lambda: self.dataChanged(row))
        return lineedit

    def readControl(self, control):
        """Get text for control."""
        return control.text()

    def updateControls(self):
        """Set values of controls."""
        for cntrls, val in zip(self.controls, self.setting.val):
            cntrls[0].setText(val)

class Filename(qt.QWidget):
    """A widget for selecting a filename with a browse button."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, mode, parent):
        """Construct widget as combination of LineEdit and PushButton
        for browsing.

        mode is 'image' or 'file'
        """

        qt.QWidget.__init__(self, parent)
        self.mode = mode
        self.setting = setting

        layout = qt.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)

        # the actual edit control
        self.edit = qt.QLineEdit()
        self.edit.setText( setting.toUIText() )
        layout.addWidget(self.edit, 1)

        b = self.button = DotDotButton(
            checkable=False, tooltip=_("Browse for file"))
        b.setMinimumWidth(28)
        layout.addWidget(b)

        # connect up signals
        self.edit.editingFinished.connect(self.validateAndSet)
        b.clicked.connect(self.buttonClicked)

        # completion support
        c = self.filenamecompleter = qt.QCompleter(self)
        model = qt.QFileSystemModel()
        c.setModel(model)
        self.edit.setCompleter(c)

        # for read only filenames
        if setting.readonly:
            self.edit.setReadOnly(True)

        self.setting.setOnModified(self.onModified)

    def buttonClicked(self):
        """Button clicked - show file open dialog."""

        title = _('Choose file')
        filefilter = _("All files (*)")
        if self.mode == 'image':
            title = _('Choose image')
            filefilter = (
                "Images (*.png *.jpg *.jpeg *.bmp *.svg *.tiff *.tif "
                "*.gif *.xbm *.xpm);;" + filefilter)
        
        elif self.mode == 'svg':
            title = _('Choose SVG file')
            filefilter = ("Images (*.svg);;" + filefilter)

        retn = qt.QFileDialog.getOpenFileName(
            self, title, self.edit.text(), filefilter)

        if retn:
            filename = retn[0]
            self.sigSettingChanged.emit(self, self.setting, filename)

    def validateAndSet(self):
        """Check the text is a valid setting and update it."""

        text = self.edit.text()
        try:
            val = self.setting.fromUIText(text)
            styleClear(self.edit)
            self.sigSettingChanged.emit(self, self.setting, val)

        except utils.InvalidType:
            styleError(self.edit)

    @qt.pyqtSlot()
    def onModified(self):
        """called when the setting is changed remotely"""
        self.edit.setText( self.setting.toUIText() )

class FontFamily(qt.QFontComboBox):
    """List the font families, showing each font."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)

    def __init__(self, setting, parent):
        """Create the combobox."""

        qt.QFontComboBox.__init__(self, parent)
        self.setting = setting
        self.setFontFilters( qt.QFontComboBox.FontFilter.ScalableFonts )

        # set initial value
        self.onModified()

        # stops combobox readjusting in size to fit contents
        self.setSizeAdjustPolicy(
            qt.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

        self.setting.setOnModified(self.onModified)

        # if a different item is selected
        self.textActivated[str].connect(self.slotActivated)

    def focusOutEvent(self, *args):
        """Allows us to check the contents of the widget."""
        qt.QFontComboBox.focusOutEvent(self, *args)
        self.slotActivated('')

    def slotActivated(self, val):
        """Update setting if a different item is chosen."""
        newval = self.currentText()
        self.sigSettingChanged.emit(self, self.setting, newval)

    @qt.pyqtSlot()
    def onModified(self):
        """Make control reflect chosen setting."""
        self.setCurrentFont( qt.QFont(self.setting.toUIText()) )

class FontStyle(qt.QComboBox):
    """Font style associated with font family."""

    sigSettingChanged = qt.pyqtSignal(qt.QObject, object, object)
    deftext = _('default')

    def __init__(self, setting, familysetting, parent):
        """Create the combobox."""

        qt.QComboBox.__init__(self, parent)
        self.setEditable(True)
        self.setting = setting
        self.familysetting = familysetting

        self.onModified()

        self.setting.setOnModified(self.onModified)
        self.familysetting.setOnModified(self.onModified)

        # if a different item is selected
        self.textActivated[str].connect(self.slotActivated)

    def slotActivated(self, val):
        """Update setting if a different item is chosen."""
        newval = self.currentText().strip()
        if newval == self.deftext:
            newval = ''
        self.sigSettingChanged.emit(self, self.setting, newval)

    @qt.pyqtSlot()
    def onModified(self):
        """Make control reflect chosen setting."""

        font_family = self.familysetting.get()
        styles = [self.deftext] + sorted(
            qt.QFontDatabase.styles(font_family))

        val = self.setting.get().strip()
        if not val:
            val = 'default'
        elif val not in styles:
            styles.append(val)

        utils.populateCombo(self, styles)
        idx = self.findText(val)
        self.setCurrentIndex(idx)

class ErrorStyle(Choice):
    """Choose different error bar styles."""

    _icons = None         # generated icons
    _errorstyles = None   # copied in by setting.py

    def __init__(self, setting, parent):
        if self._icons is None:
            self._generateIcons()

        Choice.__init__(
            self, setting, False,
            self._errorstyles, parent,
            icons=self._icons
        )

    @classmethod
    def _generateIcons(cls):
        """Generate a list of pixmaps for drop down menu."""
        cls._icons = []
        for errstyle in cls._errorstyles:
            cls._icons.append( utils.getIcon('error_%s' % errstyle) )

class Colormap(Choice):
    """Give the user a preview of colormaps.

    Based on Choice to make life easier
    """

    _icons = {}

    size = (32, 12)

    def __init__(self, setn, document, parent):
        names = sorted(document.evaluate.colormaps)

        icons = Colormap._generateIcons(document, names)
        Choice.__init__(
            self, setn, True,
            names, parent,
            icons=icons
        )
        self.setIconSize( qt.QSize(*self.size) )

    @classmethod
    def _generateIcons(kls, document, names):
        """Generate a list of icons for drop down menu."""

        # create a fake dataset smoothly varying from 0 to size[0]-1
        size = kls.size
        fakedataset = N.fromfunction(lambda x, y: y, (size[1], size[0]))

        # keep track of icons to return
        retn = []

        # iterate over colour maps
        for name in names:
            val = document.evaluate.colormaps.get(name, None)
            if name in kls._icons:
                icon = kls._icons[name]
            else:
                if val is None:
                    # empty icon
                    pixmap = qt.QPixmap(*size)
                    pixmap.fill(qt.Qt.GlobalColor.transparent)
                else:
                    # generate icon
                    image = utils.applyColorMap(
                        val, 'linear', fakedataset, 0., size[0]-1., 0)
                    pixmap = qt.QPixmap.fromImage(image)
                icon = qt.QIcon(pixmap)
                kls._icons[name] = icon
            retn.append(icon)
        return retn

class AxisBound(Choice):
    """Control for setting bounds of axis.

    This is to allow dates etc
    """

    def __init__(self, setting, *args):
        Choice.__init__(self, setting, True, ['Auto'], *args)

        modesetn = setting.parent.get('mode')
        modesetn.setOnModified(self.modeChange)

    @qt.pyqtSlot()
    def modeChange(self):
        """Called if the mode of the axis changes.
        Re-set text as float or date."""

        if self.currentText().lower() != 'auto':
            self.setEditText( self.setting.toUIText() )

