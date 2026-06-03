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
        self.timelineWidget = TimelineWidget()
        self.timelineWidget.timeline.frameChanged.connect(self._frame_changed)
        if stage:
            self.set_stage(stage)

        widget_layout = QtWidgets.QVBoxLayout()
        widget_layout.addWidget(self.view)
        widget_layout.addWidget(self.timelineWidget)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(widget_layout)

    def set_stage(self, stage: Usd.Stage):
        self.view.closeRenderer()
        self.model.stage = stage
        self.model.currentFrame = Usd.TimeCode.EarliestTime()
        
        # set timeline
        start = stage.GetStartTimeCode()
        end = stage.GetEndTimeCode()
        fps = stage.GetFramesPerSecond()
        total_frames = end - start + 1
        duration = int((total_frames / fps) * 1000)
        self.timelineWidget.set_timeline(start, end, duration)

        # update view
        self.view.update()
        if self.isVisible():
            self.refresh_view()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.view.closeRenderer()
        return super().closeEvent(event)
    
    def refresh_view(self):
        self.view.updateView(resetCam=True, forceComputeBBox=True)

    def _frame_changed(self, frame):
        self.model.currentFrame = Usd.TimeCode(frame)
        self.view.updateView()
        


class TimelineWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.timeline = QtCore.QTimeLine()
        self.timeline.frameChanged.connect(self._frame_changed)
        self._play_btn = QtWidgets.QPushButton(">")
        self._play_btn.clicked.connect(self._play)
        self._pause_btn = QtWidgets.QPushButton("||")
        self._pause_btn.clicked.connect(self._pause)
        self._stop_btn = QtWidgets.QPushButton("P")
        self._stop_btn.clicked.connect(self._stop)
        self._slider = QtWidgets.QSlider()
        self._slider.setOrientation(QtCore.Qt.Orientation.Horizontal)
        self._frame = QtWidgets.QLabel()
        self._frame.setFixedWidth(50)

        widget_layout = QtWidgets.QHBoxLayout()
        widget_layout.addWidget(self._play_btn)
        widget_layout.addWidget(self._pause_btn)
        widget_layout.addWidget(self._stop_btn)
        widget_layout.addWidget(self._slider)
        widget_layout.addWidget(self._frame)
        self.setLayout(widget_layout)

    def set_timeline(self, start, end, duration):
        self.timeline.setStartFrame(start)
        self.timeline.setEndFrame(end)
        self.timeline.setDuration(duration)
        self._slider.setMinimum(start)
        self._slider.setMaximum(end)

    def _play(self):
        if self.timeline.state() == QtCore.QTimeLine.State.Running:
            self._stop()
        self.timeline.start()

    def _pause(self):
        self.timeline.stop()

    def _stop(self):
        self.timeline.stop()
        self.timeline.setCurrentTime(0)

    def _frame_changed(self, frame):
        self._slider.setValue(frame)
        self._frame.setText(str(frame))