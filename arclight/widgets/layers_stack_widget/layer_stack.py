import os
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QListWidget, 
                               QAbstractItemView, 
                               QWidget, 
                               QVBoxLayout,
                               QHBoxLayout, 
                               QPushButton)


class LayerStackItem:
    def __init__(self, path, name) -> None:
        self.path = path
        self.name = name
        
    def __repr__(self) -> str:
        return self.name


class LayerStackWidget(QWidget):
    load_sublayer_signal = Signal()
    delete_signal = Signal(bool)
    
    def __init__(self):
        super().__init__()
        self.list = LayerStackListWidget()
              
        load_btn = QPushButton("Add sublayer")
        load_btn.clicked.connect(self._add_sublayer)
        delete_btn = QPushButton("Delete selected")
        delete_btn.clicked.connect(self._delete)
        panel_layout = QHBoxLayout()
        panel_layout.addWidget(load_btn)
        panel_layout.addWidget(delete_btn)

        widget_layout = QVBoxLayout()
        widget_layout.addLayout(panel_layout)
        widget_layout.addWidget(self.list)
        
        self.setLayout(widget_layout)

    @property
    def items_count(self):
        return self.list.count()
    
    @property
    def list_model(self):
        return self.list.model()

    def add_layer(self, file_path):
        self.list.add_layer(file_path)

    def get_item_by_index(self, index):
        return self.list.item(index)

    def get_layer_item(self, list_item):
        return self.list.get_layer_item(list_item.text())
    
    def _add_sublayer(self):
        self.load_sublayer_signal.emit()

    def _delete(self):
        for index in self.list.selectedIndexes():
            self.list.takeItem(index.row())
        self.delete_signal.emit(True)

    def delete_all(self):
        self.list.clear()


class LayerStackListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self._stack = {}
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def add_layer(self, path):
        layer_name = os.path.basename(path)
        new_item = LayerStackItem(path, layer_name)
        self._stack[layer_name] =  new_item
        self.addItem(str(new_item))

    def get_layer_item(self, layer_name):
        layer_item = self._stack.get(layer_name)
        return layer_item