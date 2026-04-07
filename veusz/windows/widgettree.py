#    Copyright (C) 2010 Jeremy S. Sanders
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

"""Contains a model and view for handling a tree of widgets."""

from .. import qtall as qt
from .. import utils
from .. import document

def _(text, disambiguation=None, context="WidgetTree"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)

class _WidgetNode:
    """Class to represent widgets in WidgetTreeModel.

     parent: parent _WidgetNode
     widget: document widget node is representing
     children: child nodes
     data: tuple of data items, so we can see whether the node should
           be refreshed
     _child_index: dict mapping child node -> index for O(1) lookups
    """

    def __init__(self, parent, widget):
        self.parent = parent
        self.widget = widget
        self.children = []
        self._child_index = {}
        self.data = self.getData()

    def indexOf(self, child):
        """O(1) index lookup for a child node."""
        return self._child_index[child]

    def _rebuildIndex(self):
        """Rebuild the child index mapping."""
        self._child_index = {c: i for i, c in enumerate(self.children)}

    def insertChild(self, index, child):
        """Insert child at index and update index mapping."""
        self.children.insert(index, child)
        # only rebuild from insertion point
        for i in range(index, len(self.children)):
            self._child_index[self.children[i]] = i

    def removeChild(self, index):
        """Remove child at index and update index mapping."""
        removed = self.children[index]
        del self._child_index[removed]
        del self.children[index]
        # only rebuild from removal point
        for i in range(index, len(self.children)):
            self._child_index[self.children[i]] = i
        return removed

    def getData(self):
        """Get the latest version of the data."""
        w = self.widget
        parenthidden = False if self.parent is None else self.parent.data[3]
        hidden = parenthidden or ("hide" in w.settings and w.settings.hide)
        return (
            w.name,
            w.typename,
            w.userdescription,
            hidden,
        )

    def __repr__(self):
        return "<_WidgetNode widget:%s>" % repr(self.widget)

