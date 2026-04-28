from PySide6.QtWidgets import QTreeView


class UsdTreeView(QTreeView):
    def __init__(self):
        super().__init__()
        self.setAnimated = True
        self.setIndentation(20)
        self.setHeaderHidden(False)