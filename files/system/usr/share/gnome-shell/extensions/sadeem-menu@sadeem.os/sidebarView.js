// sidebarView.js - Collapsible All Apps Sidebar & Alphabet Jump Grid
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as I18n from './i18n.js';
import * as TileLayout from './tileLayout.js';

const LATIN_LETTERS = [
    '#', '0-9', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H',
    'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
    'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
];

const ARABIC_LETTERS = [
    'أ', 'ب', 'ت', 'ث', 'ج', 'ح', 'خ', 'د',
    'ذ', 'ر', 'ز', 'س', 'ش', 'ص', 'ض', 'ط',
    'ظ', 'ع', 'غ', 'ف', 'ق', 'ك', 'ل', 'م',
    'ن', 'ه', 'و', 'ي',
];

function getAppGicon(appRecord) {
    try {
        const icon = appRecord?.appInfo?.get_icon?.();
        if (icon)
            return icon;
    } catch (_e) {}
    return Gio.Icon.new_for_string('application-x-executable');
}

function normalizeLetterBucket(name) {
    const ch = (name || '#').trim().charAt(0).toUpperCase() || '#';
    if (/[0-9]/.test(ch))
        return '0-9';
    if (ch === 'ا' || ch === 'إ' || ch === 'آ')
        return 'أ';
    if (ch === 'ة')
        return 'ت';
    if (ch === 'ى')
        return 'ي';
    if (/[A-Z]/.test(ch) || /[\u0621-\u064A]/.test(ch))
        return ch;
    return '#';
}

export class SidebarView extends St.ScrollView {
    static {
        GObject.registerClass(this);
    }