class WidgetTreeModel(qt.QAbstractItemModel):
    """A model representing the widget tree structure.

    We hide the actual widgets behind a tree of _WidgetNode
    objects. The syncTree method synchronises the tree in the model to
    the tree in the document. It works out which nodes to be deleted,
    which to be added and which to be moved around. It informs the
    view that the data are being changed using the standard
    begin... and end... functions. The synchronisation code is a bit
    hairy and is hopefully correct.

    This extra layer is necessary as the model requires that the
    document underneath it can't be changed until the view knows its
    about to be changed.

    """

    def __init__(self, document, parent=None):
        """Initialise using document."""

        qt.QAbstractItemModel.__init__(self, parent)

        self.document = document

        document.signalModified.connect(self.slotDocumentModified)
        document.sigWiped.connect(self.deleteTree)

        # root node of document
        self.rootnode = _WidgetNode(None, document.basewidget)
        # map of widgets to nodes
        self.widgetnodemap = {self.rootnode.widget: self.rootnode}
        self.syncTree()

    def deleteTree(self):
        """Reset tree contents (for loading docs, etc)."""
        self.beginRemoveRows(
            self.nodeIndex(self.rootnode),
            0, len(self.rootnode.children))
        self.rootnode.widget = self.document.basewidget
        del self.rootnode.children[:]
        self.widgetnodemap = {self.rootnode.widget: self.rootnode}
        self.endRemoveRows()

    def slotDocumentModified(self):
        """The document has been changed."""
        self.syncTree()

    def syncTree(self):
        """Synchronise tree to document in a single pass."""

        # collect all widgets currently in the document
        docwidgets = set()
        def recursecollect(widget):
            docwidgets.add(widget)
            for child in widget.children:
                recursecollect(child)
        recursecollect(self.rootnode.widget)

        self._recursiveupdate(self.rootnode.widget, docwidgets)

    def _recursiveupdate(self, widget, docwidgets):
        """Recursively remove, add and move nodes to correct place.

        widget: widget to operate below
        docwidgets: all widgets used in the document
        """

        node = self.widgetnodemap[widget]

        # delete non-existent child nodes (reverse order for stable indices)
        for nch in node.children[::-1]:
            if nch.widget not in docwidgets:
                self._recursivedelete(nch)

        # iterate over document children and sync
        for i in range(len(widget.children)):
            c = widget.children[i]
            add = False
            if c not in self.widgetnodemap:
                # add new widget
                self.beginInsertRows(self.nodeIndex(node), i, i)
                self.widgetnodemap[c] = cnode = _WidgetNode(node, c)
                node.insertChild(i, cnode)
                self.endInsertRows()
                add = True

            elif (i >= len(node.children) or
                  c is not node.children[i].widget or
                  c.parent is not node.children[i].parent.widget):
                # move widget — use O(1) indexOf
                cnode = self.widgetnodemap[c]
                oldparent = cnode.parent
                oldrow = oldparent.indexOf(cnode)

                oldidx = self.nodeIndex(oldparent)
                newidx = oldidx if oldparent is node else self.nodeIndex(node)

                self.beginMoveRows(oldidx, oldrow, oldrow, newidx, i)
                oldparent.removeChild(oldrow)
                node.insertChild(i, cnode)
                cnode.parent = node
                self.endMoveRows()

            if not add:
                # update data if changed
                cnode = self.widgetnodemap[c]
                data = cnode.getData()
                if cnode.data != data:
                    idx0 = self.nodeIndex(cnode)
                    idx2 = self.index(idx0.row(), 2, idx0.parent())
                    cnode.data = data
                    self.dataChanged.emit(idx0, idx2)

            self._recursiveupdate(c, docwidgets)

    def _recursivedelete(self, node):
        """Recursively delete node and its children."""
        for cnode in node.children[::-1]:
            self._recursivedelete(cnode)
        parentnode = node.parent
        if parentnode is not None:
            row = parentnode.indexOf(node)
            self.beginRemoveRows(self.nodeIndex(parentnode), row, row)
            parentnode.removeChild(row)
            del self.widgetnodemap[node.widget]
            self.endRemoveRows()

    def columnCount(self, parent):
        """Return number of columns of data."""
        return 3

    def rowCount(self, index):
        """Return number of rows of children of index."""

        if index.isValid():
            return len(index.internalPointer().children)
        else:
            # always 1 root node
            return 1

    def data(self, index, role):
        """Return data for the index given.

        Uses the data from the _WidgetNode class.

        """

        if not index.isValid():
            return None

        column = index.column()
        data = index.internalPointer().data

        if role in (qt.Qt.ItemDataRole.DisplayRole, qt.Qt.ItemDataRole.EditRole):
            # return text for columns
            if column == 0:
                return data[0]
            elif column == 1:
                return data[1]

        elif role == qt.Qt.ItemDataRole.DecorationRole:
            if column == 0:
                # return widget type icon
                filename = 'button_%s' % data[1]
                return utils.getIcon(filename)
            elif column == 2:
                # return visibility icon (eye) for applicable widgets
                widget = index.internalPointer().widget
                if _widgetHasVisibility(widget):
                    if widget.settings.hide:
                        return utils.getIcon('eye-hide')
                    else:
                        return utils.getIcon('eye-show')

        elif role == qt.Qt.ItemDataRole.ToolTipRole:
            if column == 2:
                return _('Toggle visibility')
            return data[2]

        elif role == qt.Qt.ItemDataRole.ForegroundRole:
            # show disabled looking text if object or any parent is hidden
            # return brush for hidden widget text, based on disabled text
            if data[3]:
                return qt.QPalette().brush(
                    qt.QPalette.ColorGroup.Disabled, qt.QPalette.ColorRole.Text)

        # return nothing
        return None

    def setData(self, index, name, role):
        """User renames object. This renames the widget."""

        if not index.isValid():
            return False

        widget = index.internalPointer().widget

        # check symbols in name
        if not utils.validateWidgetName(name):
            return False

        # check name not already used
        if widget.parent.hasChild(name):
            return False

        # actually rename the widget
        self.document.applyOperation(
            document.OperationWidgetRename(widget, name))

        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        """What we can do with the item."""

        if not index.isValid():
            return qt.Qt.ItemFlag.ItemIsEnabled

        flags = (
            qt.Qt.ItemFlag.ItemIsEnabled | qt.Qt.ItemFlag.ItemIsSelectable |
            qt.Qt.ItemFlag.ItemIsDropEnabled
        )
        if ( index.internalPointer().parent is not None and
             index.column() == 0 ):
            # allow items other than root to be edited and dragged
            flags = flags | qt.Qt.ItemFlag.ItemIsEditable | qt.Qt.ItemFlag.ItemIsDragEnabled

        return flags

    def headerData(self, section, orientation, role):
        """Return the header of the tree."""

        if orientation == qt.Qt.Orientation.Horizontal and role == qt.Qt.ItemDataRole.DisplayRole:
            val = ('Name', 'Type', '')[section]
            return val
        return None

    def nodeIndex(self, node):
        row = 0 if node.parent is None else node.parent.indexOf(node)
        return self.createIndex(row, 0, node)

    def index(self, row, column, parent):
        """Construct an index for a child of parent."""

        if parent.isValid():
            # normal widget
            try:
                child = parent.internalPointer().children[row]
            except IndexError:
                return qt.QModelIndex()
        else:
            # root widget
            child = self.rootnode
        return self.createIndex(row, column, child)

    def getWidgetIndex(self, widget):
        """Returns index for widget specified."""

        if widget not in self.widgetnodemap:
            return None
        node = self.widgetnodemap[widget]
        parent = node.parent
        row = 0 if parent is None else parent.indexOf(node)
        return self.createIndex(row, 0, node)

    def parent(self, index):
        """Find the parent of the index given."""

        if not index.isValid():
            return qt.QModelIndex()

        parent = index.internalPointer().parent
        if parent is None:
            return qt.QModelIndex()
        else:
            gparent = parent.parent
            row = 0 if gparent is None else gparent.indexOf(parent)
            return self.createIndex(row, 0, parent)

    def getSettings(self, index):
        """Return the settings for the index selected."""
        return index.internalPointer().widget.settings

    def getWidget(self, index):
        """Get associated widget for index selected."""
        return index.internalPointer().widget

    def removeRows(self, row, count, parentindex):
        """Remove widgets from parent.

        This is used by the mime dragging and dropping
        """

        if not parentindex.isValid():
            return

        parent = self.getWidget(parentindex)

        # make an operation to delete the rows
        deleteops = []
        for w in parent.children[row:row+count]:
            deleteops.append( document.OperationWidgetDelete(w) )
        op = document.OperationMultiple(deleteops, descr=_("remove widgets"))
        self.document.applyOperation(op)
        return True

    def supportedDropActions(self):
        """Supported drag and drop actions."""
        return qt.Qt.DropAction.MoveAction | qt.Qt.DropAction.CopyAction

    def mimeData(self, indexes):
        """Get mime data for indexes."""
        widgets = [idx.internalPointer().widget for idx in indexes]
        return document.generateWidgetsMime(widgets)

    def mimeTypes(self):
        """Accepted mime types."""
        return [document.widgetmime]

    def dropMimeData(self, mimedata, action, row, column, parentindex):
        """User drags and drops widget."""

        if action == qt.Qt.DropAction.IgnoreAction:
            return True

        data = document.getWidgetMime(mimedata)
        if data is None:
            return False

        if parentindex.isValid():
            parent = self.getWidget(parentindex)
        else:
            parent = self.document.basewidget

        # check parent supports child
        if not document.isMimeDropable(parent, data):
            return False

        # work out where row will be pasted
        startrow = row
        if row == -1:
            startrow = len(parent.children)

        op = document.OperationWidgetPaste(parent, data, index=startrow)
        self.document.applyOperation(op)
        return True


