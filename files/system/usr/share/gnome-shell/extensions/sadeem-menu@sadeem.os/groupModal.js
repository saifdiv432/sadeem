// groupModal.js - Clean centered floating group overlay inside menu container
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as I18n from './i18n.js';

function getAppGicon(appRecord) {
    try {
        const icon = appRecord?.appInfo?.get_icon?.();
        if (icon)
            return icon;
    } catch (_e) {}
    return Gio.Icon.new_for_string('application-x-executable');
}

export class GroupModalOverlay extends St.Widget {
    static {
        GObject.registerClass(this);
    }

    constructor() {
        super({
            layout_manager: new Clutter.BinLayout(),
            reactive: false,
            x_expand: true,
            y_expand: true,
            visible: false,
        });
        this._isOpen = false;
        this._groupId = null;
        this._suppressCommit = false;
        this._nameEntry = null;
        this._cleanupIdleId = null;

        this._backdrop = new St.Widget({
            style_class: 'sadeem-group-modal-backdrop',
            reactive: true,
            x_expand: true,
            y_expand: true,
        });
        this._backdrop.connect('button-press-event', () => {
            this.close();
            return Clutter.EVENT_STOP;
        });

        this._card = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-group-modal',
            reactive: true,
            can_focus: true,
            x_expand: false,
            y_expand: false,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._card.clip_to_allocation = true;

        this.add_child(this._backdrop);
        this.add_child(this._card);
    }

    get isOpen() {
        return this._isOpen;
    }

    get groupId() {
        return this._groupId;
    }

    _clearCleanupIdle() {
        if (this._cleanupIdleId) {
            GLib.source_remove(this._cleanupIdleId);
            this._cleanupIdleId = null;
        }
    }

    focusNameEntry() {
        try {
            this._nameEntry?.grab_key_focus?.();
        } catch (_e) {}
    }

