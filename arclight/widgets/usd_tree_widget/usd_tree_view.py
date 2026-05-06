from PySide6 import QtCore
from PySide6.QtCore import QItemSelection
from PySide6.QtWidgets import QTreeView, QAbstractItemView


class UsdTreeView(QTreeView):
    selection_changed_signal = QtCore.Signal(list)
    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAnimated(True)
        self.setIndentation(20)
        self.setHeaderHidden(False)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        selected_index = selected.indexes()
        deselected_index = deselected.indexes()
        
        if selected_index:
            selected_index = selected_index[0]
        else:
            selected_index = None
        
        if deselected_index:
            deselected_index = deselected_index[0]
        else:
            deselected_index = None

        self.selection_changed_signal.emit([selected_index, deselected_index])
        return super().selectionChanged(selected, deselected)