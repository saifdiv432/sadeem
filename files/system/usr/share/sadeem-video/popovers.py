#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modular Libadwaita Popovers for Sadeem Video (فيديو سديم).
Builds the Audio & Subtitles popover and the multi-page Settings popover
using calm adaptive neutral highlights and Gtk.Stack slide navigation.
"""

import os
from typing import Callable, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gtk, Pango

import i18n
import playlist

t = i18n.t

SADEEM_VIDEO_PLAYER_CSS = """
.sadeem-video-stage {
    background-color: #000000;
}

.sadeem-hud-top {
    background-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.72), transparent);
    background-color: transparent;
    color: #ffffff;
    border: none;
    border-radius: 0px;
    padding: 10px 16px 20px 16px;
}

.sadeem-osd-btn {
    color: #f8fafc;
    background-color: rgba(20, 20, 26, 0.52);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 999px;
    min-width: 34px;
    min-height: 34px;
    padding: 4px 10px;
}
.sadeem-osd-btn:hover {
    background-color: rgba(255, 255, 255, 0.18);
    color: #ffffff;
}
.sadeem-osd-btn:disabled {
    opacity: 0.45;
}

.sadeem-hud-capsule {
    background-color: rgba(20, 20, 24, 0.88);
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 18px;
    padding: 10px 16px;
    margin: 0 16px 18px 16px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55);
}

menubutton.sadeem-hud-btn,
menubutton.sadeem-hud-btn:hover,
menubutton.sadeem-hud-btn:active {
    background: none;
    background-color: transparent;
    border: none;
    padding: 0;
    margin: 0;
    min-width: 0;
    min-height: 0;
    box-shadow: none;
}

button.sadeem-hud-btn,
menubutton.sadeem-hud-btn > button {
    color: #f8fafc;
    background-color: transparent;
    border-radius: 999px;
    min-width: 34px;
    min-height: 34px;
    padding: 0;
}
button.sadeem-hud-btn:hover,
menubutton.sadeem-hud-btn > button:hover,
menubutton.sadeem-hud-btn > button:checked {
    background-color: rgba(255, 255, 255, 0.14);
}
button.sadeem-hud-btn:disabled,
menubutton.sadeem-hud-btn > button:disabled {
    color: rgba(248, 250, 252, 0.35);
}

.sadeem-vol-boost {
    color: #5eead4;
}

.sadeem-play-btn {
    background-color: #7a1c33;
    color: #ffffff;
    border-radius: 999px;
    min-width: 38px;
    min-height: 38px;
    padding: 0;
}
.sadeem-play-btn:hover {
    background-color: #93233e;
}

.sadeem-video-title {
    font-weight: 600;
    font-size: 13px;
    color: #ffffff;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.85);
}

.sadeem-time-label {
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    font-weight: 600;
    color: rgba(248, 250, 252, 0.94);
    min-width: 48px;
}

.sadeem-seek-scale trough {
    min-height: 6px;
    border-radius: 999px;
    background-color: rgba(255, 255, 255, 0.22);
}
.sadeem-seek-scale highlight {
    border-radius: 999px;
    background-color: #7a1c33;
}
.sadeem-seek-scale slider {
    min-width: 14px;
    min-height: 14px;
    margin: -4px;
    border-radius: 999px;
    background-color: #ffffff;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.55);
}

.sadeem-vol-scale trough {
    min-height: 5px;
    border-radius: 999px;
    background-color: rgba(255, 255, 255, 0.22);
}
.sadeem-vol-scale highlight {
    border-radius: 999px;
    background-color: rgba(248, 250, 252, 0.85);
}
.sadeem-vol-scale slider {
    min-width: 12px;
    min-height: 12px;
    margin: -3px;
    border-radius: 999px;
    background-color: #ffffff;
}

.sadeem-osd-badge {
    background-color: rgba(15, 16, 20, 0.86);
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 999px;
    padding: 8px 18px;
    font-size: 14px;
    font-weight: 600;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.48);
}

.sadeem-resume-banner {
    background-color: rgba(20, 20, 24, 0.90);
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 14px;
    padding: 8px 14px;
    margin-bottom: 112px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.52);
}

.sadeem-resume-btn {
    background-color: rgba(255, 255, 255, 0.16);
    color: #ffffff;
    border-radius: 999px;
    font-weight: 600;
    padding: 4px 14px;
}
.sadeem-resume-btn:hover {
    background-color: rgba(255, 255, 255, 0.26);
}

.sadeem-welcome-card {
    background-color: rgba(20, 20, 26, 0.88);
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 20px;
    padding: 28px 34px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.55);
}

.sadeem-playlist-active {
    background-color: alpha(currentColor, 0.10);
    font-weight: 600;
}

.sadeem-section-heading {
    font-size: 12px;
    font-weight: 700;
    opacity: 0.78;
}

.sadeem-menu-row {
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 34px;
}

.sadeem-menu-subhdr {
    font-weight: 700;
    font-size: 13px;
}

.sadeem-tabular-val {
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    font-weight: 600;
    min-width: 44px;
}

.sadeem-popover-active {
    background-color: alpha(currentColor, 0.10);
    font-weight: 600;
}

.sadeem-step-btn {
    min-width: 26px;
    min-height: 26px;
    padding: 2px 4px;
    border-radius: 999px;
}

.sadeem-tracks-tabs > button {
    min-height: 30px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}

.sadeem-thumb-preview {
    background-color: rgba(15, 16, 20, 0.94);
    color: #f8fafc;
    border-radius: 10px;
    padding: 6px;
}

.sadeem-recent-row {
    border-radius: 10px;
    padding: 6px 10px;
}

