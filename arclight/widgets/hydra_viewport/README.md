# hydra_viewport

A self-contained PySide6 widget that renders an OpenUSD stage using raw
OpenGL 3.3 Core Profile — **no `UsdImagingGL` required**.

---

## Quick start

```python
from widgets.hydra_viewport.hydra_viewport import HydraViewport
from pxr import Usd

stage = Usd.Stage.Open("scene.usda")

vp = HydraViewport()          # drop into any QLayout
vp.set_stage(stage)
vp.show()
```

Call `set_stage(None)` to clear the viewport.

> **Before creating `QApplication`** you must set the global surface format
> and force the X11/GLX platform (required on Wayland + NVIDIA):
>
> ```python
> import os, sys
> os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
> from PySide6.QtGui import QSurfaceFormat
> fmt = QSurfaceFormat()
> fmt.setVersion(3, 3)
> fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
> fmt.setDepthBufferSize(24)
> QSurfaceFormat.setDefaultFormat(fmt)
> ```

---

## Architecture

```
HydraViewport  (QWidget)
│
├── toolbar  QFrame
│     ├── Camera combo     — lists all UsdGeom.Camera prims + "Free Camera"
│     ├── Renderer combo   — render delegate selector (GL Simple for now)
│     └── Pause button     — toggles stage-edit reactivity
│
├── _UsdGLViewport  (QOpenGLWidget)
│     │   3-D rendering area
│     ├── _FreeCam         — spherical orbit camera (CPU state only)
│     ├── list[_Batch]     — one entry per UsdGeom.Mesh prim
│     │     ├── QOpenGLVertexArrayObject  — records vertex layout
│     │     ├── QOpenGLBuffer  vbo_pos   — flat XYZ floats
│     │     └── QOpenGLBuffer  vbo_nrm   — flat XYZ normal floats
│     └── QOpenGLShaderProgram  — Phong vertex + fragment shader
│
└── _TimelineBar  (QWidget)
      ├── |◀ button        — go to first frame
      ├── ▶/⏸ button       — play / pause (drives a QTimer at stage FPS)
      ├── QDoubleSpinBox   — current time code (editable)
      ├── QSlider          — timeline scrub bar
      └── fps label        — displays GetTimeCodesPerSecond()
```

---

## Rendering pipeline

### On `set_stage(stage)`

1. `_populate_cameras()` — scan stage for `UsdGeom.Camera` prims.
2. `_timeline.set_stage(stage)` — read `GetStartTimeCode()`, `GetEndTimeCode()`,
   `GetTimeCodesPerSecond()`; enable or disable playback controls.
3. `_UsdGLViewport.set_stage(stage)` → `_rebuild_geometry()`.

### `_rebuild_geometry()` (full upload)

```
for prim in stage.TraverseAll():
    if prim.IsA(UsdGeom.Mesh):
        _upload_mesh(prim, TimeCode(current_time))
            → _triangulate()          fan-triangulate polygons → flat normals
            → QOpenGLVertexArrayObject.create / bind
            → shader.bind
            → _fill_vbo(positions)    pack floats → bytes → QOpenGLBuffer
            → shader.setAttributeBuffer(loc=0, …)
            → shader.enableAttributeArray(0)
            → _fill_vbo(normals)
            → shader.setAttributeBuffer(loc=1, …)
            → shader.enableAttributeArray(1)
            → shader.release / vao.release
```

`setAttributeBuffer` (Qt C++) is used instead of the Python binding of
`glVertexAttribPointer` because the latter has a broken type signature in
the PySide6 version bundled with `usd-core` 0.26.

### `paintGL()` (every frame)

```
for batch in batches:
    set uniforms (MVP, Model, lightDir, color)
    vao.bind()
    glDrawArrays(GL_TRIANGLES, 0, batch.count)
    vao.release()
```

### `set_time(t)` — animation scrub / playback

Called by `_TimelineBar.time_changed` on every timer tick or slider drag.

1. Update `_current_time`.
2. `_update_time()` — **fast path**: re-triangulate each mesh at the new time
   and re-upload VBO data with `allocate()` (overwrites in place).  
   Model matrices are recomputed from `UsdGeom.Xformable`.  
   If any mesh has a different vertex count (topology changed), fall back to
   a full `_rebuild_geometry()`.

### Stage change notifications

```
Tf.Notice.Register(Usd.Notice.ObjectsChanged, callback, stage)
```

The callback fires on the authoring thread.  To keep GPU calls on the main
thread, the callback starts a zero-interval `QTimer` whose `timeout` runs
`_rebuild_geometry()` on the main thread.

When **Paused**, the listener is revoked; on **Resume** it is re-registered.

---

## Coordinate system

| System | Convention | Multiplication |
|--------|-----------|----------------|
| USD / `Gf.Matrix4d` | Row-major, right-handed Y-up | `v' = v · M` |
| OpenGL / `QMatrix4x4` | Column-major, right-handed Y-up | `v' = M · v` |

`_gf_to_qt(m)` transposes the USD matrix so that the same spatial transform
is expressed correctly for OpenGL:

```python
QMatrix4x4(
    m[0][0], m[1][0], m[2][0], m[3][0],   # row 0 = column 0 of USD matrix
    m[0][1], m[1][1], m[2][1], m[3][1],
    m[0][2], m[1][2], m[2][2], m[3][2],
    m[0][3], m[1][3], m[2][3], m[3][3],
)
```

---

## Navigation (free camera)

| Action | Effect |
|--------|--------|
| Left-drag | Orbit around pivot |
| Middle-drag | Pan pivot |
| Right-drag / scroll wheel | Dolly in/out |
| `F` or `Home` | Reset camera to default |

Navigation is disabled while a stage camera is selected.

---

## Timeline controls

| Control | Action |
|---------|--------|
| `\|◀` button | Jump to first frame |
| `▶ / ⏸` button | Start / pause playback |
| Frame spinbox | Type a specific time code |
| Slider | Scrub through the range |

Playback wraps (loops) automatically.  The bar is greyed out when the stage
has no authored time-code range (`HasAuthoredTimeCodeRange() == False`).

---

## Known limitations

- **No materials** — all meshes render as a single clay colour.
- **Mesh only** — curves, points, volumes, lights, and instanced prims are skipped.
- **Flat normals** — authored normals from the USD file are ignored; normals
  are always computed per-triangle from the cross product of two edges.
- **`_update_time` is O(n_triangles)** — every frame of animation re-packs and
  re-uploads all geometry.  For large scenes this will be slow.  A production
  path would use `UsdImagingGL` (Hydra Storm / Embree / etc.).
- **Single render delegate** — the "Renderer" combo is decorative; only the
  custom GL path is implemented.  Extend `_RENDER_DELEGATES` and wire
  `_on_delegate_changed()` to add more backends.

---

## Extending

### Adding a new render delegate

```python
# in hydra_viewport.py
_RENDER_DELEGATES = ["GL (Simple)", "My Delegate"]

# in HydraViewport._on_delegate_changed(index):
#   switch on self._delegate_combo.itemText(index)
#   and reconfigure self._gl_view accordingly
```

### Using UsdImagingGL when available

If `pxr.UsdImagingGL` becomes importable (e.g. a Houdini or full USD build),
replace `_UsdGLViewport` with a thin wrapper that owns a
`UsdImagingGL.Engine`, calls `Engine.Render(params)` into an FBO, and blits
the result.  The `HydraViewport` container and `_TimelineBar` require no
changes — `set_stage()` and `set_time()` are the only interface points.
```
