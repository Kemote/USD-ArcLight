"""
HydraViewport — PySide6 USD stage viewer
=========================================

Provides a self-contained widget that renders an OpenUSD stage using raw
OpenGL 3.3 (Core Profile) without requiring UsdImagingGL.  It is intentionally
simple: geometry-only, flat-shaded Phong, no materials.  The goal is a
lightweight companion to the USD composition explorer, not a production renderer.

Public surface
--------------
    HydraViewport(parent)      Main widget to embed in your layout.
    .set_stage(Usd.Stage)      Point the viewport at a stage (or None to clear).

Everything else is private implementation detail.

Architecture
------------

    HydraViewport  (QWidget)
    ├── toolbar      camera combo | renderer combo | pause button
    ├── _UsdGLViewport  (QOpenGLWidget)   ← 3-D rendering area
    └── _TimelineBar (QWidget)            ← playback controls

Rendering pipeline
------------------
    set_stage()
      └─ _rebuild_geometry()          traverse stage, triangulate each Mesh prim
           └─ _upload_mesh()          upload pos+normal VBOs, record in VAO
                └─ _fill_vbo()        pack floats → bytes → QOpenGLBuffer

    paintGL()  (called by Qt on every repaint)
      ├── _projection_matrix()        perspective from free-cam or stage camera
      ├── _view_matrix()              lookAt from free-cam or stage camera xform
      └── for each _Batch:
            bind VAO → glDrawArrays → release VAO

    set_time(t)                       called by _TimelineBar on scrub/play
      └─ _update_time()               re-triangulate + reupload VBO data in place;
                                      falls back to _rebuild_geometry() if topology
                                      changes (different vertex count).

Coordinate systems
------------------
    USD uses right-handed Y-up, row-vector convention (v' = v · M).
    OpenGL uses right-handed Y-up, column-vector convention (v' = M · v).
    The two are related by matrix transpose.  _gf_to_qt() performs that
    conversion so all Gf.Matrix4d values from USD can be passed directly to
    QOpenGLShaderProgram.setUniformValue().

Stage change notifications
--------------------------
    Tf.Notice.Register(Usd.Notice.ObjectsChanged, …) fires whenever the stage
    is edited.  Because Tf fires on the authoring thread, the callback posts a
    zero-delay QTimer event to ensure the GPU rebuild runs on the main (GL)
    thread.  When paused, the listener is revoked; it is re-registered on resume.

Known limitations
-----------------
  • No material / texture support — meshes render as a single clay colour.
  • Only UsdGeom.Mesh prims are rendered (no curves, points, volumes, lights).
  • Normals are always computed as flat (per-triangle).  Authored normals
    from the stage are ignored.
  • _update_time() is O(n_triangles) per frame — fine for small scenes, slow
    for large ones.  A production path would stream deltas or use UsdImagingGL.
  • Render delegate combo is decorative: only "GL (Simple)" is implemented.
    Extend _RENDER_DELEGATES and _on_delegate_changed() to add backends.
"""

import math
import struct

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMatrix4x4, QVector3D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from pxr import Gf, Sdf, Tf, Usd, UsdGeom


# ---------------------------------------------------------------------------
# GLSL shaders  (OpenGL 3.3 Core Profile)
# ---------------------------------------------------------------------------

