from pxr import Usd
from PySide6 import QtWidgets


class UsdEditor(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.top_panel = QtWidgets.QHBoxLayout()
        self.editor = QtWidgets.QTextEdit()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(self.top_panel)
        layout.addWidget(self.editor)
        
        self.setLayout(layout)
        self.setMinimumWidth(500)

    def set_stage_as_text(self, stage: Usd.Stage):
        txt = stage.ExportToString()
        self.editor.setText(txt)
