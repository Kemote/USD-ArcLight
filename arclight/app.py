import os
import sys

from PySide6 import QtWidgets, QtCore, QtGui
from core.usd_engine import *
from widgets.usd_tree_widget.usd_tree_delegate import UsdTreeDelegate
from widgets.usd_tree_widget.usd_tree_model import UsdTreeModel
from widgets.usd_tree_widget.usd_tree_view import UsdTreeView
from widgets.usd_tree_widget.usd_tree_item import UsdTreeItem


class ArcLightMainWindow(QtWidgets.QMainWindow):
    stage_opened_signal = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("ArcLight - USD Composition Explorer")
        self.resize(1200, 720)
        self.stage = None

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        # create menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        open_action = QtGui.QAction("Open USD file", self)
        open_action.triggered.connect(self._open_layer)
        file_menu.addAction(open_action)

        # create USD tree view
        self.usd_tree_model = UsdTreeModel(["PrimName", "PrimSpec"])
        self.usd_tree_delegate = UsdTreeDelegate()
        self.usd_tree_view = UsdTreeView()
        self.usd_tree_view.setModel(self.usd_tree_model)
        self.usd_tree_view.setItemDelegate(self.usd_tree_delegate)

        # Adding sample items
        # root = self.usd_tree_model.root_item
        # folder1 = UsdTreeItem(["Documents", "Folder"], root)
        # root.append_child(folder1)
        # folder1.append_child(UsdTreeItem(["Resume.pdf", "File"], folder1))

        # create main layout
        self.main_layout = QtWidgets.QGridLayout()
        self.central_widget.setLayout(self.main_layout )
        self.main_layout.addWidget(self.usd_tree_view, 0, 0)

    def _open_layer(self):
        open_dialog = QtWidgets.QFileDialog(self)
        open_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        open_dialog.setWindowTitle("Open USD file...")
        file_path = open_dialog.getOpenFileName(filter="(*.usd *.usda *.usdc)")[0]
        if os.path.exists(file_path):
            self.stage = open_stage(file_path)
            if self.stage:
                self._load_stage_to_tree()
                self.stage_opened_signal.emit(True)
            else:
                self.stage_opened_signal.emit(False)

    def _load_stage_to_tree(self):
        """
        Sdf.Layer.Traverse rozni sie do Usd.Stage.Traverse tym, ze ten pierwszy
        PrimSpec w zasadzie ejst swego rodzaju opinia w USD, natomiast UsdPrim jest
        jiuz gotowa kompozycja.

        """
        self.usd_tree_model.clear_tree()

        parent_nodes = {"": self.usd_tree_model.root_item}
        for prim in self.stage.TraverseAll(): # type: ignore
            prim_path = prim.GetPrimPath()
            parent_path = prim_path.pathString.removesuffix(f"/{prim_path.name}")
            parent_item = parent_nodes.get(parent_path)
            new_item = UsdTreeItem([prim_path.name, prim.GetSpecifier().name], parent_item)
            parent_nodes[prim_path.pathString] = new_item
            parent_item.append_child(new_item)
            # TODO, todaj ten stack ktory tworzy prim!!!
            # print()
            # print(prim)
            # Prim stack zwraca w kolejnosci od namocniejszej to nahjslabszej opini pobranej z prima?
            # jakos rpzekminic jak zebrac czym ta opinia jest tzn czy lokal czy variantset etc?
            # moze dodac tu jakis sposob na zmiane ich kolejnosci zeby cos zasymulowac? Wtedy zabarwic 
            # calosc na inny kolor?
            # prim_path = prim.GetPath()
            # for sub_prim_path in prim_path.split("/")
            # prim_stack = prim.GetPrimStack()
            

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ArcLightMainWindow()
    window.show()
    sys.exit(app.exec())