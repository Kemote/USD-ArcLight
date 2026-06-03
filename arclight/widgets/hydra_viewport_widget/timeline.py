from PySide6 import QtWidgets, QtCore


class TimelineWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.timeline = QtCore.QTimeLine()
        self.timeline.frameChanged.connect(self._frame_changed)
        
        self._first_frame = QtWidgets.QLineEdit()
        self._first_frame.setText("1")
        self._first_frame.setFixedWidth(50)
        self._first_frame.textChanged.connect(self._first_frame_changed)

        self._play_btn = QtWidgets.QPushButton(">")
        self._play_btn.clicked.connect(self._play)
        self._play_btn.setFixedWidth(30)

        self._pause_btn = QtWidgets.QPushButton("||")
        self._pause_btn.clicked.connect(self._pause)
        self._pause_btn.setFixedWidth(30)

        self._stop_btn = QtWidgets.QPushButton("P")
        self._stop_btn.clicked.connect(self._stop)
        self._stop_btn.setFixedWidth(30)

        self.slider = QtWidgets.QSlider()
        self.slider.setOrientation(QtCore.Qt.Orientation.Horizontal)
        
        self._end_frame = QtWidgets.QLineEdit()
        self._end_frame.setText("1")
        self._end_frame.setFixedWidth(50)
        self._end_frame.textChanged.connect(self._end_frame_changed)

        self._fps_label = QtWidgets.QLabel("FPS:")
        self._fps = QtWidgets.QLineEdit()
        self._fps.setText("24")
        self._fps.setFixedWidth(50)

        widget_layout = QtWidgets.QHBoxLayout()
        widget_layout.addWidget(self._first_frame)
        widget_layout.addWidget(self._play_btn)
        widget_layout.addWidget(self._pause_btn)
        widget_layout.addWidget(self._stop_btn)
        widget_layout.addWidget(self.slider)
        widget_layout.addWidget(self._end_frame)
        widget_layout.addWidget(self._fps_label)
        widget_layout.addWidget(self._fps)

        self.setLayout(widget_layout)

    def set_timeline(self, start, end, duration, fps= None, current_frame=None, force=False):
        if not force:
            if start != int(float(self._first_frame.text())) or end != int(float(self._end_frame.text())):
                reply = QtWidgets.QMessageBox.question(
                    None,
                    "Change Time?",
                    "Time settings from laoded layer differ from current settings, change them?",
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
                )
                if reply == QtWidgets.QMessageBox.StandardButton.No:
                    return
            
        self.timeline.setStartFrame(start)
        self.timeline.setEndFrame(end)
        self.timeline.setDuration(duration)
        if current_frame:
            self.timeline.setCurrentTime(current_frame)
            self.slider.setValue(current_frame)
        else:
            self.timeline.setCurrentTime(start)
        self.slider.setMinimum(start)
        self.slider.setMaximum(end)
        self._first_frame.setText(str(start))
        self._end_frame.setText(str(end))
        if fps:
            self._fps.setText(str(fps))

    def _first_frame_changed(self, frame):
        frame = int(float(frame))
        current_frame = None
        end_frame = self.timeline.endFrame()
        if frame > self.timeline.currentFrame():
            current_frame = frame
        duration = self._get_duration(frame, end_frame)
        self.set_timeline(frame, end_frame, duration, current_frame=current_frame, force=True)

    def _end_frame_changed(self, frame):
        frame = int(float(frame))
        current_frame = None
        start_frame = self.timeline.startFrame()
        if frame < self.timeline.currentFrame():
            current_frame = frame
        duration = self._get_duration(start_frame, frame)
        self.set_timeline(start_frame, frame, duration, current_frame=current_frame, force=True)
    
    def _get_duration(self, start, end):
        fps = float(self._fps.text())
        total_frames = end - start + 1
        duration = int((total_frames / fps) * 1000)
        return duration
    
    def _play(self):
        if self.timeline.state() == QtCore.QTimeLine.State.Running:
            self._stop()
        
        if self.timeline.state() == QtCore.QTimeLine.State.Paused:
            self.timeline.resume()
        else:
            self.timeline.start()
        
    def _pause(self):
        self.timeline.setPaused(True)

    def _stop(self):
        self.timeline.stop()
        self.timeline.setCurrentTime(0)

    def _frame_changed(self, frame):
        self.slider.setValue(frame)
        self._frame.setText(str(frame))