#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe ctypes wrapper around libmpv.so.2 for Sadeem Video (فيديو سديم).
No external python-mpv dependency required.

Key guarantees:
- Sets locale.setlocale(locale.LC_NUMERIC, "C") immediately before mpv_create()
  so GTK/system locale initialization never breaks mpv option/number parsing.
- Resolves OpenGL / GLES function pointers via libEGL.so.1 (eglGetProcAddress)
  with fallback to libGL.so.1 and libGLESv2.so.2 (Wayland GLES & X11 GL).
- Queries active Gtk.GLArea framebuffer binding via glGetIntegerv(0x8CA6).
- Keeps strong references to ctypes callbacks for the engine lifetime.
- Drains mpv_wait_event(ctx, 0.0) cleanly and shuts down GL render context
  after area.make_current() prior to mpv_terminate_destroy().
"""

import ctypes
import locale
import os
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# libmpv C constants & structures (mpv ABI v2 / libmpv.so.2)
# ---------------------------------------------------------------------------
MPV_FORMAT_NONE = 0
MPV_FORMAT_STRING = 1
MPV_FORMAT_OSD_STRING = 2
MPV_FORMAT_FLAG = 3
MPV_FORMAT_INT64 = 4
MPV_FORMAT_DOUBLE = 5
MPV_FORMAT_NODE = 6
MPV_FORMAT_NODE_ARRAY = 7
MPV_FORMAT_NODE_MAP = 8
MPV_FORMAT_BYTE_ARRAY = 9

MPV_EVENT_NONE = 0
MPV_EVENT_SHUTDOWN = 1
MPV_EVENT_LOG_MESSAGE = 2
MPV_EVENT_GET_PROPERTY_REPLY = 3
MPV_EVENT_SET_PROPERTY_REPLY = 4
MPV_EVENT_COMMAND_REPLY = 5
MPV_EVENT_START_FILE = 6
MPV_EVENT_END_FILE = 7
MPV_EVENT_FILE_LOADED = 8
MPV_EVENT_IDLE = 11
MPV_EVENT_TICK = 14
MPV_EVENT_CLIENT_MESSAGE = 16
MPV_EVENT_VIDEO_RECONFIG = 17
MPV_EVENT_AUDIO_RECONFIG = 18
MPV_EVENT_SEEK = 20
MPV_EVENT_PLAYBACK_RESTART = 21
MPV_EVENT_PROPERTY_CHANGE = 22
MPV_EVENT_QUEUE_OVERFLOW = 24

MPV_END_FILE_REASON_EOF = 0
MPV_END_FILE_REASON_STOP = 2
MPV_END_FILE_REASON_QUIT = 3
MPV_END_FILE_REASON_ERROR = 4
MPV_END_FILE_REASON_REDIRECT = 5

MPV_RENDER_PARAM_INVALID = 0
MPV_RENDER_PARAM_API_TYPE = 1
MPV_RENDER_PARAM_OPENGL_INIT_PARAMS = 2
MPV_RENDER_PARAM_OPENGL_FBO = 3
MPV_RENDER_PARAM_FLIP_Y = 4

GL_FRAMEBUFFER_BINDING = 0x8CA6


class MpvUnavailableError(RuntimeError):
    """Raised when libmpv.so.2 or required OpenGL symbols cannot be loaded."""


class MpvError(RuntimeError):
    """Raised when a critical libmpv API call returns a negative status."""


class MpvNode(ctypes.Structure):
    pass


class MpvNodeList(ctypes.Structure):
    _fields_ = [
        ("num", ctypes.c_int),
        ("values", ctypes.POINTER(MpvNode)),
        ("keys", ctypes.POINTER(ctypes.c_char_p)),
    ]


class MpvByteArray(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
    ]


class MpvNodeUnion(ctypes.Union):
    _fields_ = [
        ("string", ctypes.c_char_p),
        ("flag", ctypes.c_int),
        ("int64", ctypes.c_int64),
        ("double_", ctypes.c_double),
        ("list", ctypes.POINTER(MpvNodeList)),
        ("ba", ctypes.POINTER(MpvByteArray)),
    ]


MpvNode._fields_ = [
    ("u", MpvNodeUnion),
    ("format", ctypes.c_int),
]


class MpvEvent(ctypes.Structure):
    _fields_ = [
        ("event_id", ctypes.c_int),
        ("error", ctypes.c_int),
        ("reply_userdata", ctypes.c_uint64),
        ("data", ctypes.c_void_p),
    ]


class MpvEventEndFile(ctypes.Structure):
    _fields_ = [
        ("reason", ctypes.c_int),
        ("error", ctypes.c_int),
        ("playlist_entry_id", ctypes.c_int64),
        ("playlist_insert_id", ctypes.c_int64),
        ("playlist_insert_num_entries", ctypes.c_int),
    ]


class MpvRenderParam(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("data", ctypes.c_void_p),
    ]


GET_PROC_ADDR_CB = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)
RENDER_UPDATE_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
WAKEUP_CB = ctypes.CFUNCTYPE(None, ctypes.c_void_p)


class MpvOpenGLInitParams(ctypes.Structure):
    _fields_ = [
        ("get_proc_address", GET_PROC_ADDR_CB),
        ("get_proc_address_ctx", ctypes.c_void_p),
    ]


class MpvOpenGLFBO(ctypes.Structure):
    _fields_ = [
        ("fbo", ctypes.c_int),
        ("w", ctypes.c_int),
        ("h", ctypes.c_int),
        ("internal_format", ctypes.c_int),
    ]


class GLProcResolver:
    """Resolves GL / GLES symbols via libEGL with libGL & libGLESv2 fallback."""

    def __init__(self) -> None:
        self._egl = self._try_load(("libEGL.so.1", "libEGL.so"))
        self._gles = self._try_load(("libGLESv2.so.2", "libGLESv2.so"))
        self._gl = self._try_load(("libGL.so.1", "libGL.so"))
        if self._egl and hasattr(self._egl, "eglGetProcAddress"):
            self._egl.eglGetProcAddress.argtypes = [ctypes.c_char_p]
            self._egl.eglGetProcAddress.restype = ctypes.c_void_p
        if self._gl and hasattr(self._gl, "glXGetProcAddressARB"):
            self._gl.glXGetProcAddressARB.argtypes = [ctypes.c_char_p]
            self._gl.glXGetProcAddressARB.restype = ctypes.c_void_p

    @staticmethod
    def _try_load(candidates) -> Optional[ctypes.CDLL]:
        for name in candidates:
            try:
                return ctypes.CDLL(name)
            except OSError:
                continue
        return None

    def resolve(self, name_bytes: bytes) -> int:
        if not name_bytes:
            return 0
        if self._egl and hasattr(self._egl, "eglGetProcAddress"):
            try:
                addr = self._egl.eglGetProcAddress(name_bytes)
                if addr:
                    return int(addr)
            except Exception:
                pass
        name_str = name_bytes.decode("ascii", errors="ignore")
        for lib in (self._gles, self._gl):
            if lib is None:
                continue
            sym = getattr(lib, name_str, None)
            if sym is not None:
                try:
                    return int(ctypes.cast(sym, ctypes.c_void_p).value or 0)
                except Exception:
                    pass
        if self._gl and hasattr(self._gl, "glXGetProcAddressARB"):
            try:
                addr = self._gl.glXGetProcAddressARB(name_bytes)
                if addr:
                    return int(addr)
            except Exception:
                pass
        return 0


def load_libmpv():
    """Load libmpv.so.2 and configure C signatures."""
    lib = None
    for candidate in ("libmpv.so.2", "libmpv.so", "/usr/lib64/libmpv.so.2", "/usr/lib/libmpv.so.2"):
        try:
            lib = ctypes.CDLL(candidate)
            break
        except OSError:
            continue
    if lib is None:
        raise MpvUnavailableError("Could not load libmpv.so.2 shared library.")

    lib.mpv_create.argtypes = []
    lib.mpv_create.restype = ctypes.c_void_p

    lib.mpv_initialize.argtypes = [ctypes.c_void_p]
    lib.mpv_initialize.restype = ctypes.c_int

    lib.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
    lib.mpv_terminate_destroy.restype = None

    lib.mpv_set_option_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.mpv_set_option_string.restype = ctypes.c_int

    lib.mpv_set_property.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
    lib.mpv_set_property.restype = ctypes.c_int

    lib.mpv_set_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.mpv_set_property_string.restype = ctypes.c_int

    lib.mpv_get_property.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
    lib.mpv_get_property.restype = ctypes.c_int

    lib.mpv_get_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.mpv_get_property_string.restype = ctypes.c_void_p

    lib.mpv_command.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
    lib.mpv_command.restype = ctypes.c_int

    if hasattr(lib, "mpv_command_async"):
        lib.mpv_command_async.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)]
        lib.mpv_command_async.restype = ctypes.c_int

    lib.mpv_wait_event.argtypes = [ctypes.c_void_p, ctypes.c_double]
    lib.mpv_wait_event.restype = ctypes.POINTER(MpvEvent)

    if hasattr(lib, "mpv_set_wakeup_callback"):
        lib.mpv_set_wakeup_callback.argtypes = [ctypes.c_void_p, WAKEUP_CB, ctypes.c_void_p]
        lib.mpv_set_wakeup_callback.restype = None

    lib.mpv_free.argtypes = [ctypes.c_void_p]
    lib.mpv_free.restype = None

    lib.mpv_free_node_contents.argtypes = [ctypes.POINTER(MpvNode)]
    lib.mpv_free_node_contents.restype = None

    lib.mpv_error_string.argtypes = [ctypes.c_int]
    lib.mpv_error_string.restype = ctypes.c_char_p

    lib.mpv_render_context_create.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(MpvRenderParam),
    ]
    lib.mpv_render_context_create.restype = ctypes.c_int

    lib.mpv_render_context_set_update_callback.argtypes = [
        ctypes.c_void_p,
        RENDER_UPDATE_CB,
        ctypes.c_void_p,
    ]
    lib.mpv_render_context_set_update_callback.restype = None

    lib.mpv_render_context_render.argtypes = [ctypes.c_void_p, ctypes.POINTER(MpvRenderParam)]
    lib.mpv_render_context_render.restype = ctypes.c_int

    if hasattr(lib, "mpv_render_context_report_swap"):
        lib.mpv_render_context_report_swap.argtypes = [ctypes.c_void_p]
        lib.mpv_render_context_report_swap.restype = None

    lib.mpv_render_context_free.argtypes = [ctypes.c_void_p]
    lib.mpv_render_context_free.restype = None

    return lib


def _node_to_python(node: MpvNode) -> Any:
    fmt = node.format
    if fmt == MPV_FORMAT_NONE:
        return None
    if fmt in (MPV_FORMAT_STRING, MPV_FORMAT_OSD_STRING):
        raw = node.u.string
        return raw.decode("utf-8", errors="replace") if raw else ""
    if fmt == MPV_FORMAT_FLAG:
        return bool(node.u.flag)
    if fmt == MPV_FORMAT_INT64:
        return int(node.u.int64)
    if fmt == MPV_FORMAT_DOUBLE:
        return float(node.u.double_)
    if fmt == MPV_FORMAT_NODE_ARRAY:
        if not node.u.list:
            return []
        nl = node.u.list.contents
        return [_node_to_python(nl.values[i]) for i in range(nl.num)]
    if fmt == MPV_FORMAT_NODE_MAP:
        if not node.u.list:
            return {}
        nl = node.u.list.contents
        out = {}
        for i in range(nl.num):
            k = nl.keys[i].decode("utf-8", errors="replace") if nl.keys[i] else ""
            out[k] = _node_to_python(nl.values[i])
        return out
    if fmt == MPV_FORMAT_BYTE_ARRAY:
        if not node.u.ba:
            return b""
        ba = node.u.ba.contents
        return ctypes.string_at(ba.data, ba.size)
    return None


class MpvEngine:
    """High-level safe wrapper around a libmpv client handle and GL render context."""

    DEFAULT_OPTIONS = {
        "vo": "libmpv",
        "hwdec": "auto-copy",
        "keep-open": "yes",
        "sub-auto": "fuzzy",
        "sub-codepage": "auto",
        "sub-vsfilter-bidi-compat": "no",
        "sub-margin-y": "34",
        "sub-border-size": "2.5",
        "embeddedfonts": "yes",
        "volume-max": "150",
        "osd-level": "0",
        "osc": "no",
        "input-default-bindings": "no",
        "input-vo-keyboard": "no",
        "screenshot-format": "png",
        "ytdl": "no",
    }

    def __init__(self, libmpv=None, gl_resolver: Optional[GLProcResolver] = None) -> None:
        self._lib = libmpv
        self._gl_resolver = gl_resolver
        self._ctx: Optional[int] = None
        self._render_ctx: Optional[int] = None
        self._alive = False

        # Keep strong refs to C callbacks & parameter buffers
        self._get_proc_cb = None
        self._render_update_cb = None
        self._wakeup_cb = None
        self._api_type_buf = None
        self._init_params = None
        self._gl_get_integerv = None
        self._gl_area = None
        self._on_render_update: Optional[Callable[[], None]] = None

    @property
    def is_initialized(self) -> bool:
        return bool(self._ctx) and self._alive

    @property
    def has_render_context(self) -> bool:
        return bool(self._render_ctx)

    def _ensure_lib(self):
        if self._lib is None:
            self._lib = load_libmpv()
        return self._lib

    def _check_err(self, rc: int, action: str) -> None:
        if rc < 0:
            try:
                msg = self._lib.mpv_error_string(rc)
                text = msg.decode("utf-8", errors="replace") if msg else f"error {rc}"
            except Exception:
                text = f"error {rc}"
            raise MpvError(f"{action} failed ({rc}): {text}")

    def initialize(self, extra_options: Optional[Dict[str, str]] = None) -> None:
        """Create and initialize libmpv instance with mandatory LC_NUMERIC=C."""
        if self._ctx:
            return
        lib = self._ensure_lib()

        # Mandatory: gtk_init changes LC_NUMERIC to system locale (e.g. Arabic decimal separator),
        # causing mpv_create() to return NULL unless LC_NUMERIC is reset to "C".
        try:
            locale.setlocale(locale.LC_NUMERIC, "C")
        except locale.Error:
            pass

        ctx = lib.mpv_create()
        if not ctx:
            raise MpvUnavailableError("mpv_create() returned NULL (check LC_NUMERIC=C and libmpv).")
        self._ctx = ctx

        opts = dict(self.DEFAULT_OPTIONS)
        if extra_options:
            opts.update(extra_options)

        for key, val in opts.items():
            rc = lib.mpv_set_option_string(
                self._ctx,
                str(key).encode("utf-8"),
                str(val).encode("utf-8"),
            )
            if rc < 0:
                # Non-fatal warning-safe behavior for optional mpv flags; fail only for core ones
                if key in ("vo", "keep-open"):
                    self._check_err(rc, f"mpv_set_option_string({key})")

        rc = lib.mpv_initialize(self._ctx)
        if rc < 0:
            lib.mpv_terminate_destroy(self._ctx)
            self._ctx = None
            self._check_err(rc, "mpv_initialize")

        self._alive = True

    def setup_gl_render(
        self,
        gl_area,
        on_update: Optional[Callable[[], None]] = None,
    ) -> None:
        """Attach an OpenGL render context to a realized Gtk.GLArea."""
        if not self.is_initialized:
            raise MpvError("MpvEngine must be initialized before setup_gl_render().")
        if self._render_ctx:
            return

        self._gl_area = gl_area
        self._on_render_update = on_update

        gl_area.make_current()
        gl_err = gl_area.get_error()
        if gl_err is not None:
            raise MpvUnavailableError(f"Gtk.GLArea GL context error: {gl_err}")

        if self._gl_resolver is None:
            self._gl_resolver = GLProcResolver()

        resolver = self._gl_resolver

        def _get_proc(_cb_ctx, name_ptr):
            return resolver.resolve(name_ptr)

        self._get_proc_cb = GET_PROC_ADDR_CB(_get_proc)
        self._init_params = MpvOpenGLInitParams(self._get_proc_cb, None)
        self._api_type_buf = ctypes.create_string_buffer(b"opengl")

        params = (MpvRenderParam * 3)(
            MpvRenderParam(MPV_RENDER_PARAM_API_TYPE, ctypes.cast(self._api_type_buf, ctypes.c_void_p)),
            MpvRenderParam(MPV_RENDER_PARAM_OPENGL_INIT_PARAMS, ctypes.cast(ctypes.byref(self._init_params), ctypes.c_void_p)),
            MpvRenderParam(MPV_RENDER_PARAM_INVALID, None),
        )

        rctx = ctypes.c_void_p()
        rc = self._lib.mpv_render_context_create(ctypes.byref(rctx), self._ctx, params)
        self._check_err(rc, "mpv_render_context_create")
        self._render_ctx = rctx.value

        # Resolve glGetIntegerv so render_frame reads the true active FBO bound by Gtk.GLArea
        gl_get_int_ptr = resolver.resolve(b"glGetIntegerv")
        if gl_get_int_ptr:
            self._gl_get_integerv = ctypes.CFUNCTYPE(
                None, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)
            )(gl_get_int_ptr)

        def _on_mpv_update(_cb_ctx):
            if self._alive and self._on_render_update is not None:
                self._on_render_update()

        self._render_update_cb = RENDER_UPDATE_CB(_on_mpv_update)
        self._lib.mpv_render_context_set_update_callback(
            self._render_ctx, self._render_update_cb, None
        )

    def render_frame(self, width: int, height: int, fbo_id: Optional[int] = None) -> bool:
        """Render the current video frame into the active OpenGL framebuffer."""
        if not self._render_ctx or not self._alive:
            return False
        if fbo_id is None:
            fbo_val = ctypes.c_int(0)
            if self._gl_get_integerv is not None:
                self._gl_get_integerv(GL_FRAMEBUFFER_BINDING, ctypes.byref(fbo_val))
            fbo_num = int(fbo_val.value)
        else:
            fbo_num = int(fbo_id)

        fbo = MpvOpenGLFBO(fbo_num, max(1, int(width)), max(1, int(height)), 0)
        flip_y = ctypes.c_int(1)
        params = (MpvRenderParam * 3)(
            MpvRenderParam(MPV_RENDER_PARAM_OPENGL_FBO, ctypes.cast(ctypes.byref(fbo), ctypes.c_void_p)),
            MpvRenderParam(MPV_RENDER_PARAM_FLIP_Y, ctypes.cast(ctypes.byref(flip_y), ctypes.c_void_p)),
            MpvRenderParam(MPV_RENDER_PARAM_INVALID, None),
        )
        rc = self._lib.mpv_render_context_render(self._render_ctx, params)
        return rc >= 0

    def destroy_gl_render(self, gl_area=None) -> None:
        """Safely free mpv_render_context with an active GL context."""
        area = gl_area or self._gl_area
        if self._render_ctx and self._lib:
            try:
                if area is not None and area.get_realized():
                    area.make_current()
            except Exception:
                pass
            try:
                self._lib.mpv_render_context_free(self._render_ctx)
            finally:
                self._render_ctx = None
        self._gl_area = None
        self._on_render_update = None

    def destroy(self, gl_area=None) -> None:
        """Safely tear down GL render context first, then terminate libmpv."""
        self._alive = False
        self.destroy_gl_render(gl_area=gl_area)
        if self._ctx and self._lib:
            ctx = self._ctx
            self._ctx = None
            self._lib.mpv_terminate_destroy(ctx)

    def drain_events(self, handler: Optional[Callable[[Dict[str, Any]], None]] = None) -> List[Dict[str, Any]]:
        """Drain queued mpv events without blocking so the event queue never overflows."""
        events: List[Dict[str, Any]] = []
        if not self._ctx or not self._lib:
            return events
        while self._alive and self._ctx:
            ev_ptr = self._lib.mpv_wait_event(self._ctx, 0.0)
            if not ev_ptr:
                break
            ev = ev_ptr.contents
            ev_id = int(ev.event_id)
            if ev_id == MPV_EVENT_NONE:
                break
            info: Dict[str, Any] = {
                "event_id": ev_id,
                "error": int(ev.error),
            }
            if ev_id == MPV_EVENT_END_FILE and ev.data:
                end_data = ctypes.cast(ev.data, ctypes.POINTER(MpvEventEndFile)).contents
                info["reason"] = int(end_data.reason)
                info["end_error"] = int(end_data.error)
            events.append(info)
            if handler is not None:
                handler(info)
            if ev_id == MPV_EVENT_SHUTDOWN:
                break
        return events

    # -----------------------------------------------------------------------
    # Commands & Properties
    # -----------------------------------------------------------------------
    def command(self, *args: Any) -> int:
        if not self.is_initialized:
            return -1
        c_args = [str(a).encode("utf-8") for a in args] + [None]
        arr = (ctypes.c_char_p * len(c_args))(*c_args)
        return int(self._lib.mpv_command(self._ctx, arr))

    def command_async(self, *args: Any, reply_userdata: int = 0) -> int:
        """Issue an async mpv command without blocking the GTK main thread."""
        if not self.is_initialized:
            return -1
        fn = getattr(self._lib, "mpv_command_async", None)
        if fn is None:
            return self.command(*args)
        c_args = [str(a).encode("utf-8") for a in args] + [None]
        arr = (ctypes.c_char_p * len(c_args))(*c_args)
        return int(fn(self._ctx, int(reply_userdata), arr))

    def set_property_string(self, name: str, value: str) -> int:
        if not self.is_initialized:
            return -1
        return int(
            self._lib.mpv_set_property_string(
                self._ctx, name.encode("utf-8"), str(value).encode("utf-8")
            )
        )

    def set_property_bool(self, name: str, value: bool) -> int:
        if not self.is_initialized:
            return -1
        flag = ctypes.c_int(1 if value else 0)
        return int(
            self._lib.mpv_set_property(
                self._ctx, name.encode("utf-8"), MPV_FORMAT_FLAG, ctypes.byref(flag)
            )
        )

    def set_property_int(self, name: str, value: int) -> int:
        if not self.is_initialized:
            return -1
        num = ctypes.c_int64(int(value))
        return int(
            self._lib.mpv_set_property(
                self._ctx, name.encode("utf-8"), MPV_FORMAT_INT64, ctypes.byref(num)
            )
        )

    def set_property_double(self, name: str, value: float) -> int:
        if not self.is_initialized:
            return -1
        dbl = ctypes.c_double(float(value))
        return int(
            self._lib.mpv_set_property(
                self._ctx, name.encode("utf-8"), MPV_FORMAT_DOUBLE, ctypes.byref(dbl)
            )
        )

    def get_property_string(self, name: str, default: Optional[str] = None) -> Optional[str]:
        if not self.is_initialized:
            return default
        ptr = self._lib.mpv_get_property_string(self._ctx, name.encode("utf-8"))
        if not ptr:
            return default
        try:
            raw = ctypes.cast(ptr, ctypes.c_char_p).value
            return raw.decode("utf-8", errors="replace") if raw is not None else default
        finally:
            self._lib.mpv_free(ptr)

    def get_property_bool(self, name: str, default: bool = False) -> bool:
        if not self.is_initialized:
            return default
        val = ctypes.c_int(0)
        rc = self._lib.mpv_get_property(
            self._ctx, name.encode("utf-8"), MPV_FORMAT_FLAG, ctypes.byref(val)
        )
        return bool(val.value) if rc >= 0 else default

    def get_property_int(self, name: str, default: int = 0) -> int:
        if not self.is_initialized:
            return default
        val = ctypes.c_int64(0)
        rc = self._lib.mpv_get_property(
            self._ctx, name.encode("utf-8"), MPV_FORMAT_INT64, ctypes.byref(val)
        )
        return int(val.value) if rc >= 0 else default

    def get_property_double(self, name: str, default: float = 0.0) -> float:
        if not self.is_initialized:
            return default
        val = ctypes.c_double(0.0)
        rc = self._lib.mpv_get_property(
            self._ctx, name.encode("utf-8"), MPV_FORMAT_DOUBLE, ctypes.byref(val)
        )
        return float(val.value) if rc >= 0 else default

    def get_property_node(self, name: str, default: Any = None) -> Any:
        if not self.is_initialized:
            return default
        node = MpvNode()
        rc = self._lib.mpv_get_property(
            self._ctx, name.encode("utf-8"), MPV_FORMAT_NODE, ctypes.byref(node)
        )
        if rc < 0:
            return default
        try:
            return _node_to_python(node)
        finally:
            self._lib.mpv_free_node_contents(ctypes.byref(node))

    # -----------------------------------------------------------------------
    # Playback convenience API
    # -----------------------------------------------------------------------
    def load_file(self, path: str, start_seconds: float = 0.0) -> int:
        # Clear any active A-B loop when switching media
        self.set_ab_loop(None, None)
        if start_seconds and start_seconds > 1.0:
            # Pass start option safely per-file when resuming
            rc = self.command_async("loadfile", path, "replace", "-1", f"start={start_seconds:.3f}")
            if rc < 0:
                rc = self.command_async("loadfile", path, "replace")
        else:
            rc = self.command_async("loadfile", path, "replace")
        self.set_paused(False)
        return rc

    def set_paused(self, paused: bool) -> int:
        return self.set_property_bool("pause", bool(paused))

    def is_paused(self) -> bool:
        return self.get_property_bool("pause", False)

    def toggle_pause(self) -> bool:
        now_paused = not self.is_paused()
        self.set_paused(now_paused)
        return now_paused

    def stop(self) -> int:
        return self.command("stop")

    def seek(self, offset: float, exact: bool = False) -> int:
        mode = "relative+exact" if exact else "relative"
        return self.command_async("seek", f"{float(offset):.3f}", mode)

    def seek_absolute(self, seconds: float) -> int:
        return self.command_async("seek", f"{max(0.0, float(seconds)):.3f}", "absolute")

    def frame_step(self) -> int:
        return self.command("frame-step")

    def frame_back_step(self) -> int:
        return self.command("frame-back-step")

    def get_time_pos(self) -> float:
        return max(0.0, self.get_property_double("time-pos", 0.0))

    def get_duration(self) -> float:
        return max(0.0, self.get_property_double("duration", 0.0))

    def set_volume(self, volume: float) -> int:
        clamped = max(0.0, min(150.0, float(volume)))
        return self.set_property_double("volume", clamped)

    def get_volume(self) -> float:
        return self.get_property_double("volume", 100.0)

    def set_mute(self, muted: bool) -> int:
        return self.set_property_bool("mute", bool(muted))

    def get_mute(self) -> bool:
        return self.get_property_bool("mute", False)

    def set_speed(self, speed: float) -> int:
        clamped = max(0.25, min(4.0, float(speed)))
        return self.set_property_double("speed", clamped)

    def get_speed(self) -> float:
        return self.get_property_double("speed", 1.0)

    def set_loop_file(self, enabled: bool) -> int:
        return self.set_property_string("loop-file", "inf" if enabled else "no")

    def set_ab_loop(self, a: Optional[float], b: Optional[float]) -> None:
        self.set_property_string("ab-loop-a", f"{float(a):.3f}" if a is not None else "no")
        self.set_property_string("ab-loop-b", f"{float(b):.3f}" if b is not None else "no")

    def set_audio_track(self, track_id: int) -> int:
        return self.set_property_int("aid", int(track_id))

    def set_subtitle_track(self, track_id: Optional[int]) -> int:
        if track_id is None or track_id == 0:
            return self.set_property_string("sid", "no")
        return self.set_property_int("sid", int(track_id))

    def add_subtitle(self, sub_path: str) -> int:
        return self.command_async("sub-add", sub_path, "select")

    def set_sub_bidi_compat(self, enabled: bool) -> int:
        rc = self.set_property_string("sub-vsfilter-bidi-compat", "yes" if enabled else "no")
        if rc >= 0:
            cur_sid = self.get_property_int("sid", 0)
            if cur_sid > 0:
                tracks = self.get_tracks().get("sub", [])
                active = next((tr for tr in tracks if tr.get("id") == cur_sid), None)
                if active and active.get("external"):
                    self.command_async("sub-reload")
                else:
                    self.set_property_string("sid", "no")
                    self.set_property_int("sid", cur_sid)
        return rc

    def get_sub_bidi_compat(self) -> bool:
        val = self.get_property_string("sub-vsfilter-bidi-compat", "no")
        return str(val).strip().lower() == "yes"

    def set_sub_delay(self, seconds: float) -> int:
        return self.set_property_double("sub-delay", float(seconds))

    def set_sub_scale(self, scale: float) -> int:
        clamped = max(0.3, min(3.0, float(scale)))
        return self.set_property_double("sub-scale", clamped)

    def set_aspect_ratio(self, mode: str) -> None:
        """mode: 'auto' ('-1'), '16:9', '4:3', '21:9', or 'fill'."""
        if mode == "fill":
            self.set_property_string("video-aspect-override", "-1")
            self.set_property_double("panscan", 1.0)
        elif mode == "auto":
            self.set_property_double("panscan", 0.0)
            self.set_property_string("video-aspect-override", "-1")
        else:
            self.set_property_double("panscan", 0.0)
            self.set_property_string("video-aspect-override", mode)

    def set_rotation(self, degrees: int) -> int:
        deg = int(degrees) % 360
        return self.set_property_int("video-rotate", deg)

    def set_equalizer(
        self,
        brightness: Optional[float] = None,
        contrast: Optional[float] = None,
        saturation: Optional[float] = None,
        gamma: Optional[float] = None,
    ) -> None:
        if brightness is not None:
            self.set_property_double("brightness", float(brightness))
        if contrast is not None:
            self.set_property_double("contrast", float(contrast))
        if saturation is not None:
            self.set_property_double("saturation", float(saturation))
        if gamma is not None:
            self.set_property_double("gamma", float(gamma))

    def reset_equalizer(self) -> None:
        self.set_equalizer(brightness=0.0, contrast=0.0, saturation=0.0, gamma=0.0)

    def take_screenshot(self, output_path: str) -> int:
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return self.command("screenshot-to-file", output_path, "subtitles")

    def get_tracks(self) -> Dict[str, List[Dict[str, Any]]]:
        raw = self.get_property_node("track-list", []) or []
        audio: List[Dict[str, Any]] = []
        sub: List[Dict[str, Any]] = []
        video: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            t_type = item.get("type")
            entry = {
                "id": int(item.get("id", 0)),
                "title": item.get("title") or "",
                "lang": item.get("lang") or "",
                "codec": item.get("codec") or "",
                "selected": bool(item.get("selected", False)),
                "external": bool(item.get("external", False)),
                "demux-w": item.get("demux-w"),
                "demux-h": item.get("demux-h"),
                "demux-fps": item.get("demux-fps"),
            }
            if t_type == "audio":
                audio.append(entry)
            elif t_type == "sub":
                sub.append(entry)
            elif t_type == "video":
                video.append(entry)
        return {"video": video, "audio": audio, "sub": sub}

    def get_chapters(self) -> List[Dict[str, Any]]:
        raw = self.get_property_node("chapter-list", []) or []
        chapters: List[Dict[str, Any]] = []
        for idx, ch in enumerate(raw):
            if not isinstance(ch, dict):
                continue
            chapters.append(
                {
                    "index": idx,
                    "title": ch.get("title") or "",
                    "time": float(ch.get("time", 0.0)),
                }
            )
        return chapters

    def get_media_info(self) -> Dict[str, Any]:
        tracks = self.get_tracks()
        video_track = next((v for v in tracks["video"] if v.get("selected")), None)
        if video_track is None and tracks["video"]:
            video_track = tracks["video"][0]

        width = self.get_property_int("width", 0) or (video_track.get("demux-w") if video_track else 0) or 0
        height = self.get_property_int("height", 0) or (video_track.get("demux-h") if video_track else 0) or 0
        fps = self.get_property_double("container-fps", 0.0) or self.get_property_double("estimated-vf-fps", 0.0)
        if not fps and video_track and video_track.get("demux-fps"):
            fps = float(video_track["demux-fps"])

        video_codec = self.get_property_string("video-codec") or (video_track.get("codec") if video_track else "") or ""
        hwdec_current = self.get_property_string("hwdec-current") or "no"
        duration = self.get_duration()
        return {
            "width": int(width),
            "height": int(height),
            "fps": float(fps or 0.0),
            "video_codec": str(video_codec),
            "hwdec_current": str(hwdec_current),
            "duration": float(duration),
            "audio_tracks": tracks["audio"],
            "sub_tracks": tracks["sub"],
            "chapters": self.get_chapters(),
        }
