from pxr import Usd
from PySide6 import QtWidgets
from PySide6.QtGui import QCloseEvent
from pxr.Usdviewq.stageView import StageView
from core.usd_engine import open_layer
from widgets.hydra_viewport_widget.timeline import TimelineWidget


class UsdViewportWidget(QtWidgets.QWidget):
    def __init__(self, stage: Usd.Stage):
        super().__init__()
        
        # create stage view
        self.model = StageView.DefaultDataModel()
        self.view = StageView(dataModel=self.model)
        self.setMinimumWidth(600)

        # create timeline
        self.timelineWidget = TimelineWidget()
        self.timelineWidget.timeline.frameChanged.connect(self._frame_changed)
        if stage:
            self.set_stage(stage)
        self.timelineWidget.slider.valueChanged.connect(self._frame_changed)

        widget_layout = QtWidgets.QVBoxLayout()
        widget_layout.addWidget(self.view)
        widget_layout.addWidget(self.timelineWidget)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(widget_layout)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.view.closeRenderer()
        return super().closeEvent(event)
    
    def set_stage(self, stage: Usd.Stage):
        self.view.closeRenderer()
        self.model.stage = stage
        self.model.currentFrame = Usd.TimeCode.EarliestTime()
        self.update_view()
    
    def layer_loaded(self, layer_path):
        layer = open_layer(layer_path)
        self._set_layer_timeline(layer)

    def update_view(self):
        self.view.update()
        if self.isVisible():
            self.view.updateView(resetCam=True, forceComputeBBox=True)

    def _set_layer_timeline(self, layer):
        start = layer.GetStartTimeCode()
        end = layer.GetEndTimeCode()
        fps = layer.GetFramesPerSecond()
        total_frames = end - start + 1
        duration = int((total_frames / fps) * 1000)
        self.timelineWidget.set_timeline(start, end, duration, fps)
    
    def _frame_changed(self, frame):
        self.model.currentFrame = Usd.TimeCode(frame)
        self.view.updateView()
