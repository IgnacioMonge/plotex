#    Copyright (C) 2026 M. Ignacio Monge García
#
#    This file is part of Plotex (fork of Veusz).
#
##############################################################################

"""Command Palette — quick access to all actions via keyboard (Ctrl+K)."""

from .. import qtall as qt


def _(text, disambiguation=None, context="CommandPalette"):
    return qt.QCoreApplication.translate(context, text, disambiguation)


class CommandPalette(qt.QDialog):
    """A VS Code-style command palette for quick action access."""

    def __init__(self, actions, parent=None):
        """actions: dict of name → QAction."""
        qt.QDialog.__init__(
            self, parent, qt.Qt.WindowType.Popup | qt.Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(qt.Qt.WidgetAttribute.WA_TranslucentBackground)
        # Popup auto-closes on focus loss but Qt keeps the widget alive
        # until the parent is destroyed. WA_DeleteOnClose releases the
        # palette + its captured QAction references promptly so a stale
        # action (deleted after a tab change, etc.) cannot be invoked
        # later.
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

        self._actions = {}
        for name, act in actions.items():
            if act is not None and act.text() and act.isEnabled():
                self._actions[name] = act

        self._setupUI()
        self._populateList("")

    def _setupUI(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # container with rounded corners and shadow
        container = qt.QFrame(self)
        container.setObjectName("paletteContainer")
        container.setStyleSheet("""
            #paletteContainer {
                background: white;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
        """)
        clayout = qt.QVBoxLayout(container)
        clayout.setContentsMargins(8, 8, 8, 4)
        clayout.setSpacing(4)

        # search input
        self._search = qt.QLineEdit()
        self._search.setPlaceholderText(_("Type a command..."))
        self._search.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1.5px solid #4A90D9;
            }
        """)
        self._search.textChanged.connect(self._onFilter)
        self._search.installEventFilter(self)
        clayout.addWidget(self._search)

        # results list
        self._list = qt.QListWidget()
        self._list.setStyleSheet("""
            QListWidget {
                border: none;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 3px;
            }
            QListWidget::item:selected {
                background: #e8f0fe;
                color: black;
            }
            QListWidget::item:hover {
                background: #f5f5f5;
            }
        """)
        self._list.setMaximumHeight(320)
        self._list.itemActivated.connect(self._onActivate)
        self._list.itemClicked.connect(self._onActivate)
        clayout.addWidget(self._list)

        layout.addWidget(container)

        # size
        self.setFixedWidth(450)

    def _populateList(self, filtertext):
        """Fill list with matching actions."""
        self._list.clear()
        self._matches = []
        ft = filtertext.strip().lower()

        for name, act in sorted(self._actions.items(), key=lambda x: x[1].text()):
            text = act.text().replace("&", "")
            shortcut = act.shortcut().toString()
            tooltip = act.toolTip() or ""

            # match against text, name, tooltip
            searchable = (text + " " + name + " " + tooltip).lower()
            if ft and ft not in searchable:
                continue

            # display text
            display = text
            if shortcut:
                display += "    %s" % shortcut

            item = qt.QListWidgetItem(display)
            if act.icon() and not act.icon().isNull():
                item.setIcon(act.icon())
            item.setData(qt.Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)
            self._matches.append(name)

        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _onFilter(self, text):
        self._populateList(text)

    def _onActivate(self, item):
        name = item.data(qt.Qt.ItemDataRole.UserRole)
        self.close()
        act = self._actions.get(name)
        if act and act.isEnabled():
            act.trigger()

    def eventFilter(self, obj, event):
        """Handle keyboard navigation in search field."""
        if obj is self._search and event.type() == qt.QEvent.Type.KeyPress:
            key = event.key()
            if key == qt.Qt.Key.Key_Escape:
                self.close()
                return True
            elif key in (qt.Qt.Key.Key_Down, qt.Qt.Key.Key_Up):
                # forward to list
                row = self._list.currentRow()
                if key == qt.Qt.Key.Key_Down:
                    row = min(row + 1, self._list.count() - 1)
                else:
                    row = max(row - 1, 0)
                self._list.setCurrentRow(row)
                return True
            elif key in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item:
                    self._onActivate(item)
                return True
        return qt.QDialog.eventFilter(self, obj, event)

    def showEvent(self, event):
        """Position palette at top center of parent."""
        qt.QDialog.showEvent(self, event)
        self._search.setFocus()
        if self.parentWidget():
            pw = self.parentWidget()
            x = pw.x() + (pw.width() - self.width()) // 2
            y = pw.y() + 80
            self.move(x, y)
