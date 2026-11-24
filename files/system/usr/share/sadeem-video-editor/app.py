#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sadeem Video Editor (محرر فيديو سديم) — Main Application.
Provides:
- Standalone Adw.Application with org.sadeem.VideoEditor ID.
- Multi-window management: opening different videos opens separate windows;
  opening an already-opened video focuses its window.
- Single-page interface with ToastOverlay and window-level keyboard shortcut routing.
- Clean Welcome Screen with file chooser and drag-and-drop Gtk.DropTarget.
- Unified Sadeem Visual Identity styling and RTL/LTR internationalization.
"""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import i18n
import video_editor_ui
import video_utils

t = i18n.t

APP_ID = "org.sadeem.VideoEditor"

SADEEM_VIDEO_CSS = """
/* Sadeem Video Editor Unified Theme (Single-Page Professional Layout) */
.sadeem-canvas-bg {
    background-color: #101014;
}

.sadeem-sidebar-shell {
    background-color: #18181d;
    border-left: 1px solid rgba(255, 255, 255, 0.08);
}

/* Floating / Top Interaction Toolbar */
.top-toolbar-card {
    background-color: rgba(24, 24, 29, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 4px 8px;
}

.top-tool-btn {
    border-radius: 6px;
    padding: 6px 12px;
    background: transparent;
    color: rgba(255, 255, 255, 0.75);
    border: none;
    font-size: 12px;
    font-weight: 500;
}
.top-tool-btn:hover {
    background-color: rgba(255, 255, 255, 0.08);
    color: #ffffff;
}
.top-tool-btn-active {
    background-color: #7a1c33;
    color: #ffffff;
    font-weight: 600;
}

/* Unified Property Cards */
.property-card {
    background-color: rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    padding: 12px;
    margin-bottom: 8px;
}

.property-section-title {
    font-size: 11px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.65);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}

.property-subtle-label {
    font-size: 11px;
    color: #94a3b8;
}

/* Timeline Container */
.video-timeline-container {
    background-color: #18181d;
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 8px 12px;
}

.timeline-scroller scrollbar {
    background-color: rgba(20, 20, 25, 0.6);
    border-radius: 4px;
}
.timeline-scroller scrollbar.vertical {
    min-width: 8px;
}
.timeline-scroller scrollbar slider {
    min-width: 6px;
    min-height: 24px;
    border-radius: 4px;
    background-color: rgba(255, 255, 255, 0.28);
}
.timeline-scroller scrollbar slider:hover {
    background-color: rgba(255, 255, 255, 0.45);
}

.video-btn-play {
    border-radius: 50%;
    min-width: 38px;
    min-height: 38px;
    padding: 0;
    background-color: #7a1c33;
    color: #ffffff;
}
.video-btn-play:hover {
    background-color: #942540;
}

.video-time-lbl {
    font-family: monospace;
    font-weight: 700;
    font-size: 13px;
    color: #f1f5f9;
}

.badge {
    background-color: rgba(6, 182, 212, 0.15);
    color: #22d3ee;
    border-radius: 12px;
    padding: 2px 8px;
    font-weight: 600;
    font-size: 11px;
}

.badge-danger {
    background-color: rgba(239, 68, 68, 0.15);
    color: #ef4444;
    border-radius: 12px;
    padding: 2px 8px;
    font-weight: 600;
    font-size: 11px;
}

.video-progress-banner {
    background-color: rgba(122, 28, 51, 0.25);
    border-radius: 8px;
    border: 1px solid rgba(122, 28, 51, 0.5);
    padding: 6px 12px;
}

.sadeem-btn {
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
}
.sadeem-btn-compact {
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
}
.sadeem-btn-active {
    background-color: #7a1c33;
    color: #ffffff;
}
.sadeem-btn-danger {
    background-color: rgba(239, 68, 68, 0.15);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 6px;
    padding: 4px 10px;
}
.sadeem-btn-danger:hover {
    background-color: rgba(239, 68, 68, 0.28);
}

