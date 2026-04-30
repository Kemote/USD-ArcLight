import os
import sys

from PySide6 import QtWidgets, QtCore, QtGui
from widgets.usd_tree_widget.usd_tree_delegate import UsdTreeDelegate
from widgets.usd_tree_widget.usd_tree_model import UsdTreeModel
from widgets.usd_tree_widget.usd_tree_view import UsdTreeView
from widgets.usd_tree_widget.usd_tree_item import UsdTreeItem


class ArcLightMainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("ArcLight - USD Composition Explorer")
        self.resize(1200, 720)

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        # create menu bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        open_action = QtGui.QAction("Open USD file", self)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        # create USD tree view
        self.usd_tree_model = UsdTreeModel(["Name", "Type"])
        self.usd_tree_delegate = UsdTreeDelegate()
        self.usd_tree_view = UsdTreeView()
        self.usd_tree_view.setModel(self.usd_tree_model)
        self.usd_tree_view.setItemDelegate(self.usd_tree_delegate)


        # Adding sample items
        root = self.usd_tree_model.root_item
        folder1 = UsdTreeItem(["Documents", "Folder"], root)
        root.append_child(folder1)
        folder1.append_child(UsdTreeItem(["Resume.pdf", "File"], folder1))


        # create main layout
        self.main_layout = QtWidgets.QGridLayout()
        self.central_widget.setLayout(self.main_layout )
        self.main_layout.addWidget(self.usd_tree_view, 0, 0)

        # connecting signals
        self._connect_signals()

    def _connect_signals(self):
        return
    
    def _open_file(self):
        open_dialog = QtWidgets.QFileDialog(self)
        open_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        open_dialog.setWindowTitle("Open USD file...")
        file_path = open_dialog.getOpenFileName(filter="(*.usd *.usda *.usdc)")[0]
        if os.path.exists(file_path):
            # tutaj logika wczytania usd
            print(file_path)
        # open_dialog.show()
        # print(open_dialog.fileSelected.emit())

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ArcLightMainWindow()
    window.show()
    sys.exit(app.exec())