    constructor() {
        const list = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-menu-sidebar-list',
            x_expand: true,
        });
        super({
            style_class: 'sadeem-menu-sidebar-scroll',
            overlay_scrollbars: true,
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            enable_mouse_scrolling: true,
            x_expand: false,
            y_expand: true,
            child: list,
        });
        this.clip_to_allocation = true;
        this.set_width(TileLayout.SIDEBAR_WIDTH);
        this.style = `width: ${TileLayout.SIDEBAR_WIDTH}px; min-width: ${TileLayout.SIDEBAR_WIDTH}px; max-width: ${TileLayout.SIDEBAR_WIDTH}px; min-height: 0px;`;

        this._list = list;
        this._mode = 'list';
        this._letterAnchors = new Map();
        this._scrollIdleId = null;
    }

    get mode() {
        return this._mode;
    }

    resetMode() {
        this._mode = 'list';
    }

    render(records, { show, isRtl, onLaunchApp, onAppContext, dragManager = null }) {
        this._list.destroy_all_children();
        this._letterAnchors.clear();
        this.visible = Boolean(show);
        if (!show)
            return;

        const sorted = records.slice().sort((a, b) => a.name.localeCompare(b.name));
        const buckets = new Map();
        for (const rec of sorted) {
            const letter = normalizeLetterBucket(rec.name);
            if (!buckets.has(letter))
                buckets.set(letter, []);
            buckets.get(letter).push(rec);
        }

        if (this._mode === 'jump') {
            this._renderJumpGrid(buckets, isRtl, () => this.render(records, { show, isRtl, onLaunchApp, onAppContext, dragManager }));
            return;
        }

        this._list.add_child(new St.Label({
            text: I18n.t('all_apps'),
            style_class: 'sadeem-menu-letter-header',
            style: 'padding: 2px 8px 6px 8px;',
            reactive: false,
        }));

        const preferredOrder = isRtl
            ? [...ARABIC_LETTERS, ...LATIN_LETTERS]
            : [...LATIN_LETTERS, ...ARABIC_LETTERS];

        const ordered = [];
        for (const l of preferredOrder) {
            if (buckets.has(l))
                ordered.push(l);
        }
        for (const l of buckets.keys()) {
            if (!ordered.includes(l))
                ordered.push(l);
        }

        ordered.forEach((letter, idx) => {
            const letterLbl = new St.Label({
                text: letter,
                style_class: 'sadeem-menu-letter-header',
                x_expand: true,
                x_align: Clutter.ActorAlign.START,
                reactive: false,
            });
            const letterBtn = new St.Button({
                style_class: idx === 0 ? 'sadeem-menu-letter-btn sadeem-menu-letter-btn-first' : 'sadeem-menu-letter-btn',
                can_focus: true,
                reactive: true,
                x_expand: true,
                child: letterLbl,
            });
            letterBtn.connect('clicked', () => {
                this._mode = 'jump';
                this.render(records, { show, isRtl, onLaunchApp, onAppContext, dragManager });
            });
            this._letterAnchors.set(letter, letterBtn);
            this._list.add_child(letterBtn);

            for (const rec of buckets.get(letter))
                this._list.add_child(this._createRow(rec, onLaunchApp, onAppContext, dragManager));
        });
    }

    _renderJumpGrid(buckets, isRtl, rerenderList) {
        const wrap = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-jump-grid-box',
            x_expand: true,
        });
        wrap.add_child(new St.Label({
            text: I18n.t('alphabet_jump_hint'),
            style_class: 'sadeem-jump-grid-hint',
            reactive: false,
        }));

        const letters = isRtl
            ? [...ARABIC_LETTERS, ...LATIN_LETTERS]
            : [...LATIN_LETTERS, ...ARABIC_LETTERS];

        for (let i = 0; i < letters.length; i += 4) {
            const rowBox = new St.BoxLayout({
                orientation: Clutter.Orientation.HORIZONTAL,
                style_class: 'sadeem-jump-row',
                x_expand: true,
            });
            for (const l of letters.slice(i, i + 4)) {
                const hasApps = buckets.has(l);
                const btnStyle = hasApps ? 'sadeem-jump-letter-btn' : 'sadeem-jump-letter-btn sadeem-jump-letter-disabled';
                const btnLbl = new St.Label({ text: l, x_align: Clutter.ActorAlign.CENTER, reactive: false });
                const btn = new St.Button({
                    style_class: btnStyle,
                    can_focus: hasApps,
                    reactive: hasApps,
                    x_expand: true,
                    child: btnLbl,
                });
                if (hasApps) {
                    btn.connect('clicked', () => {
                        this._mode = 'list';
                        rerenderList();
                        this._scrollToLetter(l);
                    });
                }
                rowBox.add_child(btn);
            }
            wrap.add_child(rowBox);
        }
        this._list.add_child(wrap);
    }

    _scrollToLetter(letter) {
        if (this._scrollIdleId)
            GLib.source_remove(this._scrollIdleId);
        this._scrollIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._scrollIdleId = null;
            const anchor = this._letterAnchors.get(letter);
            if (anchor) {
                try {
                    const box = anchor.get_allocation_box?.();
                    const adj = this.vadjustment;
                    if (box && adj)
                        adj.value = Math.max(0, box.y1 - 4);
                } catch (_e) {}
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _createRow(appRecord, onLaunchApp, onAppContext, dragManager = null) {
        const icon = getAppGicon(appRecord);
        const rowBox = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            style_class: 'sadeem-menu-sidebar-row-inner',
            x_expand: true,
            reactive: false,
        });
        rowBox.add_child(new St.Icon({
            gicon: icon,
            icon_size: 22,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        }));
        const label = new St.Label({
            text: appRecord.name,
            style_class: 'sadeem-menu-sidebar-label',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        label.clutter_text.single_line_mode = true;
        label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        rowBox.add_child(label);

        const rowBtn = new St.Button({
            style_class: 'sadeem-menu-sidebar-row',
            button_mask: St.ButtonMask.PRIMARY,
            can_focus: true,
            reactive: true,
            track_hover: true,
            x_expand: true,
            child: rowBox,
        });
        rowBtn.accessible_name = appRecord.name;
        rowBtn.connect('clicked', () => {
            if (dragManager?.consumeSuppressedClick()) return;
            onLaunchApp?.(appRecord, false);
        });
        rowBtn.connect('button-press-event', (_b, ev) => {
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                const [sx, sy] = ev.get_coords();
                onAppContext?.(appRecord, sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        dragManager?.attachDraggable(rowBtn, 'sidebar-app', {
            itemType: 'app',
            itemId: appRecord.id,
            name: appRecord.name,
            gicon: icon,
            sourceGroupId: null,
        });
        return rowBtn;
    }

    destroy() {
        if (this._scrollIdleId) {
            GLib.source_remove(this._scrollIdleId);
            this._scrollIdleId = null;
        }
        this._letterAnchors.clear();
        super.destroy();
    }
}