_VERT_SRC = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
uniform mat4 uMVP;
uniform mat4 uModel;
out vec3 vNormal;
out vec3 vFragPos;
void main() {
    vFragPos    = vec3(uModel * vec4(aPos, 1.0));
    vNormal     = normalize(mat3(transpose(inverse(uModel))) * aNormal);
    gl_Position = uMVP * vec4(aPos, 1.0);
}
"""

_FRAG_SRC = """
#version 330 core
in  vec3 vNormal;
in  vec3 vFragPos;
out vec4 fragColor;
uniform vec3 uLightDir;
uniform vec3 uColor;
void main() {
    vec3  n    = normalize(vNormal);
    vec3  l    = normalize(uLightDir);
    float diff = max(dot(n, l), 0.0);
    float back = max(dot(-n, l), 0.0) * 0.08;   // soft backlight
    vec3  col  = (0.22 + diff * 0.78 + back) * uColor;
    fragColor  = vec4(col, 1.0);
}
"""


# ---------------------------------------------------------------------------
# Helper — USD→Qt matrix conversion
# ---------------------------------------------------------------------------

def _gf_to_qt(m: Gf.Matrix4d) -> QMatrix4x4:
    """Transpose a USD row-vector matrix into a Qt column-vector matrix.

    USD Gf.Matrix4d stores transforms for row-vector multiplication (v' = v·M).
    QMatrix4x4 / OpenGL expect column-vector multiplication (v' = M·v).
    The two are transposes of each other.  QMatrix4x4's constructor takes
    values row-by-row, so filling it with m[col][row] produces the transpose.
    """
    return QMatrix4x4(
        m[0][0], m[1][0], m[2][0], m[3][0],
        m[0][1], m[1][1], m[2][1], m[3][1],
        m[0][2], m[1][2], m[2][2], m[3][2],
        m[0][3], m[1][3], m[2][3], m[3][3],
    )


# ---------------------------------------------------------------------------
# Free-look orbit camera
# ---------------------------------------------------------------------------

class _FreeCam:
    """Spherical-coordinate orbit camera stored as CPU state.

    The camera revolves around a *pivot* point at a given *distance*.
    *azimuth* rotates around the world Y axis; *elevation* tilts up/down.
    All angles are in degrees.
    """

    def __init__(self) -> None:
        self.distance  = 10.0
        self.azimuth   = 45.0
        self.elevation = 30.0
        self.pivot     = QVector3D(0.0, 0.0, 0.0)
        self.fov_v     = 60.0
        self.near      = 0.01
        self.far       = 100_000.0

    def view_matrix(self) -> QMatrix4x4:
        az  = math.radians(self.azimuth)
        el  = math.radians(self.elevation)
        x   = self.distance * math.cos(el) * math.sin(az)
        y   = self.distance * math.sin(el)
        z   = self.distance * math.cos(el) * math.cos(az)
        eye = QVector3D(x, y, z) + self.pivot
        m   = QMatrix4x4()
        m.lookAt(eye, self.pivot, QVector3D(0.0, 1.0, 0.0))
        return m


# ---------------------------------------------------------------------------
# GPU mesh batch
# ---------------------------------------------------------------------------

class _Batch:
    """GPU-side data for one UsdGeom.Mesh prim at a particular time code.

    Owns a VAO (records vertex layout), two VBOs (positions + normals),
    the triangle vertex count, and the model matrix from the USD xform.

    The VAO records which VBOs are bound to which attribute locations so
    paintGL only needs to bind the VAO — no per-frame attribute setup.
    """

    def __init__(
        self,
        vao:     QOpenGLVertexArrayObject,
        vbo_pos: QOpenGLBuffer,
        vbo_nrm: QOpenGLBuffer,
        count:   int,
        model:   QMatrix4x4,
    ) -> None:
        self.vao     = vao
        self.vbo_pos = vbo_pos
        self.vbo_nrm = vbo_nrm
        self.count   = count   # number of vertices  (= 3 × triangle count)
        self.model   = model   # world transform as QMatrix4x4

    def destroy(self) -> None:
        self.vao.destroy()
        self.vbo_pos.destroy()
        self.vbo_nrm.destroy()


# ---------------------------------------------------------------------------
# OpenGL viewport
# ---------------------------------------------------------------------------

class _UsdGLViewport(QOpenGLWidget):
    """QOpenGLWidget that renders the active USD stage.

    Responsibilities
    ----------------
    • initializeGL  — compile shaders, enable depth test.
    • paintGL       — bind shader, iterate batches, draw.
    • _rebuild_geometry — traverse stage, triangulate meshes, upload to GPU.
    • _update_time  — fast path: repack VBO data at a new time code without
                      destroying VAOs; falls back to full rebuild on topology
                      change (vertex count mismatch).
    • Mouse / wheel — orbit (LMB), pan (MMB), dolly (RMB / wheel).
    • Tf.Notice     — listens for stage edits; routes rebuild to main thread
                      via a zero-interval QTimer.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 300)

        self._stage: Usd.Stage | None           = None
        self._batches: list[_Batch]             = []
        self._shader: QOpenGLShaderProgram | None = None
        self._gl                                = None
        self._gl_ready                          = False

        self._current_time: float               = 0.0

        self._cam                               = _FreeCam()
        self._stage_cam_path: Sdf.Path | None   = None

        self._last_mouse                        = QtCore.QPoint()
        self._active_button: Qt.MouseButton | None = None

        self._listener  = None
        self._paused    = False
        self._rebuild_timer = QtCore.QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(0)
        self._rebuild_timer.timeout.connect(self._rebuild_geometry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_stage(self, stage: Usd.Stage | None) -> None:
        self._revoke_listener()
        self._stage       = stage
        self._current_time = 0.0
        self._rebuild_geometry()
        if not self._paused:
            self._register_listener()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused:
            self._revoke_listener()
        else:
            self._register_listener()
            self.update()

    def set_stage_camera(self, prim_path: str) -> None:
        self._stage_cam_path = Sdf.Path(prim_path) if prim_path else None
        self.update()

    def set_time(self, time_code: float) -> None:
        """Seek to *time_code* and redraw.

        Uses an in-place VBO update (fast) when topology is unchanged;
        falls back to a full _rebuild_geometry() otherwise.
        """
        self._current_time = time_code
        if not self._gl_ready or not self._stage:
            self.update()
            return
        if not self._batches:
            self._rebuild_geometry()
            return
        self._update_time()

    # ------------------------------------------------------------------
    # Stage change listener
    # ------------------------------------------------------------------

    def _register_listener(self) -> None:
        if self._stage and self._listener is None:
            self._listener = Tf.Notice.Register(
                Usd.Notice.ObjectsChanged,
                self._on_stage_changed,
                self._stage,
            )

    def _revoke_listener(self) -> None:
        if self._listener is not None:
            self._listener.Revoke()
            self._listener = None

    def _on_stage_changed(self, notice, stage) -> None:
        # Tf fires on the authoring thread — defer to main thread via timer.
        if not self._paused:
            self._rebuild_timer.start()

    # ------------------------------------------------------------------
    # OpenGL lifecycle
    # ------------------------------------------------------------------

    def initializeGL(self) -> None:
        self._gl = self.context().functions()
        self._gl.glEnable(0x0B44)           # GL_DEPTH_TEST
        self._gl.glClearColor(0.18, 0.18, 0.18, 1.0)

        self._shader = QOpenGLShaderProgram(self)
        ok  = self._shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex,   _VERT_SRC)
        ok &= self._shader.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, _FRAG_SRC)
        ok &= self._shader.link()
        if not ok:
            print("[HydraViewport] Shader compilation failed:", self._shader.log())

        self._gl_ready = True
        if self._stage:
            self._rebuild_geometry()

    def resizeGL(self, w: int, h: int) -> None:
        if self._gl:
            self._gl.glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        self._gl.glClear(0x4100)    # GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT

        if not self._shader or not self._batches:
            return

        proj = self._projection_matrix()
        view = self._view_matrix()

        self._shader.bind()
        self._shader.setUniformValue("uLightDir", QVector3D(1.0, 2.0, 1.5))
        self._shader.setUniformValue("uColor",    QVector3D(0.80, 0.76, 0.62))

        for batch in self._batches:
            mvp = proj * view * batch.model
            self._shader.setUniformValue("uMVP",   mvp)
            self._shader.setUniformValue("uModel", batch.model)
            batch.vao.bind()
            self._gl.glDrawArrays(0x0004, 0, batch.count)  # GL_TRIANGLES
            batch.vao.release()

        self._shader.release()

    # ------------------------------------------------------------------
    # Geometry — full rebuild
    # ------------------------------------------------------------------

    def _rebuild_geometry(self) -> None:
        """Destroy all GPU batches and re-upload from scratch at _current_time."""
        if not self._gl_ready:
            return

        self.makeCurrent()
        for b in self._batches:
            b.destroy()
        self._batches.clear()

        if self._stage:
            t = Usd.TimeCode(self._current_time)
            for prim in self._stage.TraverseAll():
                if not prim.IsActive():
                    continue
                if prim.IsA(UsdGeom.Mesh):
                    batch = self._upload_mesh(UsdGeom.Mesh(prim), t)
                    if batch:
                        self._batches.append(batch)

        self.doneCurrent()
        self.update()

    def _upload_mesh(self, mesh: UsdGeom.Mesh, t: Usd.TimeCode) -> "_Batch | None":
        """Triangulate *mesh* at time *t* and upload to a new VAO+VBOs."""
        if self._shader is None:
            return None

        pts      = mesh.GetPointsAttr().Get(t)
        face_idx = mesh.GetFaceVertexIndicesAttr().Get(t)
        face_cnt = mesh.GetFaceVertexCountsAttr().Get(t)
        if pts is None or face_idx is None or face_cnt is None:
            return None

        pos_data, nrm_data, vertex_count = _triangulate(pts, face_idx, face_cnt)
        if vertex_count == 0:
            return None

        xf    = UsdGeom.Xformable(mesh.GetPrim()).ComputeLocalToWorldTransform(t)
        model = _gf_to_qt(xf)

        # Core Profile requires a VAO.  We use Qt's C++ setAttributeBuffer()
        # to record attribute layout into it — this avoids the broken Python
        # binding of QOpenGLFunctions.glVertexAttribPointer().
        vao = QOpenGLVertexArrayObject()
        vao.create()
        vao.bind()
        self._shader.bind()

        vbo_pos = self._fill_vbo(pos_data)
        self._shader.setAttributeBuffer(0, 0x1406, 0, 3)   # GL_FLOAT, position
        self._shader.enableAttributeArray(0)
        vbo_pos.release()

        vbo_nrm = self._fill_vbo(nrm_data)
        self._shader.setAttributeBuffer(1, 0x1406, 0, 3)   # GL_FLOAT, normal
        self._shader.enableAttributeArray(1)
        vbo_nrm.release()

        self._shader.release()
        vao.release()

        return _Batch(vao, vbo_pos, vbo_nrm, vertex_count, model)

    @staticmethod
    def _fill_vbo(data: list[float]) -> QOpenGLBuffer:
        """Create, bind, and fill a VBO.  Caller must release after attribute setup."""
        raw = struct.pack(f"{len(data)}f", *data)
        vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        vbo.create()
        vbo.bind()
        vbo.allocate(raw, len(raw))
        return vbo

    # ------------------------------------------------------------------
    # Geometry — fast time update
    # ------------------------------------------------------------------

    def _update_time(self) -> None:
        """Re-upload VBO data at _current_time without rebuilding VAOs.

        Iterates existing batches in the same order as _rebuild_geometry().
        If a mesh's vertex count changes (topology edit), falls back to a
        full rebuild so correctness is maintained.
        """
        self.makeCurrent()
        t             = Usd.TimeCode(self._current_time)
        batch_iter    = iter(self._batches)
        needs_rebuild = False

        for prim in self._stage.TraverseAll():        # type: ignore[union-attr]
            if not prim.IsActive() or not prim.IsA(UsdGeom.Mesh):
                continue
            try:
                batch = next(batch_iter)
            except StopIteration:
                needs_rebuild = True
                break

            mesh     = UsdGeom.Mesh(prim)
            pts      = mesh.GetPointsAttr().Get(t)
            face_idx = mesh.GetFaceVertexIndicesAttr().Get(t)
            face_cnt = mesh.GetFaceVertexCountsAttr().Get(t)

            if pts is not None and face_idx is not None and face_cnt is not None:
                pos_data, nrm_data, vc = _triangulate(pts, face_idx, face_cnt)
                if vc != batch.count:
                    needs_rebuild = True
                    break

                raw_pos = struct.pack(f"{len(pos_data)}f", *pos_data)
                batch.vbo_pos.bind()
                batch.vbo_pos.allocate(raw_pos, len(raw_pos))
                batch.vbo_pos.release()

                raw_nrm = struct.pack(f"{len(nrm_data)}f", *nrm_data)
                batch.vbo_nrm.bind()
                batch.vbo_nrm.allocate(raw_nrm, len(raw_nrm))
                batch.vbo_nrm.release()

            xf          = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(t)
            batch.model = _gf_to_qt(xf)

        self.doneCurrent()

        if needs_rebuild:
            self._rebuild_geometry()
        else:
            self.update()

    # ------------------------------------------------------------------
    # Camera & projection
    # ------------------------------------------------------------------

    def _projection_matrix(self) -> QMatrix4x4:
        w, h   = self.width(), max(self.height(), 1)
        aspect = w / h
        t      = Usd.TimeCode(self._current_time)

        if self._stage_cam_path and self._stage:
            prim = self._stage.GetPrimAtPath(self._stage_cam_path)
            if prim.IsValid() and prim.IsA(UsdGeom.Camera):
                gf_cam = UsdGeom.Camera(prim).GetCamera(t)
                near   = gf_cam.clippingRange.min
                far    = gf_cam.clippingRange.max
                fov_h  = gf_cam.GetFieldOfView(Gf.Camera.FOVHorizontal)
                fov_v  = math.degrees(
                    2.0 * math.atan(math.tan(math.radians(fov_h) / 2.0) / aspect)
                )
                m = QMatrix4x4()
                m.perspective(fov_v, aspect, near, far)
                return m

        m = QMatrix4x4()
        m.perspective(self._cam.fov_v, aspect, self._cam.near, self._cam.far)
        return m

    def _view_matrix(self) -> QMatrix4x4:
        t = Usd.TimeCode(self._current_time)

        if self._stage_cam_path and self._stage:
            prim = self._stage.GetPrimAtPath(self._stage_cam_path)
            if prim.IsValid() and prim.IsA(UsdGeom.Camera):
                xf       = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(t)
                view, _  = _gf_to_qt(xf).inverted()
                return view

        return self._cam.view_matrix()

    # ------------------------------------------------------------------
    # Mouse / keyboard navigation  (free camera only)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._stage_cam_path:
            return
        self._last_mouse    = event.position().toPoint()
        self._active_button = event.button()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._stage_cam_path or self._active_button is None:
            return

        pos = event.position().toPoint()
        dx  = pos.x() - self._last_mouse.x()
        dy  = pos.y() - self._last_mouse.y()
        self._last_mouse = pos

        btn = self._active_button
        if btn == Qt.MouseButton.LeftButton:
            # Orbit
            self._cam.azimuth   -= dx * 0.4
            self._cam.elevation  = max(-89.0, min(89.0, self._cam.elevation + dy * 0.4))

        elif btn == Qt.MouseButton.MiddleButton:
            # Pan in camera-right and world-up directions
            scale = self._cam.distance * 0.001
            az    = math.radians(self._cam.azimuth)
            right = QVector3D(math.cos(az), 0.0, -math.sin(az))
            self._cam.pivot -= right                 * (dx * scale)
            self._cam.pivot += QVector3D(0, 1, 0)   * (dy * scale)

        elif btn == Qt.MouseButton.RightButton:
            # Dolly
            self._cam.distance = max(0.001, self._cam.distance * (1.0 + dy * 0.005))

        self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._active_button = None

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self._stage_cam_path:
            return
        factor = 0.90 if event.angleDelta().y() > 0 else 1.11
        self._cam.distance = max(0.001, self._cam.distance * factor)
        self.update()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_F, Qt.Key.Key_Home):
            self._frame_scene()

    def _frame_scene(self) -> None:
        """Reset free camera to default orbit around world origin."""
        self._cam.pivot     = QVector3D(0.0, 0.0, 0.0)
        self._cam.distance  = 10.0
        self._cam.azimuth   = 45.0
        self._cam.elevation = 30.0
        self.update()


