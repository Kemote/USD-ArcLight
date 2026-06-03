import os
import sys

from PySide6 import QtWidgets, QtCore, QtGui
from widgets.usd_tree_widget.usd_tree_delegate import UsdTreeDelegate
from widgets.usd_tree_widget.usd_tree_model import UsdTreeModel
from widgets.usd_tree_widget.usd_tree_view import UsdTreeView
from widgets.usd_tree_widget.usd_tree_item import UsdTreeItem
from widgets.hydra_viewport_widget.viewport import UsdViewportWidget
from widgets.layers_stack_widget.layer_stack import LayerStackWidget
from core.usd_engine import *


class ArcLightMainWindow(QtWidgets.QMainWindow):
    layer_loaded_signal = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("ArcLight - USD Composition Explorer")
        self.resize(1200, 720)
        
        self.stage = create_in_memmory_stage()
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        # create menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        open_action = QtGui.QAction("Load USD file", self)
        open_action.triggered.connect(self._load_layer)
        close_action = QtGui.QAction("Close", self)
        close_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(close_action)

        # create USD tree view
        self.usd_tree_model = UsdTreeModel(["PrimName", "PrimSpec"])
        self.usd_tree_delegate = UsdTreeDelegate()
        self.usd_tree_view = UsdTreeView()
        self.usd_tree_view.setModel(self.usd_tree_model)
        self.usd_tree_view.setItemDelegate(self.usd_tree_delegate)

        # create list widget for prim stack
        self.prim_stack_table = QtWidgets.QTableWidget()
        self.prim_stack_table.setSizeAdjustPolicy(
            QtWidgets.QTableWidget.SizeAdjustPolicy.AdjustToContents)
        self.prim_stack_table.setColumnCount(4)
        columns_headers = ["Intorducing Layer:", "Introducing Prim", "Arc Type:", "Is Implicit"]
        self.prim_stack_table.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.prim_stack_table.setHorizontalHeaderLabels(columns_headers)

        # create USD viewport
        self.viewport = UsdViewportWidget(self.stage)
        self.viewport.set_stage(self.stage)

        # create layer stack
        self.layer_stack = LayerStackWidget()
        self.layer_stack.model().rowsMoved.connect(self._layer_order_changed)

        # create main layout
        self.main_layout = QtWidgets.QGridLayout()
        self.central_widget.setLayout(self.main_layout)
        self.main_layout.addWidget(self.usd_tree_view, 0, 0)
        self.main_layout.addWidget(self.prim_stack_table, 1, 0)
        self.main_layout.addWidget(self.viewport, 0, 1)
        self.main_layout.addWidget(self.layer_stack, 1, 1)

        #connect signals
        self.usd_tree_view.selection_changed_signal.connect(self._refresh_prim_stack)
        self.layer_loaded_signal.connect(self.viewport.layer_loaded)

    def _layer_order_changed(self):
        root_layer = self.stage.GetRootLayer()
        sub_layers = root_layer.subLayerPaths
        sub_layers.clear()

        for item_index in range(self.layer_stack.count()):
            # TODO!! Tutaj jest babol coś się wali prz przechwyceniu nazwy
            list_item = self.layer_stack.item(item_index)
            layer_item = self.layer_stack.get_layer_item(list_item.text())
            if layer_item:
                sub_layers.append(layer_item.path)
        
        self._load_stage_to_tree()

    def _load_layer(self):
        open_dialog = QtWidgets.QFileDialog(self)
        open_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        open_dialog.setWindowTitle("Open USD file...")
        file_path = open_dialog.getOpenFileName(filter="(*.usd *.usda *.usdc *.usdz)")[0]
        if os.path.exists(file_path):
            # add new sublayer to main stage
            root_layer = self.stage.GetRootLayer() 
            root_layer.subLayerPaths.append(file_path)
            self.layer_stack.add_layer(file_path)
            self._load_stage_to_tree()
            self.layer_loaded_signal.emit(file_path)            

    def _load_stage_to_tree(self):
        """
        INFO
        Sdf.Layer.Traverse rozni sie do Usd.Stage.Traverse tym, ze ten pierwszy
        PrimSpec w zasadzie ejst swego rodzaju opinia w USD, natomiast UsdPrim jest
        jiuz gotowa kompozycja.

        """
        self.usd_tree_model.clear_tree()

        parent_nodes = {"": self.usd_tree_model.root_item}
        for prim in self.stage.TraverseAll(): # type: ignore
            prim_composition = list(get_prim_compostion_data(prim))            
            prim_path = prim.GetPrimPath()
            parent_path = prim_path.pathString.removesuffix(f"/{prim_path.name}")
            parent_item = parent_nodes[parent_path]
            new_item = UsdTreeItem([prim_path.name, 
                                    prim.GetSpecifier().name,
                                    prim_composition],
                                    parent_item)
            parent_nodes[prim_path.pathString] = new_item
            parent_item.append_child(new_item)
            
    def _refresh_prim_stack(self, selection_list):
        self.prim_stack_table.clearContents()
        selected_index = selection_list[0]
        if selected_index:
            item_object = selected_index.internalPointer()
            prim_stack_list = item_object.prim_stack
            self.prim_stack_table.setRowCount(len(prim_stack_list))
            for row, prim_stack in enumerate(prim_stack_list):
                for column, data_str in enumerate(prim_stack):
                    table_item = QtWidgets.QTableWidgetItem(str(data_str))
                    self.prim_stack_table.setItem(row, column, table_item)
            self.prim_stack_table.resizeColumnsToContents()


if __name__ == "__main__":
    # need to use that for rocky linux
    if sys.platform.startswith("linux"):
        if "QT_QPA_PLATFORM" not in os.environ:
            if "WAYLAND_DISPLAY" in os.environ:
                os.environ["QT_QPA_PLATFORM"] = "xcb"
    
    app = QtWidgets.QApplication(sys.argv)
    window = ArcLightMainWindow()
    window.show()
    sys.exit(app.exec())