from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from .usd_tree_item import UsdTreeItem


"""
Key Logic: You must implement the "Big Five" methods:

index(): Returns the address of an item.

parent(): Tells Qt who the parent folder of an item is.

rowCount(): Tells Qt how many files/subfolders are inside a folder.

columnCount(): How many columns (Name, Size, Date).

data(): Returns the actual text or icon for a specific item.
"""

class UsdTreeModel(QAbstractItemModel):
    def __init__(self, root_item):
        super().__init__()
        self.root_item = UsdTreeItem(root_item)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        child_item = parent_item.child(row)

        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()
    
    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        
        item = index.internalPointer()
        parent_item = item.parent_item

        if parent_item == self.root_item:
            return QModelIndex()
        
        return self.createIndex(parent_item.row(), 0, parent_item)
    
    def rowCount(self, parent=QModelIndex()):
        # wee need to check if column is 0 because we dont want to have 3d tree...
        if parent.column() > 0:
            return 0
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        return parent_item.child_count()
    
    def columnCount(self, parent=QModelIndex()):
        # more as place holder, in future I will do it as const
        return len(self.root_item.item_data)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return index.internalPointer().item_data[index.column()]
    
    def clear_tree(self):
        self.beginResetModel()
        self.removeRows(0, self.rowCount())
        self.endResetModel()