# ---------------------------------------------------------------------------
# Mesh triangulation (CPU, no GL dependency)
# ---------------------------------------------------------------------------

def _triangulate(
    points,
    face_indices,
    face_counts,
) -> "tuple[list[float], list[float], int]":
    """Fan-triangulate a USD polygon mesh and compute flat per-triangle normals.

    Returns
    -------
    pos_data : list[float]   Flat XYZ values — 3 floats × vertex_count entries.
    nrm_data : list[float]   Flat XYZ normal values — same layout as pos_data.
    vertex_count : int       Total number of vertices (= 3 × number of triangles).

    The output is non-indexed (each triangle has 3 independent vertices) so
    it can be fed directly to glDrawArrays without an element buffer.
    """
    pos_data: list[float] = []
    nrm_data: list[float] = []
    fi = 0

    for count in face_counts:
        fan = [face_indices[fi + i] for i in range(count)]
        fi += count
        # Fan triangulation: triangle (0, i, i+1) for i in 1..count-2
        for i in range(1, count - 1):
            p0 = Gf.Vec3f(points[fan[0]])
            p1 = Gf.Vec3f(points[fan[i]])
            p2 = Gf.Vec3f(points[fan[i + 1]])
            n  = Gf.Cross(p1 - p0, p2 - p0)
            ln = n.GetLength()
            n  = n / ln if ln > 1e-8 else Gf.Vec3f(0.0, 1.0, 0.0)
            for p in (p0, p1, p2):
                pos_data.extend([p[0], p[1], p[2]])
                nrm_data.extend([n[0], n[1], n[2]])

    return pos_data, nrm_data, len(pos_data) // 3


