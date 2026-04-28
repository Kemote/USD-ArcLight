import sys

from PySide6 import QtWidgets, QtCore
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
    

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ArcLightMainWindow()
    window.show()
    sys.exit(app.exec())