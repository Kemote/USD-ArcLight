import os
import sys

from PySide6 import QtWidgets, QtCore, QtGui
from core.usd_engine import *
from widgets.usd_tree_widget.usd_tree_delegate import UsdTreeDelegate
from widgets.usd_tree_widget.usd_tree_model import UsdTreeModel
from widgets.usd_tree_widget.usd_tree_view import UsdTreeView
from widgets.usd_tree_widget.usd_tree_item import UsdTreeItem
from widgets.hydra_viewport.viewport import UsdViewportWidget


class ArcLightMainWindow(QtWidgets.QMainWindow):
    stage_opened_signal = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("ArcLight - USD Composition Explorer")
        self.resize(1200, 720)
        
        self.stage = Usd.Stage.CreateInMemory()

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        # create menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        close_action = QtGui.QAction("Close", self)
        close_action.
        open_action = QtGui.QAction("Open USD file", self)
        open_action.triggered.connect(self._open_layer)
        file_menu.addAction(open_action)

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

        # create main layout
        self.main_layout = QtWidgets.QGridLayout()
        self.central_widget.setLayout(self.main_layout)
        self.main_layout.addWidget(self.usd_tree_view, 0, 0)
        self.main_layout.addWidget(self.prim_stack_table, 1, 0)
        self.main_layout.addWidget(self.viewport, 0, 1)

        #connect signals
        self.usd_tree_view.selection_changed_signal.connect(self._refresh_prim_stack)

    def _open_layer(self):
        open_dialog = QtWidgets.QFileDialog(self)
        open_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        open_dialog.setWindowTitle("Open USD file...")
        file_path = open_dialog.getOpenFileName(filter="(*.usd *.usda *.usdc *.usdz)")[0]
        if os.path.exists(file_path):
            self.stage = open_stage(file_path)
            if self.stage:
                self._load_stage_to_viewport()
                self._load_stage_to_tree()
                self.stage_opened_signal.emit(True)
            else:
                self.stage_opened_signal.emit(False)

    def _load_stage_to_viewport(self):
        self.viewport.set_stage(self.stage)

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

# TODO czy to potrzebne??
def setup_usd_environment(verbose=False):
    # Set environment variables
    USD_INSTALL_PATH = '/home/kemot/USD'
    os.environ['USD_INSTALL_ROOT'] = USD_INSTALL_PATH
    os.environ['PYTHONPATH'] = f"{USD_INSTALL_PATH}/lib/python:{os.environ.get('PYTHONPATH', '')}"
    os.environ['PATH'] = f"{USD_INSTALL_PATH}/bin:{os.environ.get('PATH', '')}"

    # Set DYLD_LIBRARY_PATH to include the USD library paths
    usd_lib_path = os.path.join(USD_INSTALL_PATH, 'lib')
    os.environ['DYLD_LIBRARY_PATH'] = f"{usd_lib_path}:{os.environ.get('DYLD_LIBRARY_PATH', '')}"

    # Manually append the USD Python library path
    usd_python_path = os.path.join(USD_INSTALL_PATH, 'lib', 'python')
    if usd_python_path not in sys.path:
        sys.path.append(usd_python_path)

    if verbose:
        # Print environment variables for debugging
        print(f"USD_INSTALL_ROOT: {os.environ['USD_INSTALL_ROOT']}")
        print(f"PYTHONPATH: {os.environ['PYTHONPATH']}")
        print(f"PATH: {os.environ['PATH']}")
        print(f"DYLD_LIBRARY_PATH: {os.environ['DYLD_LIBRARY_PATH']}")
        print(f"sys.path: {sys.path}")



# sp[rawdzic czemu to sie nie doswierza tzn po wczytaniu stagu?

if __name__ == "__main__":
    # need to use that for rocky linux
    setup_usd_environment()
    if sys.platform.startswith("linux"):
        if "QT_QPA_PLATFORM" not in os.environ:
            if "WAYLAND_DISPLAY" in os.environ:
                os.environ["QT_QPA_PLATFORM"] = "xcb"
    
    app = QtWidgets.QApplication(sys.argv)
    window = ArcLightMainWindow()
    window.show()
    sys.exit(app.exec())