# ---------------------------------------------------------------------------
# Timeline / playback bar
# ---------------------------------------------------------------------------

class _TimelineBar(QtWidgets.QWidget):
    """Playback controls that emit time_changed(float) on every frame step.

    The bar is disabled when the stage has no authored time-code range.
    On play, a QTimer fires at the stage's native FPS (GetTimeCodesPerSecond).
    Looping is automatic: after the last frame, playback wraps to the first.

    Scrubbing (dragging the slider or editing the spinbox) stops playback and
    immediately emits the new time so the viewport can respond.
    """

    time_changed = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._start = 1.0
        self._end   = 1.0
        self._fps   = 24.0

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        self._start_btn = QtWidgets.QPushButton("|◀")
        self._start_btn.setFixedWidth(28)
        self._start_btn.setToolTip("Go to first frame")
        layout.addWidget(self._start_btn)

        self._play_btn = QtWidgets.QPushButton("▶")
        self._play_btn.setCheckable(True)
        self._play_btn.setFixedWidth(32)
        self._play_btn.setToolTip("Play / Pause animation")
        layout.addWidget(self._play_btn)

        self._frame_spin = QtWidgets.QDoubleSpinBox()
        self._frame_spin.setDecimals(0)
        self._frame_spin.setFixedWidth(64)
        self._frame_spin.setToolTip("Current time code")
        layout.addWidget(self._frame_spin)

        self._start_label = QtWidgets.QLabel("1")
        self._start_label.setFixedWidth(36)
        self._start_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._start_label)

        self._slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        layout.addWidget(self._slider, stretch=1)

        self._end_label = QtWidgets.QLabel("1")
        self._end_label.setFixedWidth(36)
        layout.addWidget(self._end_label)

        self._fps_label = QtWidgets.QLabel("24 fps")
        self._fps_label.setFixedWidth(52)
        layout.addWidget(self._fps_label)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

        self._start_btn.clicked.connect(self._go_to_start)
        self._play_btn.toggled.connect(self._on_play_toggled)
        self._frame_spin.valueChanged.connect(self._on_spin_changed)
        self._slider.valueChanged.connect(self._on_slider_changed)

        self._set_playback_available(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_stage(self, stage: Usd.Stage | None) -> None:
        """Configure the timeline from the stage's metadata, or disable it."""
        self._timer.stop()
        self._play_btn.setChecked(False)

        if stage and stage.HasAuthoredTimeCodeRange():
            start = stage.GetStartTimeCode()
            end   = stage.GetEndTimeCode()
            fps   = stage.GetTimeCodesPerSecond()
            if end <= start:            # degenerate range — treat as static
                self._set_playback_available(False)
                return

            self._start = start
            self._end   = end
            self._fps   = fps

            self._slider.setRange(int(start), int(end))
            self._frame_spin.setRange(start, end)
            self._frame_spin.setSingleStep(1.0)
            self._start_label.setText(str(int(start)))
            self._end_label.setText(str(int(end)))
            self._fps_label.setText(f"{fps:.0f} fps")
            self._timer.setInterval(max(1, int(1000.0 / fps)))
            self._set_frame(start, emit=True)
            self._set_playback_available(True)
        else:
            self._set_playback_available(False)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_playback_available(self, available: bool) -> None:
        for w in (self._play_btn, self._start_btn,
                  self._slider, self._frame_spin, self._fps_label):
            w.setEnabled(available)
        if not available:
            self._start_label.setText("—")
            self._end_label.setText("—")
            self._fps_label.setText("— fps")

    def _on_play_toggled(self, playing: bool) -> None:
        self._play_btn.setText("⏸" if playing else "▶")
        if playing:
            self._timer.start()
        else:
            self._timer.stop()

    def _go_to_start(self) -> None:
        self._play_btn.setChecked(False)
        self._set_frame(self._start, emit=True)

    def _advance_frame(self) -> None:
        next_f = self._frame_spin.value() + 1.0
        if next_f > self._end:
            next_f = self._start
        self._set_frame(next_f, emit=True)

    def _on_spin_changed(self, value: float) -> None:
        # Spinbox edited by user — stop playback, sync slider, emit.
        self._play_btn.setChecked(False)
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)
        self.time_changed.emit(value)

    def _on_slider_changed(self, value: int) -> None:
        # Slider dragged by user — stop playback, sync spinbox, emit.
        self._play_btn.setChecked(False)
        self._frame_spin.blockSignals(True)
        self._frame_spin.setValue(float(value))
        self._frame_spin.blockSignals(False)
        self.time_changed.emit(float(value))

    def _set_frame(self, frame: float, *, emit: bool = False) -> None:
        """Silently update both controls to *frame*; optionally emit time_changed."""
        self._slider.blockSignals(True)
        self._frame_spin.blockSignals(True)
        self._slider.setValue(int(frame))
        self._frame_spin.setValue(frame)
        self._slider.blockSignals(False)
        self._frame_spin.blockSignals(False)
        if emit:
            self.time_changed.emit(frame)


