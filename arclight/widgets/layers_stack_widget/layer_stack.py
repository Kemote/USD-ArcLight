import os
from PySide6.QtWidgets import QListWidget, QAbstractItemView


class LayerStackItem:
    def __init__(self, path, name) -> None:
        self.path = path
        self.name = name
        
    def __repr__(self) -> str:
        return self.name


class LayerStackWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self._stack = {}
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def add_layer(self, path):
        layer_name = os.path.basename(path)
        new_item = LayerStackItem(path, layer_name)
        self._stack[layer_name] =  new_item
        self.addItem(str(new_item))

    def get_layer_item(self, layer_name):
        layer_item = self._stack.get(layer_name)
        return layer_item