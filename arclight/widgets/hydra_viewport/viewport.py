import os
import sys


from PySide6 import QtWidgets, QtCore
from PySide6.QtGui import QCloseEvent, QShowEvent
from pxr import Usd, UsdUtils
from pxr.Usdviewq.stageView import StageView


class UsdViewportWidget(QtWidgets.QWidget):
    def __init__(self, stage):
        super().__init__()
        self.model = StageView.DefaultDataModel()
        self.view = StageView(dataModel=self.model)
        if stage:
            self.set_stage(stage)

        widget_layout = QtWidgets.QHBoxLayout()
        widget_layout.addWidget(self.view)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(widget_layout)

    def set_stage(self, stage):
        self.model.stage = stage
        self.model.currentFrame = Usd.TimeCode.EarliestTime()
        if self.isVisible():
            self.refresh_view()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.view.closeRenderer()
        return super().closeEvent(event)
    
    def refresh_view(self):
        self.view.updateView(resetCam=True, forceComputeBBox=True)