# ---------------------------------------------------------------------------
# Public container widget
# ---------------------------------------------------------------------------

_RENDER_DELEGATES = ["GL (Simple)"]    # extend when UsdImagingGL is available


class HydraViewport(QtWidgets.QWidget):
    """Self-contained USD viewport widget.

    Layout
    ------
    ::

        ┌─ toolbar ────────────────────────────────────────────────────────┐
        │  Camera: [combo]   Renderer: [combo]   [Pause]                   │
        ├─ 3-D view ───────────────────────────────────────────────────────┤
        │                                                                   │
        │            OpenGL render of the USD stage                        │
        │            (mouse: LMB=orbit  MMB=pan  RMB/wheel=dolly)         │
        │            (keyboard: F / Home = frame scene)                    │
        │                                                                   │
        ├─ timeline ───────────────────────────────────────────────────────┤
        │  |◀  ▶   [frame]   1 ──────────────────── 100   24 fps          │
        └──────────────────────────────────────────────────────────────────┘

    Usage
    -----
    ::

        vp = HydraViewport()
        vp.set_stage(my_usd_stage)

    Call ``set_stage(None)`` to clear.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stage: Usd.Stage | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── toolbar ──────────────────────────────────────────────────────
        toolbar = QtWidgets.QFrame()
        toolbar.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        tl = QtWidgets.QHBoxLayout(toolbar)
        tl.setContentsMargins(6, 4, 6, 4)
        tl.setSpacing(8)

        tl.addWidget(QtWidgets.QLabel("Camera:"))
        self._cam_combo = QtWidgets.QComboBox()
        self._cam_combo.setMinimumWidth(150)
        self._cam_combo.setToolTip(
            "Free Camera — orbit/pan/dolly with the mouse.\n"
            "Stage camera — locked to the selected UsdGeom.Camera prim."
        )
        tl.addWidget(self._cam_combo)

        tl.addSpacing(16)
        tl.addWidget(QtWidgets.QLabel("Renderer:"))
        self._delegate_combo = QtWidgets.QComboBox()
        for d in _RENDER_DELEGATES:
            self._delegate_combo.addItem(d)
        self._delegate_combo.setToolTip("Render backend (delegate).")
        tl.addWidget(self._delegate_combo)

        tl.addSpacing(16)
        self._pause_btn = QtWidgets.QPushButton("Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.setMinimumWidth(72)
        self._pause_btn.setToolTip(
            "Pause  — stop reacting to external stage edits.\n"
            "Resume — re-subscribe and redraw immediately."
        )
        tl.addWidget(self._pause_btn)
        tl.addStretch()

        root.addWidget(toolbar)

        # ── GL viewport ───────────────────────────────────────────────────
        self._gl_view = _UsdGLViewport(self)
        root.addWidget(self._gl_view, stretch=1)

        # ── timeline ──────────────────────────────────────────────────────
        self._timeline = _TimelineBar(self)
        root.addWidget(self._timeline)

        # ── signals ───────────────────────────────────────────────────────
        self._cam_combo.currentIndexChanged.connect(self._on_camera_changed)
        self._pause_btn.toggled.connect(self._on_pause_toggled)
        self._timeline.time_changed.connect(self._gl_view.set_time)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_stage(self, stage: Usd.Stage | None) -> None:
        """Point the viewport at *stage* (pass None to clear)."""
        self._stage = stage
        self._populate_cameras()
        self._timeline.set_stage(stage)
        self._gl_view.set_stage(stage)

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _populate_cameras(self) -> None:
        self._cam_combo.blockSignals(True)
        self._cam_combo.clear()
        self._cam_combo.addItem("Free Camera", userData="")
        if self._stage:
            for prim in self._stage.TraverseAll():
                if prim.IsA(UsdGeom.Camera):
                    path = prim.GetPrimPath().pathString
                    self._cam_combo.addItem(prim.GetName(), userData=path)
        self._cam_combo.blockSignals(False)
        self._cam_combo.setCurrentIndex(0)
        self._gl_view.set_stage_camera("")

    def _on_camera_changed(self, index: int) -> None:
        path = self._cam_combo.itemData(index) or ""
        self._gl_view.set_stage_camera(path)

    def _on_pause_toggled(self, paused: bool) -> None:
        self._pause_btn.setText("Resume" if paused else "Pause")
        self._gl_view.set_paused(paused)
