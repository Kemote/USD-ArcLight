from PySide6 import QtWidgets, QtCore
from PySide6.QtGui import QCloseEvent
from pxr import Usd
from pxr.Usdviewq.stageView import StageView


class UsdViewportWidget(QtWidgets.QWidget):
    def __init__(self, stage: Usd.Stage):
        super().__init__()
        
        # create stage view
        self.model = StageView.DefaultDataModel()
        self.view = StageView(dataModel=self.model)

        # create timeline
        self.timeline = TimelineWidget()

        if stage:
            self.set_stage(stage)

        widget_layout = QtWidgets.QVBoxLayout()
        widget_layout.addWidget(self.view)
        widget_layout.addWidget(self.timeline)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(widget_layout)

    def set_stage(self, stage: Usd.Stage):
        self.view.closeRenderer()
        self.model.stage = stage
        self.model.currentFrame = Usd.TimeCode.EarliestTime()
        
        # set timeline
        start = stage.GetStartTimeCode()
        end = stage.GetEndTimeCode()
        self.timeline.set_timeline(start, end)

        # update view
        self.view.update()
        if self.isVisible():
            self.refresh_view()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.view.closeRenderer()
        return super().closeEvent(event)
    
    def refresh_view(self):
        self.view.updateView(resetCam=True, forceComputeBBox=True)


class TimelineWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._timeline = QtCore.QTimeLine()
        self._play_btn = QtWidgets.QPushButton()
        self._pause_btn = QtWidgets.QPushButton()
        self._stop_btn = QtWidgets.QPushButton()
        self._slider = QtWidgets.QSlider()
        self._slider.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self._frame = QtWidgets.QLabel()

        widget_layout = QtWidgets.QHBoxLayout()
        widget_layout.addWidget(self._play_btn)
        widget_layout.addWidget(self._pause_btn)
        widget_layout.addWidget(self._stop_btn)
        widget_layout.addWidget(self._slider)
        widget_layout.addWidget(self._frame)
        self.setLayout(widget_layout)

    def set_timeline(self, start, end):
        self._timeline.setStartFrame = start
        self._timeline.setEndFrame = end
        self._slider.setMinimum(start)
        self._slider.setMaximum(end)