    open(group, { containerW = 900, containerH = 600, isRtl = false, isLight = false, onRename, onLaunchApp, onAppContext, dragManager = null }) {
        this._clearCleanupIdle();
        this._suppressCommit = true;
        this._card.destroy_all_children();
        this._suppressCommit = false;

        this._groupId = group.id;
        this.text_direction = isRtl ? Clutter.TextDirection.RTL : Clutter.TextDirection.LTR;
        this._card.text_direction = this.text_direction;
        if (isLight)
            this._card.add_style_class_name('sadeem-surface-light');
        else
            this._card.remove_style_class_name('sadeem-surface-light');

        const apps = Array.isArray(group.apps) ? group.apps : [];
        const modalW = Math.min(460, Math.max(280, containerW - 48));
        const cols = Math.max(3, Math.floor((modalW - 36) / 96));
        const tileW = Math.floor((modalW - 36 - Math.max(0, cols - 1) * 8) / cols);
        const tileH = 88;
        const rows = Math.max(1, Math.ceil(apps.length / cols));
        const contentH = 56 + rows * (tileH + 8) + 32;
        const maxModalH = Math.min(410, Math.max(200, containerH - 48));
        const modalH = Math.min(maxModalH, Math.max(185, contentH));
        this._card.set_size(modalW, modalH);
        this._card.style = `width: ${modalW}px; height: ${modalH}px;`;

        const header = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            style_class: 'sadeem-group-modal-header',
            x_expand: true,
        });

        const initialTitle = group.name || '';
        const nameEntry = new St.Entry({
            text: initialTitle,
            hint_text: I18n.t('name_group_hint'),
            style_class: 'sadeem-folder-name-entry',
            can_focus: true,
            reactive: true,
            x_expand: true,
        });
        this._nameEntry = nameEntry;

        const commitRename = () => {
            if (this._suppressCommit || !this._isOpen)
                return;
            const clean = (nameEntry.get_text() || '').trim();
            if (clean !== initialTitle)
                onRename?.(group.id, clean);
        };
        const ct = nameEntry.get_clutter_text();
        ct.connect('activate', () => {
            commitRename();
            this._card.grab_key_focus();
        });
        ct.connect('key-focus-out', commitRename);

        const closeIcon = new St.Icon({
            icon_name: 'window-close-symbolic',
            icon_size: 16,
            reactive: false,
        });
        const closeBtn = new St.Button({
            style_class: 'sadeem-group-action-btn',
            can_focus: true,
            reactive: true,
            child: closeIcon,
        });
        closeBtn.connect('clicked', () => {
            commitRename();
            this.close();
        });

        header.add_child(nameEntry);
        header.add_child(closeBtn);
        this._card.add_child(header);

        const grid = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-group-modal-grid',
            x_expand: true,
            y_expand: false,
        });

        if (apps.length === 0) {
            const emptyLbl = new St.Label({
                text: I18n.t('hint_empty_group'),
                style_class: 'sadeem-empty-group-dropzone',
                x_expand: true,
                reactive: false,
            });
            emptyLbl.clutter_text.line_wrap = true;
            emptyLbl.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
            grid.add_child(emptyLbl);
        } else {
            for (let i = 0; i < apps.length; i += cols) {
                const rowBox = new St.BoxLayout({
                    orientation: Clutter.Orientation.HORIZONTAL,
                    style_class: 'sadeem-group-modal-row',
                    x_expand: true,
                });
                for (const entry of apps.slice(i, i + cols)) {
                    const rec = entry.record;
                    const vbox = new St.BoxLayout({
                        orientation: Clutter.Orientation.VERTICAL,
                        x_expand: true,
                        y_expand: true,
                        y_align: Clutter.ActorAlign.CENTER,
                        reactive: false,
                        style: 'spacing: 4px;',
                    });
                    const gicon = getAppGicon(rec);
                    const icon = new St.Icon({
                        gicon,
                        icon_size: 40,
                        x_align: Clutter.ActorAlign.CENTER,
                        reactive: false,
                    });
                    const lbl = new St.Label({
                        text: rec.name,
                        style_class: 'sadeem-tile-label',
                        x_expand: true,
                        x_align: Clutter.ActorAlign.CENTER,
                        reactive: false,
                    });
                    lbl.clutter_text.single_line_mode = false;
                    lbl.clutter_text.line_wrap = true;
                    lbl.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
                    lbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                    lbl.clutter_text.line_alignment = Pango.Alignment.CENTER;
                    vbox.add_child(icon);
                    vbox.add_child(lbl);

                    const tile = new St.Button({
                        style_class: 'sadeem-group-modal-tile',
                        button_mask: St.ButtonMask.PRIMARY,
                        style: `width: ${tileW}px; height: ${tileH}px;`,
                        can_focus: true,
                        reactive: true,
                        track_hover: true,
                        x_expand: false,
                        y_expand: false,
                        child: vbox,
                    });
                    tile.set_size(tileW, tileH);
                    tile.accessible_name = rec.name;
                    tile.connect('clicked', () => onLaunchApp?.(rec, false));
                    tile.connect('button-press-event', (_b, ev) => {
                        if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                            const [sx, sy] = ev.get_coords();
                            onAppContext?.(group, rec, sx, sy);
                            return Clutter.EVENT_STOP;
                        }
                        return Clutter.EVENT_PROPAGATE;
                    });
                    rowBox.add_child(tile);
                }
                grid.add_child(rowBox);
            }
        }

        const scroll = new St.ScrollView({
            style_class: 'sadeem-group-modal-scroll',
            style: 'min-width: 0px; min-height: 0px;',
            overlay_scrollbars: false,
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            enable_mouse_scrolling: true,
            x_expand: true,
            y_expand: true,
            child: grid,
        });
        scroll.clip_to_allocation = true;
        this._card.add_child(scroll);

        this.visible = true;
        this._isOpen = true;
    }

    close() {
        this._clearCleanupIdle();
        this._suppressCommit = true;
        this._isOpen = false;
        this._groupId = null;
        this.visible = false;
        this._nameEntry = null;
        this._cleanupIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._cleanupIdleId = null;
            if (!this._isOpen) {
                this._suppressCommit = true;
                this._card?.destroy_all_children();
                this._suppressCommit = false;
            }
            return GLib.SOURCE_REMOVE;
        });
        this._suppressCommit = false;
    }

    destroy() {
        this._clearCleanupIdle();
        this._suppressCommit = true;
        this._isOpen = false;
        this._groupId = null;
        this.visible = false;
        this._nameEntry = null;
        this._card?.destroy_all_children();
        this._suppressCommit = false;
        super.destroy();
    }
}