.swatch-dot {
    min-width: 20px;
    min-height: 20px;
    border-radius: 50%;
    padding: 0;
    border: 2px solid rgba(255, 255, 255, 0.2);
}
.swatch-dot-active {
    border-color: #ffffff;
    outline: 2px solid #7a1c33;
}

.sadeem-scale highlight {
    background-color: #7a1c33;
}

/* Welcome Screen */
.welcome-container {
    background-color: #141418;
}

.welcome-title {
    font-size: 26px;
    font-weight: 800;
    color: #f8fafc;
}

.welcome-subtitle {
    font-size: 14px;
    color: #94a3b8;
}

.welcome-drop-zone {
    border: 2px dashed rgba(255, 255, 255, 0.16);
    border-radius: 16px;
    background-color: rgba(255, 255, 255, 0.02);
    padding: 32px 48px;
}
.welcome-drop-zone:hover {
    border-color: #22d3ee;
    background-color: rgba(34, 211, 238, 0.04);
}

.welcome-open-btn {
    background-color: #7a1c33;
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
    border-radius: 24px;
    padding: 10px 28px;
}
.welcome-open-btn:hover {
    background-color: #942540;
}
"""


class VideoEditorWindow(Adw.ApplicationWindow):
    """Top-level application window hosting either the welcome screen or the editor."""

    def __init__(self, app, video_path=None):
        super().__init__(application=app)

        self.current_path = None
        self.video_editor_view = None
        self._force_close = False
        self._close_dialog_open = False

        self.set_title(t("app_name"))
        self.set_default_size(1080, 720)

        # Root Stack: "welcome" or "editor"
        self.root_stack = Gtk.Stack()
        self.root_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.root_stack.set_transition_duration(150)

        # Wrap root_stack in ToastOverlay so all in-app toasts display properly
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.root_stack)
        self.set_content(self.toast_overlay)

        self.welcome_widget = self._build_welcome_widget()
        self.root_stack.add_named(self.welcome_widget, "welcome")

        # Setup Drag and Drop onto window
        self._setup_drop_target()

        # Keyboard shortcuts at window level
        self._setup_key_controller()

        # Connect close request
        self.connect("close-request", self._on_close_request)

        if video_path and os.path.isfile(video_path):
            self.open_video(video_path)
        else:
            self.root_stack.set_visible_child_name("welcome")

    def add_toast(self, toast):
        """Display an Adw.Toast on the window's ToastOverlay."""
        if hasattr(self, "toast_overlay") and self.toast_overlay:
            self.toast_overlay.add_toast(toast)

    def _setup_key_controller(self):
        ctrl = Gtk.EventControllerKey()
        ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        ctrl.connect("key-pressed", self._on_window_key_pressed)
        self.add_controller(ctrl)

    def _on_window_key_pressed(self, _ctrl, keyval, _keycode, state):
        if not self.video_editor_view:
            return False

        focus = self.get_focus()
        is_text_entry = False
        if focus:
            if isinstance(focus, (Gtk.Editable, Gtk.TextView, Gtk.Entry, Gtk.SpinButton)):
                is_text_entry = True
            elif hasattr(Gtk, "Text") and isinstance(focus, Gtk.Text):
                is_text_entry = True

        ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        # Undo / Redo
        if ctrl_pressed:
            if keyval in (Gdk.KEY_z, Gdk.KEY_Z):
                if shift_pressed:
                    self.video_editor_view.redo()
                else:
                    self.video_editor_view.undo()
                return True
            elif keyval in (Gdk.KEY_y, Gdk.KEY_Y):
                self.video_editor_view.redo()
                return True

        if keyval == Gdk.KEY_Escape:
            self.video_editor_view.set_active_tool("select")
            self.set_focus(None)
            return True

        # When typing in text entry, do not intercept playback/editing shortcuts
        if is_text_entry:
            return False

        if keyval == Gdk.KEY_space:
            self.video_editor_view.toggle_play()
            return True
        elif keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.video_editor_view.split_current_segment()
            return True
        elif keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self.video_editor_view.delete_selected_item()
            return True
        elif keyval == Gdk.KEY_Left:
            self.video_editor_view.step_time(-1.0)
            return True
        elif keyval == Gdk.KEY_Right:
            self.video_editor_view.step_time(1.0)
            return True

        return False

    def _build_welcome_widget(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.add_css_class("welcome-container")

        # Top Bar for Welcome
        hb = Adw.HeaderBar()
        hb.set_title_widget(Adw.WindowTitle(title=t("welcome_title"), subtitle=t("app_name")))
        root.append(hb)

        # Center area
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        center_box.set_vexpand(True)
        center_box.set_hexpand(True)
        center_box.set_valign(Gtk.Align.CENTER)
        center_box.set_halign(Gtk.Align.CENTER)
        root.append(center_box)

        # App Icon
        icon_img = Gtk.Image.new_from_icon_name("org.sadeem.VideoEditor")
        icon_img.set_pixel_size(112)
        center_box.append(icon_img)

        # Titles
        lbl_title = Gtk.Label(label=t("welcome_title"))
        lbl_title.add_css_class("welcome-title")
        center_box.append(lbl_title)

        lbl_sub = Gtk.Label(label=t("welcome_subtitle"))
        lbl_sub.add_css_class("welcome-subtitle")
        lbl_sub.set_wrap(True)
        lbl_sub.set_justify(Gtk.Justification.CENTER)
        center_box.append(lbl_sub)

        # Drop Zone & Open Button
        drop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        drop_box.add_css_class("welcome-drop-zone")
        drop_box.set_halign(Gtk.Align.CENTER)
        center_box.append(drop_box)

        btn_open = Gtk.Button()
        bo_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bo_box.append(Gtk.Image.new_from_icon_name(video_editor_ui.safe_icon(["document-open-symbolic"])))
        bo_box.append(Gtk.Label(label=t("btn_open_video")))
        btn_open.set_child(bo_box)
        btn_open.add_css_class("welcome-open-btn")
        btn_open.connect("clicked", lambda _b: self._choose_video_dialog())
        drop_box.append(btn_open)

        lbl_drop = Gtk.Label(label=t("drop_video_here"))
        lbl_drop.add_css_class("property-subtle-label")
        drop_box.append(lbl_drop)

        return root

    def _setup_drop_target(self):
        drop_type = Gdk.FileList if hasattr(Gdk, "FileList") else Gio.File
        target = Gtk.DropTarget.new(drop_type, Gdk.DragAction.COPY)
        target.connect("drop", self._on_drop_file)
        self.add_controller(target)

    def _on_drop_file(self, _target, value, _x, _y):
        if not value:
            return False

        path_to_open = None
        if hasattr(value, "get_files"):
            files = value.get_files()
            if files:
                path_to_open = files[0].get_path()
        elif isinstance(value, Gio.File):
            path_to_open = value.get_path()
        elif isinstance(value, str):
            path_to_open = value

        if path_to_open and os.path.isfile(path_to_open) and video_utils.is_video_file(path_to_open):
            self.open_video(path_to_open)
            return True
        return False

    def _choose_video_dialog(self):
        if hasattr(Gtk, "FileDialog"):
            dialog = Gtk.FileDialog()
            dialog.set_title(t("dialog_choose_video"))

            v_filter = Gtk.FileFilter()
            v_filter.set_name(t("filter_video_files"))
            for ext in video_utils.VIDEO_EXTS:
                v_filter.add_pattern(f"*{ext}")
                v_filter.add_pattern(f"*{ext.upper()}")
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(v_filter)
            dialog.set_filters(filters)
            dialog.set_default_filter(v_filter)

            def _on_open_done(_dlg, result):
                try:
                    gfile = dialog.open_finish(result)
                    if gfile:
                        p = gfile.get_path()
                        if p and os.path.isfile(p):
                            self.open_video(p)
                except Exception:
                    pass

            dialog.open(self, None, _on_open_done)
        else:
            fc = Gtk.FileChooserNative.new(
                t("dialog_choose_video"),
                self,
                Gtk.FileChooserAction.OPEN,
                t("btn_open_video"),
                t("btn_cancel"),
            )
            v_filter = Gtk.FileFilter()
            v_filter.set_name(t("filter_video_files"))
            for ext in video_utils.VIDEO_EXTS:
                v_filter.add_pattern(f"*{ext}")
            fc.add_filter(v_filter)

            def _on_response(_dlg, res_id):
                if res_id == Gtk.ResponseType.ACCEPT:
                    gfile = fc.get_file()
                    if gfile:
                        self.open_video(gfile.get_path())

            fc.connect("response", _on_response)
            fc.show()

    def open_video(self, video_path):
        """Transition into editor mode with the specified video file."""
        if not video_path or not os.path.isfile(video_path):
            return

        if self.video_editor_view:
            self.video_editor_view._close_view()
            self.root_stack.remove(self.video_editor_view)
            self.video_editor_view = None

        self.current_path = os.path.realpath(video_path)
        self.set_title(f"{os.path.basename(video_path)} — {t('app_name')}")

        self.video_editor_view = video_editor_ui.VideoEditorView(
            window=self,
            video_path=video_path,
            on_saved=self._on_video_saved,
            on_close=self._on_editor_closed,
            on_open_another=self._choose_video_dialog,
        )
        self.root_stack.add_named(self.video_editor_view, "editor")
        self.root_stack.set_visible_child_name("editor")

    def _on_video_saved(self, new_path):
        if new_path and os.path.isfile(new_path) and new_path != self.current_path:
            self.open_video(new_path)

    def _on_editor_closed(self):
        self.root_stack.set_visible_child_name("welcome")
        self.current_path = None
        self.set_title(t("app_name"))

    def force_close_window(self):
        """Force close window bypassing unsaved checks, cleanly tearing down editor view."""
        self._force_close = True
        if self.video_editor_view:
            self.video_editor_view.has_unsaved_changes = False
            try:
                self.video_editor_view._close_view(trigger_callback=False)
            except Exception:
                pass
        def _do_destroy():
            self.destroy()
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_do_destroy)

    def _on_close_request(self, _win):
        if self._force_close:
            return False
        if self.video_editor_view and getattr(self.video_editor_view, "has_unsaved_changes", False):
            if self._close_dialog_open:
                return True
            self._confirm_close_with_unsaved()
            return True

        if self.video_editor_view:
            try:
                self.video_editor_view._close_view(trigger_callback=False)
            except Exception:
                pass
        return False

    def _present_alert(
        self,
        heading,
        body,
        on_confirm=None,
        confirm_label=None,
        cancel_label=None,
        destructive=True,
    ):
        confirm_lbl = confirm_label or t("btn_discard")
        cancel_lbl = cancel_label or t("btn_stay")

        if hasattr(Adw, "AlertDialog"):
            dialog = Adw.AlertDialog(heading=heading, body=body)
            dialog.add_response("cancel", cancel_lbl)
            dialog.add_response("confirm", confirm_lbl)
            if destructive:
                dialog.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")

            def _on_response(_d, result):
                try:
                    response = _d.choose_finish(result)
                except Exception:
                    response = "cancel"
                if response == "confirm" and on_confirm:
                    on_confirm()

            dialog.choose(self, None, _on_response)
        else:
            dlg = Adw.MessageDialog(transient_for=self, heading=heading, body=body)
            dlg.add_response("cancel", cancel_lbl)
            dlg.add_response("confirm", confirm_lbl)
            if destructive:
                dlg.set_response_appearance("confirm", Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.set_default_response("cancel")
            dlg.set_close_response("cancel")

            def _on_response(_d, response):
                if response == "confirm" and on_confirm:
                    on_confirm()

            dlg.connect("response", _on_response)
            dlg.present()

    def _confirm_close_with_unsaved(self):
        self._close_dialog_open = True

        def _handle_choice(choice):
            self._close_dialog_open = False
            if choice == "discard":
                self.force_close_window()
            elif choice == "save_and_close":
                if self.video_editor_view and hasattr(self.video_editor_view, "open_save_choice_dialog"):
                    def _do_open_save_choice():
                        self.video_editor_view.open_save_choice_dialog(close_after_save=True)
                        return GLib.SOURCE_REMOVE

                    GLib.idle_add(_do_open_save_choice)

        heading = t("unsaved_title")
        body = t("unsaved_msg")

        if hasattr(Adw, "AlertDialog"):
            dialog = Adw.AlertDialog(heading=heading, body=body)
            dialog.add_response("stay", t("btn_stay"))
            dialog.add_response("discard", t("btn_discard_close"))
            dialog.add_response("save_and_close", t("btn_save_and_close"))

            dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_response_appearance("save_and_close", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("stay")
            dialog.set_close_response("stay")

            def _on_response(_d, result):
                try:
                    resp = _d.choose_finish(result)
                except Exception:
                    resp = "stay"
                _handle_choice(resp)

            dialog.choose(self, None, _on_response)
        else:
            dlg = Adw.MessageDialog(transient_for=self, heading=heading, body=body)
            dlg.add_response("stay", t("btn_stay"))
            dlg.add_response("discard", t("btn_discard_close"))
            dlg.add_response("save_and_close", t("btn_save_and_close"))

            dlg.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.set_response_appearance("save_and_close", Adw.ResponseAppearance.SUGGESTED)
            dlg.set_default_response("stay")
            dlg.set_close_response("stay")

            def _on_response(_d, resp):
                _handle_choice(resp)

            dlg.connect("response", _on_response)
            dlg.present()

    def _confirm_discard_unsaved(self):
        self._confirm_close_with_unsaved()


class SadeemVideoEditorApp(Adw.Application):
    """Main Adw.Application controller handling command lines and multi-window routing."""

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )

    def do_startup(self):
        Adw.Application.do_startup(self)

        if i18n.LANG == "ar":
            Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL)
        else:
            Gtk.Widget.set_default_direction(Gtk.TextDirection.LTR)

        self._install_css()

    def _install_css(self):
        swatch_rules = []
        for idx, (hx, _name) in enumerate(video_editor_ui.MARKUP_COLORS):
            swatch_rules.append(
                f"button.swatch-dot.swatch-color-{idx}, "
                f"button.swatch-dot.swatch-color-{idx}:hover, "
                f"button.swatch-dot.swatch-color-{idx}:active {{ "
                f"background: {hx}; background-color: {hx}; background-image: none; box-shadow: none; }}"
            )
        full_css = SADEEM_VIDEO_CSS + "\n" + "\n".join(swatch_rules)

        prov = Gtk.CssProvider()
        prov.load_from_string(full_css)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            local_icons = os.path.abspath(os.path.join(APP_DIR, "..", "icons"))
            if os.path.isdir(local_icons):
                Gtk.IconTheme.get_for_display(display).add_search_path(local_icons)

    def do_activate(self):
        for win in self.get_windows():
            if isinstance(win, VideoEditorWindow) and win.current_path is None:
                win.present()
                return

        win = VideoEditorWindow(self, video_path=None)
        win.present()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]

        target_file = None
        for a in args:
            if not a.startswith("-") and os.path.isfile(a) and video_utils.is_video_file(a):
                target_file = os.path.realpath(a)
                break

        if target_file:
            for win in self.get_windows():
                if isinstance(win, VideoEditorWindow) and win.current_path == target_file:
                    win.present()
                    return 0

            win = VideoEditorWindow(self, video_path=target_file)
            win.present()
            return 0

        self.activate()
        return 0


def main():
    app = SadeemVideoEditorApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