.sadeem-recent-progress trough {
    min-height: 3px;
    border-radius: 999px;
    background-color: rgba(255, 255, 255, 0.14);
}
.sadeem-recent-progress progress {
    min-height: 3px;
    border-radius: 999px;
    background-color: #7a1c33;
}
"""


def format_isolated(name: str) -> str:
    if not name:
        return ""
    return f"\u2066{name}\u2069"


def format_time(seconds: float) -> str:
    sec = max(0, int(round(seconds))) if seconds and seconds > 0 else 0
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def make_section_label(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.add_css_class("caption-heading")
    lbl.add_css_class("sadeem-section-heading")
    lbl.set_margin_start(6)
    lbl.set_margin_top(2)
    return lbl


def _make_directional_arrow(entering: bool) -> Gtk.Image:
    """Return a directional chevron image unaffected by theme auto-flipping."""
    is_rtl = Gtk.Widget.get_default_direction() == Gtk.TextDirection.RTL
    if entering:
        icon_name = "go-previous-symbolic" if is_rtl else "go-next-symbolic"
    else:
        icon_name = "go-next-symbolic" if is_rtl else "go-previous-symbolic"
    img = Gtk.Image.new_from_icon_name(icon_name)
    img.set_direction(Gtk.TextDirection.LTR)
    img.set_pixel_size(16)
    return img


def make_subpage_header(title: str, on_back: Callable[[], None]) -> Gtk.Box:
    wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

    back_btn = Gtk.Button()
    back_btn.add_css_class("flat")
    back_btn.set_child(_make_directional_arrow(entering=False))
    back_btn.connect("clicked", lambda *_: on_back())
    hdr.append(back_btn)

    lbl = Gtk.Label(label=title, xalign=0)
    lbl.add_css_class("sadeem-menu-subhdr")
    lbl.set_hexpand(True)
    hdr.append(lbl)

    wrap.append(hdr)
    wrap.append(Gtk.Separator())
    return wrap


def build_check_row(
    label: str,
    selected: bool,
    on_click: Callable[[], None],
    isolate_bidi: bool = False,
) -> Tuple[Gtk.Button, Gtk.Image]:
    b = Gtk.Button()
    b.add_css_class("flat")
    b.add_css_class("sadeem-menu-row")
    if selected:
        b.add_css_class("sadeem-popover-active")
    b.set_halign(Gtk.Align.FILL)

    row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    lbl = Gtk.Label(
        label=format_isolated(label) if isolate_bidi else label,
        xalign=0,
    )
    lbl.set_hexpand(True)
    lbl.set_halign(Gtk.Align.FILL)
    lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    row_box.append(lbl)

    chk_slot = Gtk.Box()
    chk_slot.set_size_request(18, 18)
    chk_slot.set_halign(Gtk.Align.END)
    chk_slot.set_valign(Gtk.Align.CENTER)
    chk = Gtk.Image.new_from_icon_name("object-select-symbolic")
    chk.set_opacity(1.0 if selected else 0.0)
    chk_slot.append(chk)
    row_box.append(chk_slot)

    b.set_child(row_box)
    b.connect("clicked", lambda *_: on_click())
    return b, chk


def build_nav_row(
    icon_name: str,
    title: str,
    on_click: Callable[[], None],
) -> Tuple[Gtk.Button, Gtk.Label]:
    b = Gtk.Button()
    b.add_css_class("flat")
    b.add_css_class("sadeem-menu-row")
    b.set_halign(Gtk.Align.FILL)

    row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    ico = Gtk.Image.new_from_icon_name(icon_name)
    ico.set_pixel_size(16)
    row_box.append(ico)

    title_lbl = Gtk.Label(label=title, xalign=0)
    title_lbl.set_hexpand(True)
    title_lbl.set_halign(Gtk.Align.FILL)
    row_box.append(title_lbl)

    val_lbl = Gtk.Label(label="")
    val_lbl.add_css_class("dim-label")
    val_lbl.add_css_class("caption")
    row_box.append(val_lbl)

    row_box.append(_make_directional_arrow(entering=True))
    b.set_child(row_box)
    b.connect("clicked", lambda *_: on_click())
    return b, val_lbl


def build_action_row(
    icon_name: str,
    title: str,
    on_click: Callable[[], None],
) -> Tuple[Gtk.Button, Gtk.Label]:
    b = Gtk.Button()
    b.add_css_class("flat")
    b.add_css_class("sadeem-menu-row")
    b.set_halign(Gtk.Align.FILL)

    row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    ico = Gtk.Image.new_from_icon_name(icon_name)
    ico.set_pixel_size(16)
    row_box.append(ico)
    lbl = Gtk.Label(label=title, xalign=0)
    lbl.set_hexpand(True)
    row_box.append(lbl)
    b.set_child(row_box)
    b.connect("clicked", lambda *_: on_click())
    return b, lbl


def make_stepper_row(
    title: str,
    initial_text: str,
    on_dec: Callable[[], None],
    on_inc: Callable[[], None],
    on_reset: Callable[[], None],
    icon_name: Optional[str] = None,
) -> Tuple[Gtk.Box, Gtk.Label]:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.set_margin_start(10)
    row.set_margin_end(10)
    row.set_margin_top(4)
    row.set_margin_bottom(4)

    if icon_name:
        ico = Gtk.Image.new_from_icon_name(icon_name)
        ico.set_pixel_size(16)
        row.append(ico)

    lbl = Gtk.Label(label=title, xalign=0)
    lbl.set_hexpand(True)
    lbl.set_ellipsize(Pango.EllipsizeMode.END)
    row.append(lbl)

    ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
    ctrl_box.set_direction(Gtk.TextDirection.LTR)
    ctrl_box.set_valign(Gtk.Align.CENTER)

    dec_btn = Gtk.Button(label="−")
    dec_btn.add_css_class("flat")
    dec_btn.add_css_class("sadeem-step-btn")
    dec_btn.set_valign(Gtk.Align.CENTER)
    dec_btn.connect("clicked", lambda *_: on_dec())

    val_lbl = Gtk.Label(label=initial_text)
    val_lbl.add_css_class("sadeem-tabular-val")
    val_lbl.set_size_request(42, -1)
    val_lbl.set_halign(Gtk.Align.CENTER)

    inc_btn = Gtk.Button(label="+")
    inc_btn.add_css_class("flat")
    inc_btn.add_css_class("sadeem-step-btn")
    inc_btn.set_valign(Gtk.Align.CENTER)
    inc_btn.connect("clicked", lambda *_: on_inc())

    rst_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
    rst_btn.add_css_class("flat")
    rst_btn.add_css_class("circular")
    rst_btn.add_css_class("sadeem-step-btn")
    rst_btn.set_valign(Gtk.Align.CENTER)
    rst_btn.set_tooltip_text(t("reset"))
    rst_btn.connect("clicked", lambda *_: on_reset())

    ctrl_box.append(dec_btn)
    ctrl_box.append(val_lbl)
    ctrl_box.append(inc_btn)
    ctrl_box.append(rst_btn)
    row.append(ctrl_box)
    return row, val_lbl


def make_switch_row(
    title: str,
    on_notify: Callable[[Gtk.Switch, object], None],
    icon_name: Optional[str] = None,
) -> Tuple[Gtk.Box, Gtk.Switch]:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    row.set_margin_start(10)
    row.set_margin_end(10)
    row.set_margin_top(4)
    row.set_margin_bottom(4)

    if icon_name:
        ico = Gtk.Image.new_from_icon_name(icon_name)
        ico.set_pixel_size(16)
        row.append(ico)

    lbl = Gtk.Label(label=title, xalign=0)
    lbl.set_hexpand(True)
    lbl.set_wrap(True)
    sw = Gtk.Switch()
    sw.set_valign(Gtk.Align.CENTER)
    sw.connect("notify::active", on_notify)

    row.append(lbl)
    row.append(sw)
    return row, sw


def set_check_row_state(btn: Gtk.Button, chk: Gtk.Image, active: bool) -> None:
    if active:
        btn.add_css_class("sadeem-popover-active")
        chk.set_opacity(1.0)
    else:
        btn.remove_css_class("sadeem-popover-active")
        chk.set_opacity(0.0)


def _make_page_box(padding: int = 8, spacing: int = 4) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    box.set_margin_top(padding)
    box.set_margin_bottom(padding)
    box.set_margin_start(padding)
    box.set_margin_end(padding)
    return box


# ---------------------------------------------------------------------------
# Audio & Subtitles Popover Builder
# ---------------------------------------------------------------------------
def build_tracks_popover(win) -> Gtk.Popover:
    pop = Gtk.Popover()
    win._register_popover_tracking(pop)
    pop.connect("show", lambda *_: refresh_tracks_popover(win))
    pop.connect("closed", lambda *_: win.tracks_stack.set_visible_child_name("main"))

    win.tracks_stack = Gtk.Stack()
    win.tracks_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
    win.tracks_stack.set_transition_duration(180)
    win.tracks_stack.set_vhomogeneous(False)
    win.tracks_stack.set_size_request(345, -1)
    pop.set_child(win.tracks_stack)

    # ---- Page: main (Clean two-tab switcher: Audio | Subtitles) ----
    main_wrap = _make_page_box(padding=10, spacing=8)

    tab_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    tab_bar.add_css_class("linked")
    tab_bar.add_css_class("sadeem-tracks-tabs")
    tab_bar.set_homogeneous(True)
    tab_bar.set_hexpand(True)

    win.tracks_tab_audio_btn = Gtk.ToggleButton(label=t("tab_audio"))
    win.tracks_tab_audio_btn.set_active(True)
    win.tracks_tab_sub_btn = Gtk.ToggleButton(label=t("tab_subtitles"))
    win.tracks_tab_sub_btn.set_group(win.tracks_tab_audio_btn)
    tab_bar.append(win.tracks_tab_audio_btn)
    tab_bar.append(win.tracks_tab_sub_btn)
    main_wrap.append(tab_bar)

    win.tracks_tab_stack = Gtk.Stack()
    win.tracks_tab_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    win.tracks_tab_stack.set_transition_duration(150)
    win.tracks_tab_stack.set_vhomogeneous(False)
    main_wrap.append(win.tracks_tab_stack)

    def _on_tab_toggled(_btn) -> None:
        if win.tracks_tab_audio_btn.get_active():
            win.tracks_tab_stack.set_visible_child_name("audio_tab")
        elif win.tracks_tab_sub_btn.get_active():
            win.tracks_tab_stack.set_visible_child_name("sub_tab")

    win.tracks_tab_audio_btn.connect("toggled", _on_tab_toggled)
    win.tracks_tab_sub_btn.connect("toggled", _on_tab_toggled)

    # -- Tab 1: Audio --
    aud_scroll = Gtk.ScrolledWindow()
    aud_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    aud_scroll.set_max_content_height(380)
    aud_scroll.set_propagate_natural_height(True)

    aud_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    aud_scroll.set_child(aud_box)

    aud_box.append(make_section_label(t("audio_track")))
    win.audio_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    aud_box.append(win.audio_list_box)

    aud_box.append(Gtk.Separator())

    aud_delay_row, win.audio_delay_lbl = make_stepper_row(
        t("audio_delay"),
        "0.0s",
        lambda: win._adjust_audio_delay(-0.1),
        lambda: win._adjust_audio_delay(0.1),
        lambda: win._set_audio_delay(0.0),
        icon_name="preferences-system-time-symbolic",
    )
    aud_box.append(aud_delay_row)

    night_row, win.night_mode_switch = make_switch_row(
        t("night_mode"),
        win._on_night_mode_toggled,
        icon_name="weather-clear-night-symbolic",
    )
    aud_box.append(night_row)

    aud_eq_nav, win.nav_audio_eq_val = build_nav_row(
        "audio-volume-high-symbolic",
        t("audio_eq"),
        lambda: win.tracks_stack.set_visible_child_name("audio_eq"),
    )
    aud_box.append(aud_eq_nav)

    win.tracks_tab_stack.add_named(aud_scroll, "audio_tab")

    # -- Tab 2: Subtitles --
    sub_scroll = Gtk.ScrolledWindow()
    sub_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sub_scroll.set_max_content_height(400)
    sub_scroll.set_propagate_natural_height(True)

    sub_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    sub_scroll.set_child(sub_box)

    sub_box.append(make_section_label(t("subtitle_track")))
    win.sub_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    sub_box.append(win.sub_list_box)

    sec_sub_nav, win.nav_sec_sub_val = build_nav_row(
        "media-view-subtitles-symbolic",
        t("secondary_sub"),
        lambda: win.tracks_stack.set_visible_child_name("secondary_sub"),
    )
    sub_box.append(sec_sub_nav)

    add_sub_btn, _ = build_action_row(
        "folder-open-symbolic", t("load_subtitle"), lambda: win._on_load_sub_clicked(None)
    )
    sub_box.append(add_sub_btn)

    sub_box.append(Gtk.Separator())

    delay_row, win.sub_delay_lbl = make_stepper_row(
        t("sub_delay"),
        "0.0s",
        lambda: win._adjust_sub_delay(-0.2),
        lambda: win._adjust_sub_delay(0.2),
        lambda: win._set_sub_delay(0.0),
        icon_name="preferences-system-time-symbolic",
    )
    sub_box.append(delay_row)

    scale_row, win.sub_scale_lbl = make_stepper_row(
        t("sub_scale"),
        "1.0x",
        lambda: win._adjust_sub_scale(-0.1),
        lambda: win._adjust_sub_scale(0.1),
        lambda: win._set_sub_scale(1.0),
        icon_name="format-text-larger-symbolic",
    )
    sub_box.append(scale_row)

    bidi_row, win.sub_bidi_switch = make_switch_row(
        t("sub_bidi_compat"),
        win._on_sub_bidi_compat_toggled,
        icon_name="format-text-direction-rtl-symbolic",
    )
    sub_box.append(bidi_row)

    sub_style_nav, win.nav_sub_style_val = build_nav_row(
        "applications-graphics-symbolic",
        t("sub_appearance"),
        lambda: win.tracks_stack.set_visible_child_name("sub_style"),
    )
    sub_box.append(sub_style_nav)

    win.tracks_tab_stack.add_named(sub_scroll, "sub_tab")
    win.tracks_tab_stack.set_visible_child_name("audio_tab")

    win.tracks_stack.add_named(main_wrap, "main")

    # ---- Page: audio_eq ----
    eq_page = _make_page_box(padding=8, spacing=4)
    eq_page.append(
        make_subpage_header(t("audio_eq"), lambda: win.tracks_stack.set_visible_child_name("main"))
    )
    win._audio_eq_buttons = {}
    for preset_id, lbl_key in (
        ("normal", "eq_preset_normal"),
        ("voice", "eq_preset_voice"),
        ("cinema", "eq_preset_cinema"),
        ("music", "eq_preset_music"),
    ):
        b, chk = build_check_row(
            t(lbl_key), False, lambda pid=preset_id: win.set_audio_eq_preset(pid)
        )
        win._audio_eq_buttons[preset_id] = (b, chk)
        eq_page.append(b)
    win.tracks_stack.add_named(eq_page, "audio_eq")

    # ---- Page: secondary_sub ----
    sec_page = _make_page_box(padding=8, spacing=4)
    sec_page.append(
        make_subpage_header(t("secondary_sub"), lambda: win.tracks_stack.set_visible_child_name("main"))
    )
    sec_scroll = Gtk.ScrolledWindow()
    sec_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sec_scroll.set_max_content_height(300)
    sec_scroll.set_propagate_natural_height(True)
    win.sec_sub_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    sec_scroll.set_child(win.sec_sub_list_box)
    sec_page.append(sec_scroll)
    win.tracks_stack.add_named(sec_page, "secondary_sub")

    # ---- Page: sub_style ----
    style_page = _make_page_box(padding=8, spacing=6)
    style_page.append(
        make_subpage_header(t("sub_appearance"), lambda: win.tracks_stack.set_visible_child_name("main"))
    )

    pos_row, win.sub_pos_lbl = make_stepper_row(
        t("sub_pos"),
        "100%",
        lambda: win._adjust_sub_pos(-5),
        lambda: win._adjust_sub_pos(5),
        lambda: win.set_sub_pos(100),
        icon_name="go-up-symbolic",
    )
    style_page.append(pos_row)

    style_page.append(make_section_label(t("sub_color")))
    win._sub_color_buttons = {}
    for hex_val, lbl_key in (
        ("#FFFFFF", "color_white"),
        ("#FACC15", "color_yellow"),
        ("#CBD5E1", "color_silver"),
    ):
        b, chk = build_check_row(t(lbl_key), False, lambda c=hex_val: win.set_sub_color(c))
        win._sub_color_buttons[hex_val] = (b, chk)
        style_page.append(b)

    back_box_row, win.sub_back_box_switch = make_switch_row(
        t("sub_back_box"),
        win._on_sub_back_box_toggled,
        icon_name="media-view-subtitles-symbolic",
    )
    style_page.append(back_box_row)

    style_page.append(make_section_label(t("sub_font")))
    win._sub_font_buttons = {}
    for font_val, label in (
        ("", t("font_default")),
        ("Noto Sans Arabic", "Noto Sans Arabic"),
        ("Amiri", "Amiri"),
        ("Vazirmatn", "Vazirmatn"),
    ):
        b, chk = build_check_row(label, False, lambda fn=font_val: win.set_sub_font(fn), isolate_bidi=True)
        win._sub_font_buttons[font_val] = (b, chk)
        style_page.append(b)

    win.tracks_stack.add_named(style_page, "sub_style")

    return pop


def refresh_tracks_popover(win) -> None:
    for container in (win.audio_list_box, win.sub_list_box, win.sec_sub_list_box):
        while True:
            child = container.get_first_child()
            if child is None:
                break
            container.remove(child)

    tracks = win.engine.get_tracks() if win.engine.is_initialized else {"audio": [], "sub": []}
    audio_tracks = tracks["audio"]
    sub_tracks = tracks["sub"]

    if not audio_tracks:
        lbl = Gtk.Label(label=t("info_none"), xalign=0)
        lbl.add_css_class("dim-label")
        lbl.set_margin_start(8)
        lbl.set_margin_top(4)
        lbl.set_margin_bottom(4)
        win.audio_list_box.append(lbl)
    else:
        for tr in audio_tracks:
            title = tr.get("title") or tr.get("lang") or t("track_untitled", id=tr["id"])
            if tr.get("lang") and tr.get("title"):
                title = f"{tr['title']} ({tr['lang']})"
            b, _ = build_check_row(
                title,
                bool(tr.get("selected")),
                lambda tid=tr["id"]: (win.engine.set_audio_track(tid), win.tracks_popover.popdown()),
                isolate_bidi=True,
            )
            win.audio_list_box.append(b)

    # Primary subtitle tracks
    primary_sid = next((s["id"] for s in sub_tracks if s.get("selected")), 0)
    off_btn, _ = build_check_row(
        t("sub_off"),
        primary_sid == 0,
        lambda: (win.engine.set_subtitle_track(None), win.tracks_popover.popdown()),
    )
    win.sub_list_box.append(off_btn)

    for tr in sub_tracks:
        title = tr.get("title") or tr.get("lang") or t("track_untitled", id=tr["id"])
        if tr.get("lang") and tr.get("title"):
            title = f"{tr['title']} ({tr['lang']})"
        b, _ = build_check_row(
            title,
            bool(tr.get("selected")),
            lambda tid=tr["id"]: (win.engine.set_subtitle_track(tid), win.tracks_popover.popdown()),
            isolate_bidi=True,
        )
        win.sub_list_box.append(b)

    # Secondary subtitle tracks (for Top display)
    sec_sid = win.engine.get_secondary_subtitle_id() if win.engine.is_initialized else 0
    sec_off, _ = build_check_row(
        t("sub_off"),
        sec_sid == 0,
        lambda: (win.engine.set_secondary_subtitle_track(None), refresh_tracks_popover(win)),
    )
    win.sec_sub_list_box.append(sec_off)
    sec_active_title = t("sub_off")

    for tr in sub_tracks:
        if tr["id"] == primary_sid:
            continue
        title = tr.get("title") or tr.get("lang") or t("track_untitled", id=tr["id"])
        if tr.get("lang") and tr.get("title"):
            title = f"{tr['title']} ({tr['lang']})"
        is_sec = tr["id"] == sec_sid
        if is_sec:
            sec_active_title = title
        b, _ = build_check_row(
            title,
            is_sec,
            lambda tid=tr["id"]: (win.engine.set_secondary_subtitle_track(tid), refresh_tracks_popover(win)),
            isolate_bidi=True,
        )
        win.sec_sub_list_box.append(b)

    win.nav_sec_sub_val.set_text(sec_active_title)
    sync_tracks_active_states(win)


def sync_tracks_active_states(win) -> None:
    preset_key = f"eq_preset_{win._audio_eq_preset}"
    win.nav_audio_eq_val.set_text(t(preset_key))
    for pid, (btn, chk) in win._audio_eq_buttons.items():
        set_check_row_state(btn, chk, pid == win._audio_eq_preset)

    win.sub_pos_lbl.set_text(f"{win._sub_pos_val}%")
    win.nav_sub_style_val.set_text(f"{win._sub_pos_val}%")
    for col, (btn, chk) in win._sub_color_buttons.items():
        set_check_row_state(btn, chk, col.upper() == win._sub_color_val.upper())
    for fn, (btn, chk) in win._sub_font_buttons.items():
        set_check_row_state(btn, chk, fn == win._sub_font_val)


# ---------------------------------------------------------------------------
# Settings Popover Builder (Gtk.Stack sliding pages)
# ---------------------------------------------------------------------------
def build_settings_popover(win) -> Gtk.Popover:
    pop = Gtk.Popover()
    win._register_popover_tracking(pop)
    pop.connect("show", lambda *_: (sync_settings_active_states(win), refresh_chapters_section(win)))
    pop.connect("closed", lambda *_: win.settings_stack.set_visible_child_name("main"))

    win.settings_stack = Gtk.Stack()
    win.settings_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
    win.settings_stack.set_transition_duration(180)
    win.settings_stack.set_vhomogeneous(False)
    win.settings_stack.set_size_request(310, -1)
    pop.set_child(win.settings_stack)

    # ---- Page: main ----
    main_page = _make_page_box(padding=8, spacing=4)
    spd_nav, win.nav_speed_val = build_nav_row(
        "media-seek-forward-symbolic", t("speed"),
        lambda: win.settings_stack.set_visible_child_name("speed"),
    )
    rep_nav, win.nav_repeat_val = build_nav_row(
        "media-playlist-repeat-symbolic", t("loop_mode"),
        lambda: win.settings_stack.set_visible_child_name("repeat"),
    )
    vid_nav, win.nav_video_val = build_nav_row(
        "video-display-symbolic", t("aspect_ratio"),
        lambda: win.settings_stack.set_visible_child_name("video"),
    )
    res_nav, win.nav_resume_val = build_nav_row(
        "media-playback-start-symbolic", t("resume_mode"),
        lambda: win.settings_stack.set_visible_child_name("resume"),
    )
    eq_nav, _ = build_nav_row(
        "applications-graphics-symbolic", t("eq_title"),
        lambda: win.settings_stack.set_visible_child_name("eq"),
    )
    win.chapters_nav_btn, win.nav_chapters_val = build_nav_row(
        "view-list-symbolic", t("chapters"),
        lambda: win.settings_stack.set_visible_child_name("chapters"),
    )
    win.chapters_nav_btn.set_visible(False)

    for w in (spd_nav, rep_nav, vid_nav, res_nav, eq_nav, win.chapters_nav_btn):
        main_page.append(w)

    sep = Gtk.Separator()
    sep.set_margin_top(2)
    sep.set_margin_bottom(2)
    main_page.append(sep)

    skip_btn, _ = build_action_row(
        "media-skip-forward-symbolic",
        t("skip_intro"),
        lambda: (win.settings_popover.popdown(), win.skip_intro(85.0)),
    )
    main_page.append(skip_btn)

    mini_btn, win.mini_mode_row_lbl = build_action_row(
        "view-restore-symbolic",
        t("mini_mode"),
        lambda: (win.settings_popover.popdown(), win.toggle_mini_mode()),
    )
    main_page.append(mini_btn)

    ss_btn, _ = build_action_row(
        "camera-photo-symbolic",
        t("screenshot"),
        lambda: (win.settings_popover.popdown(), win.take_screenshot()),
    )
    main_page.append(ss_btn)

    url_btn, _ = build_action_row(
        "globe-symbolic",
        t("open_url"),
        lambda: (win.settings_popover.popdown(), win.prompt_open_url()),
    )
    main_page.append(url_btn)

    sc_btn, _ = build_action_row(
        "preferences-desktop-keyboard-shortcuts-symbolic",
        t("shortcuts_title"),
        lambda: (win.settings_popover.popdown(), win.show_shortcuts_dialog()),
    )
    main_page.append(sc_btn)

    sep2 = Gtk.Separator()
    sep2.set_margin_top(2)
    sep2.set_margin_bottom(2)
    main_page.append(sep2)

    pmin_row, win.pause_on_min_switch = make_switch_row(
        t("pause_on_minimize"),
        win._on_pause_on_minimize_toggled,
        icon_name="window-minimize-symbolic",
    )
    main_page.append(pmin_row)

    win.settings_stack.add_named(main_page, "main")

    # ---- Page: speed ----
    spd_page = _make_page_box(padding=8, spacing=4)
    spd_page.append(make_subpage_header(t("speed"), lambda: win.settings_stack.set_visible_child_name("main")))
    win._speed_buttons = {}
    for s in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
        b, chk = build_check_row(f"{s:g}x", False, lambda val=s: win.set_speed(val))
        win._speed_buttons[float(s)] = (b, chk)
        spd_page.append(b)
    win.settings_stack.add_named(spd_page, "speed")

    # ---- Page: repeat ----
    rep_page = _make_page_box(padding=8, spacing=4)
    rep_page.append(make_subpage_header(t("loop_mode"), lambda: win.settings_stack.set_visible_child_name("main")))
    win._loop_buttons = {}
    for mode_id, lbl_key in (("off", "loop_off"), ("file", "loop_file"), ("playlist", "loop_playlist")):
        b, chk = build_check_row(t(lbl_key), False, lambda m=mode_id: win.set_loop_mode(m))
        win._loop_buttons[mode_id] = (b, chk)
        rep_page.append(b)

    rep_sep = Gtk.Separator()
    rep_sep.set_margin_top(4)
    rep_sep.set_margin_bottom(4)
    rep_page.append(rep_sep)
    rep_page.append(make_section_label(t("ab_loop")))
    win._ab_buttons = {}
    for action, lbl_key in (("a", "ab_set_a"), ("b", "ab_set_b"), ("clear", "ab_clear")):
        b, chk = build_check_row(t(lbl_key), False, lambda act=action: win._on_ab_action(act))
        win._ab_buttons[action] = (b, chk)
        rep_page.append(b)
    win.settings_stack.add_named(rep_page, "repeat")

    # ---- Page: video (Aspect, Rotation, Zoom, Panscan) ----
    vid_scroll = Gtk.ScrolledWindow()
    vid_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    vid_scroll.set_max_content_height(460)
    vid_scroll.set_propagate_natural_height(True)

    vid_page = _make_page_box(padding=8, spacing=4)
    vid_scroll.set_child(vid_page)
    vid_page.append(make_subpage_header(t("aspect_ratio"), lambda: win.settings_stack.set_visible_child_name("main")))

    win._aspect_buttons = {}
    for mode, label in (
        ("auto", t("aspect_auto")),
        ("16:9", "16:9"),
        ("4:3", "4:3"),
        ("21:9", "21:9"),
        ("fill", t("aspect_fill")),
    ):
        b, chk = build_check_row(label, False, lambda m=mode: win._set_aspect(m))
        win._aspect_buttons[mode] = (b, chk)
        vid_page.append(b)

    vid_page.append(Gtk.Separator())
    vid_page.append(make_section_label(t("rotation")))
    win._rotation_buttons = {}
    for deg in (0, 90, 180, 270):
        b, chk = build_check_row(f"{deg}°", False, lambda d=deg: win._set_rotation(d))
        win._rotation_buttons[deg] = (b, chk)
        vid_page.append(b)

    vid_page.append(Gtk.Separator())
    zoom_row, win.zoom_val_lbl = make_stepper_row(
        t("video_zoom"),
        "0.00",
        lambda: win._adjust_video_zoom(-0.05),
        lambda: win._adjust_video_zoom(0.05),
        lambda: win.set_video_zoom(0.0),
        icon_name="zoom-in-symbolic",
    )
    vid_page.append(zoom_row)

    panscan_row, win.panscan_switch = make_switch_row(
        t("panscan_crop"),
        win._on_panscan_toggled,
        icon_name="view-fullscreen-symbolic",
    )
    vid_page.append(panscan_row)

    reset_view_btn, _ = build_action_row("edit-undo-symbolic", t("reset_view"), win.reset_video_view)
    vid_page.append(reset_view_btn)
    win.settings_stack.add_named(vid_scroll, "video")

    # ---- Page: resume ----
    res_page = _make_page_box(padding=8, spacing=4)
    res_page.append(make_subpage_header(t("resume_mode"), lambda: win.settings_stack.set_visible_child_name("main")))
    win._resume_buttons = {}
    for mode_id, lbl_key in (("ask", "resume_ask"), ("auto", "resume_auto"), ("never", "resume_never")):
        b, chk = build_check_row(t(lbl_key), False, lambda m=mode_id: win.set_resume_mode(m))
        win._resume_buttons[mode_id] = (b, chk)
        res_page.append(b)
    win.settings_stack.add_named(res_page, "resume")

    # ---- Page: eq (Picture Equalizer) ----
    eq_page = _make_page_box(padding=8, spacing=8)
    eq_page.append(make_subpage_header(t("eq_title"), lambda: win.settings_stack.set_visible_child_name("main")))
    win.eq_scales = {}
    win._eq_value_labels = {}
    for prop_key, label_key in (
        ("brightness", "eq_brightness"),
        ("contrast", "eq_contrast"),
        ("saturation", "eq_saturation"),
        ("gamma", "eq_gamma"),
    ):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_start(4)
        row.set_margin_end(4)
        lbl = Gtk.Label(label=t(label_key), xalign=0)
        lbl.set_size_request(72, -1)
        adj = Gtk.Adjustment(value=0.0, lower=-100.0, upper=100.0, step_increment=2.0, page_increment=10.0)
        sc = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        sc.set_direction(Gtk.TextDirection.LTR)
        sc.set_draw_value(False)
        sc.set_hexpand(True)
        val_lbl = Gtk.Label(label="0")
        val_lbl.add_css_class("sadeem-tabular-val")
        val_lbl.set_size_request(32, -1)
        sc.connect("value-changed", win._on_eq_changed, prop_key)
        win.eq_scales[prop_key] = sc
        win._eq_value_labels[prop_key] = val_lbl
        row.append(lbl)
        row.append(sc)
        row.append(val_lbl)
        eq_page.append(row)

    eq_reset_btn = Gtk.Button(label=t("eq_reset"))
    eq_reset_btn.add_css_class("flat")
    eq_reset_btn.add_css_class("sadeem-menu-row")
    eq_reset_btn.set_halign(Gtk.Align.END)
    eq_reset_btn.connect("clicked", lambda *_: win._reset_equalizer())
    eq_page.append(eq_reset_btn)
    win.settings_stack.add_named(eq_page, "eq")

    # ---- Page: chapters ----
    ch_page = _make_page_box(padding=8, spacing=4)
    ch_page.append(make_subpage_header(t("chapters"), lambda: win.settings_stack.set_visible_child_name("main")))
    ch_scroll = Gtk.ScrolledWindow()
    ch_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    ch_scroll.set_max_content_height(320)
    ch_scroll.set_propagate_natural_height(True)
    win.chapters_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    ch_scroll.set_child(win.chapters_section)
    ch_page.append(ch_scroll)
    win.settings_stack.add_named(ch_page, "chapters")

    return pop


def refresh_chapters_section(win) -> None:
    while True:
        child = win.chapters_section.get_first_child()
        if child is None:
            break
        win.chapters_section.remove(child)

    if not win.engine.is_initialized:
        win.chapters_nav_btn.set_visible(False)
        return
    chapters = win.engine.get_chapters()
    if not chapters:
        win.chapters_nav_btn.set_visible(False)
        return
    cur_ch = win.engine.get_current_chapter()
    win.chapters_nav_btn.set_visible(True)
    win.nav_chapters_val.set_text(str(len(chapters)))
    for ch in chapters[:40]:
        title = ch["title"] or f"{t('chapters')} {ch['index'] + 1}"
        b, _ = build_check_row(
            f"{format_time(ch['time'])}  {title}",
            ch["index"] == cur_ch,
            lambda ts=ch["time"]: (win.engine.seek_absolute(ts), win.settings_popover.popdown()),
            isolate_bidi=True,
        )
        win.chapters_section.append(b)


def sync_settings_active_states(win) -> None:
    win.nav_speed_val.set_text(f"{win._current_speed:g}x")
    loop_key = "loop_file" if win._loop_mode == "file" else ("loop_playlist" if win._loop_mode == "playlist" else "loop_off")
    win.nav_repeat_val.set_text(t(loop_key))

    asp_lbl = t("aspect_auto") if win._current_aspect == "auto" else (t("aspect_fill") if win._current_aspect == "fill" else win._current_aspect)
    win.nav_video_val.set_text(f"{asp_lbl} · {win._current_rotation}°" if win._current_rotation else asp_lbl)

    res_key = f"resume_{win._resume_mode}"
    win.nav_resume_val.set_text(t(res_key))

    win.zoom_val_lbl.set_text(f"{win._video_zoom:+.2f}" if abs(win._video_zoom) >= 0.01 else "0.00")
    win.mini_mode_row_lbl.set_text(t("exit_mini_mode") if win._is_mini_mode else t("mini_mode"))

    for spd, (btn, chk) in win._speed_buttons.items():
        set_check_row_state(btn, chk, abs(spd - win._current_speed) < 0.01)

    for mode_id, (btn, chk) in win._loop_buttons.items():
        set_check_row_state(btn, chk, mode_id == win._loop_mode)

    if "a" in win._ab_buttons:
        set_check_row_state(*win._ab_buttons["a"], win._ab_point_a is not None)
    if "b" in win._ab_buttons:
        set_check_row_state(*win._ab_buttons["b"], win._ab_point_b is not None)
    if "clear" in win._ab_buttons:
        set_check_row_state(*win._ab_buttons["clear"], False)

    for mode, (btn, chk) in win._aspect_buttons.items():
        set_check_row_state(btn, chk, mode == win._current_aspect)

    for deg, (btn, chk) in win._rotation_buttons.items():
        set_check_row_state(btn, chk, deg == win._current_rotation)

    for rmode, (btn, chk) in win._resume_buttons.items():
        set_check_row_state(btn, chk, rmode == win._resume_mode)


# ---------------------------------------------------------------------------
# Welcome Overlay + Dialogs (Open URL, Media Info, Keyboard Shortcuts)
# ---------------------------------------------------------------------------
def build_welcome_overlay(win) -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)
    box.add_css_class("sadeem-welcome-card")

    icon = Gtk.Image.new_from_icon_name("sadeem-video")
    icon.set_pixel_size(72)
    box.append(icon)

    title = Gtk.Label(label=t("app_title"))
    title.add_css_class("title-1")
    box.append(title)

    sub = Gtk.Label(label=t("open_prompt"))
    sub.add_css_class("dim-label")
    sub.set_wrap(True)
    sub.set_justify(Gtk.Justification.CENTER)
    box.append(sub)

    if win.engine_error:
        err_lbl = Gtk.Label(label=f"{t('err_mpv_missing')}\n({win.engine_error})")
        err_lbl.add_css_class("error")
        err_lbl.set_wrap(True)
        err_lbl.set_justify(Gtk.Justification.CENTER)
        box.append(err_lbl)

    btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_row.set_halign(Gtk.Align.CENTER)

    open_btn = Gtk.Button(label=t("open_file"))
    open_btn.add_css_class("suggested-action")
    open_btn.add_css_class("pill")
    open_btn.connect("clicked", lambda *_: win.prompt_open_file())
    btn_row.append(open_btn)

    win.open_url_welcome_btn = Gtk.Button(label=t("open_url_btn"))
    win.open_url_welcome_btn.add_css_class("pill")
    win.open_url_welcome_btn.set_tooltip_text(f"{t('open_url_btn')} (Ctrl+U)")
    win.open_url_welcome_btn.connect("clicked", lambda *_: win.prompt_open_url())
    btn_row.append(win.open_url_welcome_btn)
    box.append(btn_row)

    hint = Gtk.Label(label=t("drop_hint"))
    hint.add_css_class("caption")
    hint.add_css_class("dim-label")
    box.append(hint)

    win.recent_section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    win.recent_section_box.set_margin_top(6)
    win.recent_section_box.set_size_request(340, -1)
    win.recent_section_box.set_visible(False)

    rec_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    rec_lbl = Gtk.Label(label=t("recent_videos"), xalign=0)
    rec_lbl.add_css_class("caption-heading")
    rec_lbl.add_css_class("sadeem-section-heading")
    rec_lbl.set_hexpand(True)
    rec_hdr.append(rec_lbl)

    clear_rec_btn = Gtk.Button(label=t("clear_history"))
    clear_rec_btn.add_css_class("flat")
    clear_rec_btn.add_css_class("caption")
    clear_rec_btn.connect("clicked", win._on_clear_recent_clicked)
    rec_hdr.append(clear_rec_btn)
    win.recent_section_box.append(rec_hdr)

    win.recent_rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    win.recent_section_box.append(win.recent_rows_box)
    box.append(win.recent_section_box)

    refresh_welcome_recent(win)
    return box


def refresh_welcome_recent(win) -> None:
    while True:
        child = win.recent_rows_box.get_first_child()
        if child is None:
            break
        win.recent_rows_box.remove(child)

    items = win.state_store.get_recent_files(existing_only=True, limit=5)
    if not items:
        win.recent_section_box.set_visible(False)
        return

    win.recent_section_box.set_visible(True)
    for entry in items:
        path = str(entry.get("path", ""))
        pos = float(entry.get("pos", 0.0))
        dur = float(entry.get("duration", 0.0))
        is_url = playlist.is_network_url(path)
        disp_name = path if is_url else os.path.basename(path)

        row_btn = Gtk.Button()
        row_btn.add_css_class("flat")
        row_btn.add_css_class("sadeem-recent-row")
        row_btn.set_hexpand(True)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ico = Gtk.Image.new_from_icon_name("globe-symbolic" if is_url else "video-x-generic-symbolic")
        ico.set_pixel_size(16)
        top_line.append(ico)

        name_lbl = Gtk.Label(label=format_isolated(disp_name), xalign=0)
        name_lbl.set_hexpand(True)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        name_lbl.set_max_width_chars(32)
        top_line.append(name_lbl)

        if dur > 0.0:
            t_lbl = Gtk.Label(label=f"{format_time(pos)} / {format_time(dur)}")
            t_lbl.add_css_class("dim-label")
            t_lbl.add_css_class("sadeem-tabular-val")
            top_line.append(t_lbl)
        vbox.append(top_line)

        if dur > 0.0:
            pbar = Gtk.ProgressBar()
            pbar.add_css_class("sadeem-recent-progress")
            pbar.set_fraction(max(0.0, min(1.0, pos / dur)))
            vbox.append(pbar)

        row_btn.set_child(vbox)
        if is_url:
            row_btn.connect("clicked", lambda _b, u=path: win.open_url(u))
        else:
            row_btn.connect("clicked", lambda _b, p=path: win.open_paths([p]))
        win.recent_rows_box.append(row_btn)


def prompt_open_url(win):
    entry = Gtk.Entry()
    entry.set_placeholder_text(t("open_url_placeholder"))
    entry.set_activates_default(True)
    entry.set_hexpand(True)
    ui_dir = getattr(win, "_ui_direction", Gtk.Widget.get_default_direction())

    if hasattr(Adw, "AlertDialog"):
        dlg = Adw.AlertDialog(heading=t("open_url_title"), body=t("open_url_hint"))
        dlg.set_direction(ui_dir)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", t("cancel"))
        dlg.add_response("open", t("open_url_action"))
        dlg.set_response_appearance("open", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("open")
        dlg.set_close_response("cancel")
        dlg.connect("response", lambda _d, resp: win.open_url(entry.get_text()) if resp == "open" else None)
        dlg.present(win)
        return dlg
    else:
        dlg = Adw.MessageDialog(
            transient_for=win,
            modal=True,
            heading=t("open_url_title"),
            body=t("open_url_hint"),
        )
        dlg.set_direction(ui_dir)
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", t("cancel"))
        dlg.add_response("open", t("open_url_action"))
        dlg.set_response_appearance("open", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("open")
        dlg.connect("response", lambda _d, resp: win.open_url(entry.get_text()) if resp == "open" else None)
        dlg.present()
        return dlg


def present_adw_dialog(win, title: str, content: Gtk.Widget, width: int = 440, height: int = 500):
    ui_dir = getattr(win, "_ui_direction", Gtk.Widget.get_default_direction())
    if hasattr(Adw, "Dialog"):
        dlg = Adw.Dialog()
        dlg.set_direction(ui_dir)
        dlg.set_title(title)
        dlg.set_content_width(width)
        dlg.set_content_height(height)
        dlg.set_child(content)
        dlg.present(win)
        return dlg
    dlg = Adw.Window(transient_for=win, modal=True, title=title)
    dlg.set_direction(ui_dir)
    dlg.set_default_size(width, height)
    dlg.set_content(content)
    dlg.present()
    return dlg


def format_file_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    val = float(num_bytes)
    for unit in ("KB", "MB", "GB", "TB"):
        val /= 1024.0
        if val < 1024.0:
            return f"{val:.1f} {unit}"
    return f"{val:.1f} PB"


def build_media_info_page(win) -> Gtk.Widget:
    info = win.engine.get_media_info() if win.engine.is_initialized else {
        "width": 0, "height": 0, "fps": 0.0, "video_codec": "", "audio_codec": "",
        "audio_channels": 0, "audio_channels_layout": "", "hwdec_current": "no",
        "duration": 0.0, "audio_tracks": [], "sub_tracks": [], "chapters": [],
    }

    tv = Adw.ToolbarView()
    hb = Adw.HeaderBar()
    hb.set_title_widget(Adw.WindowTitle(title=t("media_info"), subtitle=""))
    tv.add_top_bar(hb)

    pref_page = Adw.PreferencesPage()
    grp = Adw.PreferencesGroup()
    pref_page.add(grp)

    res_str = f"{info['width']} × {info['height']}" if info["width"] and info["height"] else t("info_none")
    fps_str = f"{info['fps']:.2f} fps" if info["fps"] else t("info_none")

    ch_cnt = int(info.get("audio_channels") or 0)
    ch_lay = str(info.get("audio_channels_layout") or "")
    if ch_cnt and ch_lay:
        ch_str = f"{ch_cnt} ({ch_lay})"
    elif ch_cnt:
        ch_str = str(ch_cnt)
    elif ch_lay:
        ch_str = ch_lay
    else:
        ch_str = t("info_none")

    aud_str = ", ".join(
        (a.get("title") or a.get("lang") or a.get("codec") or str(a.get("id")))
        for a in info.get("audio_tracks", [])
    ) or t("info_none")
    sub_str = ", ".join(
        (s.get("title") or s.get("lang") or str(s.get("id")))
        for s in info.get("sub_tracks", [])
    ) or t("info_none")

    cur = win.playlist_mgr.current_path or ""
    if cur and not playlist.is_network_url(cur) and os.path.isfile(cur):
        try:
            size_str = format_file_size(os.path.getsize(cur))
        except OSError:
            size_str = t("info_none")
    else:
        size_str = t("info_none")
    path_str = format_isolated(cur) if cur else t("info_none")

    rows = [
        (t("info_resolution"), res_str),
        (t("info_codec"), info.get("video_codec") or t("info_none")),
        (t("info_audio_codec"), info.get("audio_codec") or t("info_none")),
        (t("info_audio_channels"), ch_str),
        (t("info_fps"), fps_str),
        (t("info_hwdec"), info.get("hwdec_current") or "no"),
        (t("info_duration"), format_time(info.get("duration", 0.0))),
        (t("info_chapters_count"), str(len(info.get("chapters", [])))),
        (t("info_audio_tracks"), aud_str),
        (t("info_sub_tracks"), sub_str),
        (t("info_file_size"), size_str),
        (t("info_file_path"), path_str),
    ]
    for label, val in rows:
        row = Adw.ActionRow(title=label, subtitle=str(val))
        row.set_subtitle_selectable(True)
        grp.add(row)

    tv.set_content(pref_page)
    return tv


def build_shortcuts_page() -> Gtk.Widget:
    tv = Adw.ToolbarView()
    hb = Adw.HeaderBar()
    hb.set_title_widget(Adw.WindowTitle(title=t("shortcuts_title"), subtitle=""))
    tv.add_top_bar(hb)

    pref_page = Adw.PreferencesPage()
    groups_spec = (
        (
            t("shortcuts_group_playback"),
            (
                (t("sc_play_pause"), "space k"),
                (t("sc_seek_5"), "Left Right"),
                (t("sc_seek_30"), "<Control>Left <Control>Right"),
                (t("sc_skip_intro"), "<Shift>Left <Shift>Right"),
                (t("sc_frame_step"), "comma period"),
                (t("sc_speed"), "bracketleft bracketright"),
                (t("sc_ab_loop"), "l"),
                (t("sc_prev_next"), "Page_Up Page_Down"),
            ),
        ),
        (
            t("shortcuts_group_audio_sub"),
            (
                (t("sc_volume"), "Up Down"),
                (t("sc_mute"), "m"),
                (t("sc_sub_toggle"), "v"),
                (t("sc_audio_cycle"), "a"),
            ),
        ),
        (
            t("shortcuts_group_view"),
            (
                (t("sc_fullscreen"), "f F11"),
                (t("sc_mini_mode"), "<Alt>m"),
                (t("sc_hud"), "h"),
                (t("sc_reset_view"), "BackSpace"),
            ),
        ),
        (
            t("shortcuts_group_files"),
            (
                (t("sc_open_file"), "<Control>o"),
                (t("sc_open_url"), "<Control>u"),
                (t("sc_playlist"), "p"),
                (t("sc_screenshot"), "s"),
                (t("sc_media_info"), "i"),
                (t("sc_shortcuts"), "question F1"),
            ),
        ),
    )
    for grp_title, entries in groups_spec:
        grp = Adw.PreferencesGroup(title=grp_title)
        for desc, accel in entries:
            row = Adw.ActionRow(title=desc)
            sc_lbl = Gtk.ShortcutLabel.new(accel)
            sc_lbl.set_valign(Gtk.Align.CENTER)
            row.add_suffix(sc_lbl)
            grp.add(row)
        pref_page.add(grp)

    tv.set_content(pref_page)
    return tv