# widget types that should not show visibility toggle
_no_visibility_types = frozenset(('document', 'page'))

def _widgetHasVisibility(widget):
    """Check if widget should have a visibility toggle."""
    return (
        widget.typename not in _no_visibility_types and
        "hide" in widget.settings
    )

class WidgetTreeView(qt.QTreeView):
    """A model view for viewing the widgets."""

    def __init__(self, model, *args):
        qt.QTreeView.__init__(self, *args)
        self.setModel(model)
        self.expandAll()

        # stretch header
        hdr = self.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, qt.QHeaderView.ResizeMode.Custom)
        hdr.setSectionResizeMode(2, qt.QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(2, 24)

        # setup drag and drop
        self.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def mousePressEvent(self, event):
        """Intercept clicks on visibility column before tree processes them."""
        index = self.indexAt(event.pos())
        if (index.isValid() and index.column() == 2 and
                event.button() == qt.Qt.MouseButton.LeftButton):
            widget = index.internalPointer().widget
            if _widgetHasVisibility(widget):
                newval = not widget.settings.hide
                op = document.OperationSettingSet(
                    widget.settings.get('hide'), newval)
                self.model().document.applyOperation(op)
                event.accept()
                return
        qt.QTreeView.mousePressEvent(self, event)

    def testModifier(self, e):
        """Look for keyboard modifier for copy or move."""
        if e.modifiers() & qt.Qt.KeyboardModifier.ControlModifier:
            e.setDropAction(qt.Qt.DropAction.CopyAction)
        else:
            e.setDropAction(qt.Qt.DropAction.MoveAction)

    def handleInternalMove(self, event):
        """Handle a move inside treeview."""

        # make sure qt doesn't handle this
        event.setDropAction(qt.Qt.DropAction.IgnoreAction)
        event.ignore()

        pos = event.position().toPoint()
        if not self.viewport().rect().contains(pos):
            return

        # get widget at event position
        index = self.indexAt(pos)
        if not index.isValid():
            index = self.rootIndex()

        # adjust according to drop indicator position
        row = -1
        posn = self.dropIndicatorPosition()
        if posn == qt.QAbstractItemView.DropIndicatorPosition.AboveItem:
            row = index.row()
            index = index.parent()
        elif posn == qt.QAbstractItemView.DropIndicatorPosition.BelowItem:
            row = index.row() + 1
            index = index.parent()

        if index.isValid():
            parent = self.model().getWidget(index)
            data = document.getWidgetMime(event.mimeData())
            if document.isMimeDropable(parent, data):
                # move the widget!
                parentpath = parent.path
                widgetpaths = document.getMimeWidgetPaths(data)
                ops = []
                r = row
                for path in widgetpaths:
                    ops.append(
                        document.OperationWidgetMove(path, parentpath, r) )
                    if r >= 0:
                        r += 1

                self.model().document.applyOperation(
                    document.OperationMultiple(ops, descr='move'))
                event.ignore()

    def dropEvent(self, e):
        """When an object is dropped on the view."""
        self.testModifier(e)

        if e.source() is self and e.dropAction() == qt.Qt.DropAction.MoveAction:
            self.handleInternalMove(e)

        qt.QTreeView.dropEvent(self, e)

    def dragMoveEvent(self, e):
        """Make items move by default and copy if Ctrl is held down."""
        self.testModifier(e)

        qt.QTreeView.dragMoveEvent(self, e)
