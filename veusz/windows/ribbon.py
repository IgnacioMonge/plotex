"""Ribbon UI components for Plotex — Office-style tabbed toolbar."""

from .. import qtall as qt
from .. import setting


class RibbonSeparator(qt.QFrame):
    """Vertical separator between ribbon groups."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(qt.QFrame.Shape.VLine)
        self.setFrameShadow(qt.QFrame.Shadow.Sunken)
        self.setObjectName("ribbonSeparator")


class RibbonLargeButton(qt.QToolButton):
    """Large button with icon on top and text below."""
    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.setDefaultAction(action)
        self.setToolButtonStyle(
            qt.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        s = setting.settingdb['toolbar_size']
        self.setIconSize(qt.QSize(s, s))
        self.setAutoRaise(True)
        self.setObjectName("ribbonLargeButton")
        self.setSizePolicy(
            qt.QSizePolicy.Policy.Preferred,
            qt.QSizePolicy.Policy.Expanding)
        if action.menu():
            self.setPopupMode(
                qt.QToolButton.ToolButtonPopupMode.MenuButtonPopup)


class RibbonSmallButton(qt.QToolButton):
    """Small button with icon and text beside."""
    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.setDefaultAction(action)
        self.setToolButtonStyle(
            qt.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        s = max(setting.settingdb['toolbar_size'] * 2 // 3, 12)
        self.setIconSize(qt.QSize(s, s))
        self.setAutoRaise(True)
        self.setObjectName("ribbonSmallButton")
        if action.menu():
            self.setPopupMode(
                qt.QToolButton.ToolButtonPopupMode.MenuButtonPopup)


class RibbonGroup(qt.QWidget):
    """Group of buttons with a title label at the bottom."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbonGroup")

        mainlayout = qt.QVBoxLayout(self)
        mainlayout.setContentsMargins(4, 2, 4, 0)
        mainlayout.setSpacing(1)

        self._content = qt.QHBoxLayout()
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(2)
        self._content.setAlignment(
            qt.Qt.AlignmentFlag.AlignLeft |
            qt.Qt.AlignmentFlag.AlignVCenter)

        label = qt.QLabel(title)
        label.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        label.setObjectName("ribbonGroupTitle")

        mainlayout.addLayout(self._content, 1)
        mainlayout.addWidget(label)

    def addLargeButton(self, action):
        """Add a large button for the given action."""
        btn = RibbonLargeButton(action, self)
        self._content.addWidget(btn)
        return btn

    def addSmallColumn(self, actions):
        """Add a vertical column of up to 3 small buttons."""
        col = qt.QVBoxLayout()
        col.setSpacing(0)
        col.setContentsMargins(0, 0, 0, 0)
        for action in actions:
            btn = RibbonSmallButton(action, self)
            col.addWidget(btn)
        for _ in range(3 - len(actions)):
            col.addStretch()
        self._content.addLayout(col)


class RibbonTab(qt.QWidget):
    """Single ribbon tab containing groups arranged horizontally."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbonTab")
        self._layout = qt.QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        self._groups = []

    def addGroup(self, title):
        """Add a titled group and return it."""
        group = RibbonGroup(title, self)
        idx = self._layout.count() - 1  # before the stretch
        if self._groups:
            sep = RibbonSeparator(self)
            self._layout.insertWidget(idx, sep)
            idx += 1
        self._layout.insertWidget(idx, group)
        self._groups.append(group)
        return group


class RibbonBar(qt.QWidget):
    """Office-style ribbon bar with tabbed groups of buttons."""

    # emitted when the ribbon is collapsed or expanded
    collapseToggled = qt.pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbonBar")
        self._collapsed = False
        self._expandedHeight = 110

        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # top row: tabbar + collapse button
        toprow = qt.QHBoxLayout()
        toprow.setContentsMargins(0, 0, 0, 0)
        toprow.setSpacing(0)

        self._tabbar = qt.QTabBar(self)
        self._tabbar.setObjectName("ribbonTabBar")
        self._tabbar.setExpanding(False)
        self._tabbar.setDrawBase(False)
        toprow.addWidget(self._tabbar, 1)

        self._collapseBtn = qt.QToolButton(self)
        self._collapseBtn.setObjectName("ribbonCollapseBtn")
        self._collapseBtn.setText('\u25B2')  # ▲
        self._collapseBtn.setToolTip('Collapse ribbon')
        self._collapseBtn.setAutoRaise(True)
        self._collapseBtn.setFixedSize(22, 22)
        self._collapseBtn.clicked.connect(self.toggleCollapse)
        toprow.addWidget(self._collapseBtn)

        layout.addLayout(toprow)

        self._stack = qt.QStackedWidget(self)
        self._stack.setObjectName("ribbonStack")
        layout.addWidget(self._stack)

        self._tabbar.currentChanged.connect(self._stack.setCurrentIndex)

        self.setFixedHeight(self._expandedHeight)
        self._tabs = {}

    def toggleCollapse(self):
        """Toggle between collapsed (tabs only) and expanded."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._stack.hide()
            self.setFixedHeight(self._tabbar.sizeHint().height() + 4)
            self._collapseBtn.setText('\u25BC')  # ▼
            self._collapseBtn.setToolTip('Expand ribbon')
        else:
            self._stack.show()
            self.setFixedHeight(self._expandedHeight)
            self._collapseBtn.setText('\u25B2')  # ▲
            self._collapseBtn.setToolTip('Collapse ribbon')
        self.collapseToggled.emit(self._collapsed)

    def addTab(self, name, key=None):
        """Add a tab and return its RibbonTab widget."""
        tab = RibbonTab(self)
        self._tabbar.addTab(name)
        self._stack.addWidget(tab)
        if key:
            self._tabs[key] = tab
        return tab

    def tab(self, key):
        """Look up a tab by key."""
        return self._tabs.get(key)

    def setIconSize(self, size):
        """Update icon sizes for all ribbon buttons and adjust height."""
        large = qt.QSize(size, size)
        small = qt.QSize(max(size * 2 // 3, 12), max(size * 2 // 3, 12))
        for btn in self.findChildren(RibbonLargeButton):
            btn.setIconSize(large)
        for btn in self.findChildren(RibbonSmallButton):
            btn.setIconSize(small)
        # adapt ribbon height: icon + text + group label + margins
        self._expandedHeight = size + 70
        if not self._collapsed:
            self.setFixedHeight(self._expandedHeight)
