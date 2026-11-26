// bottomStrip.js - Fixed-size Most Used / Recently Installed chips + Clean Footer Bar
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as SystemActions from 'resource:///org/gnome/shell/misc/systemActions.js';

import * as I18n from './i18n.js';
import * as TileLayout from './tileLayout.js';

function getAppGicon(appRecord) {
    try {
        const icon = appRecord?.appInfo?.get_icon?.();
        if (icon)
            return icon;
    } catch (_e) {}
    return Gio.Icon.new_for_string('application-x-executable');
}

export function loadSadeemPanelGicon() {
    try {
        const f = Gio.File.new_for_path('/usr/share/icons/hicolor/scalable/apps/sadeem-logo.svg');
        if (f.query_exists(null))
            return Gio.FileIcon.new(f);
    } catch (_e) {}
    return Gio.Icon.new_for_string('sadeem-logo');
}

export class BottomStripView extends St.BoxLayout {
    static {
        GObject.registerClass(this);
    }

    constructor({ onNewGroup, onOpenSettings, onPowerAction, onShowTooltip, onHideTooltip }) {
        super({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
            y_expand: false,
            style: 'spacing: 8px;',
        });

        this._stripContainer = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            style_class: 'sadeem-menu-bottom-strip',
            x_expand: false,
            y_expand: false,
        });
        this._stripScroll = new St.ScrollView({
            style_class: 'sadeem-menu-strip-scroll',
            style: 'min-width: 0px; min-height: 0px;',
            overlay_scrollbars: true,
            hscrollbar_policy: St.PolicyType.EXTERNAL,
            vscrollbar_policy: St.PolicyType.NEVER,
            enable_mouse_scrolling: true,
            x_expand: true,
            y_expand: false,
            child: this._stripContainer,
        });
        this._stripScroll.clip_to_allocation = true;
        this._stripScroll.connect('scroll-event', (_sv, ev) => {
            const dir = ev.get_scroll_direction?.();
            let delta = 0;
            if (dir === Clutter.ScrollDirection.UP || dir === Clutter.ScrollDirection.LEFT)
                delta = -48;
            else if (dir === Clutter.ScrollDirection.DOWN || dir === Clutter.ScrollDirection.RIGHT)
                delta = 48;
            else if (dir === Clutter.ScrollDirection.SMOOTH) {
                const [sdx, sdy] = ev.get_scroll_delta?.() || [0, 0];
                delta = (Math.abs(sdy) >= Math.abs(sdx) ? sdy : sdx) * 48;
            }
            const hAdj = this._stripScroll.hadjustment;
            if (delta !== 0 && hAdj && hAdj.upper > hAdj.page_size) {
                const maxVal = Math.max(hAdj.lower, hAdj.upper - hAdj.page_size);
                hAdj.value = TileLayout.clampNumber(hAdj.value + delta, hAdj.lower, maxVal);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        this._footer = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            style_class: 'sadeem-menu-footer',
            x_expand: true,
        });

        const newGroupLbl = new St.Label({ text: I18n.t('btn_new_group'), y_align: Clutter.ActorAlign.CENTER, reactive: false });
        const btnNewGroup = new St.Button({
            style_class: 'sadeem-menu-footer-btn',
            can_focus: true,
            reactive: true,
            child: newGroupLbl,
        });
        btnNewGroup.connect('clicked', () => onNewGroup?.());
        this._footer.add_child(btnNewGroup);

        const settingsBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style: 'spacing: 6px;', reactive: false });
        settingsBox.add_child(new St.Icon({ icon_name: 'emblem-system-symbolic', icon_size: 15, y_align: Clutter.ActorAlign.CENTER, reactive: false }));
        settingsBox.add_child(new St.Label({ text: I18n.t('ctx_menu_settings'), y_align: Clutter.ActorAlign.CENTER, reactive: false }));
        const btnSettings = new St.Button({ style_class: 'sadeem-menu-footer-btn', can_focus: true, reactive: true, child: settingsBox });
        btnSettings.connect('clicked', () => onOpenSettings?.());
        this._footer.add_child(btnSettings);

        this._footer.add_child(new St.Widget({ x_expand: true }));

        this._powerBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style_class: 'sadeem-menu-power-box' });
        const sysActions = SystemActions.getDefault();
        const defs = [
            { icon: 'system-lock-screen-symbolic', labelKey: 'power_lock', fn: () => sysActions.activateLockScreen() },
            { icon: 'system-reboot-symbolic', labelKey: 'power_restart', fn: () => sysActions.activateRestart() },
            { icon: 'system-shutdown-symbolic', labelKey: 'power_shutdown', fn: () => sysActions.activatePowerOff() },
        ];
        for (const d of defs) {
            const pIcon = new St.Icon({ icon_name: d.icon, icon_size: 16, reactive: false });
            const btn = new St.Button({
                style_class: 'sadeem-menu-power-btn',
                can_focus: true,
                reactive: true,
                child: pIcon,
            });
            btn.accessible_name = I18n.t(d.labelKey);
            btn.connect('clicked', () => {
                onHideTooltip?.(btn);
                onPowerAction?.();
                d.fn();
            });
            bindTooltip(btn, I18n.t(d.labelKey), onShowTooltip, onHideTooltip);
            this._powerBox.add_child(btn);
        }
        this._footer.add_child(this._powerBox);

        this._hasStripContent = false;
        this.add_child(this._stripScroll);
        this.add_child(this._footer);
    }

    get hasStripContent() {
        return this._hasStripContent;
    }

    setPowerVisible(show) {
        this._powerBox.visible = Boolean(show);
    }

    setStripVisible(show) {
        this._stripScroll.visible = Boolean(show);
        this._stripContainer.visible = Boolean(show);
    }

    renderStrip(mostUsed, recentApps, { mostCount = null, recentCount = null, maxCount = 3, onLaunchApp, onAppContext, dragManager = null }) {
        const clampCount = (val, fallback) => TileLayout.clampNumber(Math.round(Number(val ?? fallback) || 3), 1, 4);
        const mostLimit = clampCount(mostCount, maxCount);
        const recentLimit = clampCount(recentCount, maxCount);
        this._stripContainer.destroy_all_children();
        this._hasStripContent = mostUsed.length > 0 || recentApps.length > 0;
        if (!this._hasStripContent) {
            this.setStripVisible(false);
            return;
        }
        this.setStripVisible(true);

        if (mostUsed.length > 0)
            this._stripContainer.add_child(this._buildHalf(I18n.t('section_most_used'), mostUsed, mostLimit, onLaunchApp, onAppContext, dragManager));
        if (recentApps.length > 0)
            this._stripContainer.add_child(this._buildHalf(I18n.t('section_recently_installed'), recentApps, recentLimit, onLaunchApp, onAppContext, dragManager));
    }

    _buildHalf(titleText, apps, maxCount = 3, onLaunchApp, onAppContext, dragManager = null) {
        const limit = TileLayout.clampNumber(Math.round(Number(maxCount) || 3), 1, 4);
        const sec = new St.BoxLayout({ orientation: Clutter.Orientation.VERTICAL, style_class: 'sadeem-menu-strip-section', x_expand: false, y_expand: false });
        sec.add_child(new St.Label({ text: titleText, style_class: 'sadeem-menu-strip-title', reactive: false }));

        const row = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style_class: 'sadeem-menu-strip-row-box', x_expand: false, y_expand: false });
        for (const rec of apps.slice(0, limit)) {
            const gicon = getAppGicon(rec);
            const chipInner = new St.BoxLayout({
                orientation: Clutter.Orientation.HORIZONTAL,
                style_class: 'sadeem-menu-strip-row-inner',
                x_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
                reactive: false,
            });
            chipInner.add_child(new St.Icon({ gicon, icon_size: 20, y_align: Clutter.ActorAlign.CENTER, reactive: false }));
            const lbl = new St.Label({ text: rec.name, style_class: 'sadeem-menu-strip-label', x_expand: true, y_align: Clutter.ActorAlign.CENTER, reactive: false });
            lbl.clutter_text.single_line_mode = true;
            lbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            chipInner.add_child(lbl);

            const pill = new St.Button({
                style_class: 'sadeem-menu-strip-row',
                button_mask: St.ButtonMask.PRIMARY,
                style: 'width: 138px; min-width: 138px; max-width: 138px; height: 36px;',
                can_focus: true,
                reactive: true,
                track_hover: true,
                x_expand: false,
                y_expand: false,
                y_align: Clutter.ActorAlign.CENTER,
                child: chipInner,
            });
            pill.set_size(138, 36);
            pill.accessible_name = rec.name;
            pill.connect('clicked', () => {
                if (dragManager?.consumeSuppressedClick()) return;
                onLaunchApp?.(rec, false);
            });
            pill.connect('button-press-event', (_b, ev) => {
                if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                    const [sx, sy] = ev.get_coords();
                    onAppContext?.(rec, sx, sy);
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            });
            dragManager?.attachDraggable(pill, 'strip-app', {
                itemType: 'app',
                itemId: rec.id,
                name: rec.name,
                gicon,
                sourceGroupId: null,
            });
            row.add_child(pill);
        }
        sec.add_child(row);
        return sec;
    }
}

export class MenuPromptBars extends St.BoxLayout {
    static {
        GObject.registerClass(this);
    }

    constructor({ onCreateGroup, onConfirmAction }) {
        super({ orientation: Clutter.Orientation.VERTICAL, x_expand: true, y_expand: false });
        this._confirmAction = null;
        this._onCreateGroup = onCreateGroup;
        this._onConfirmAction = onConfirmAction;

        this._newGroupBar = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style_class: 'sadeem-menu-prompt-bar', x_expand: true, visible: false });
        this._newGroupEntry = new St.Entry({ hint_text: I18n.t('new_group_placeholder'), style_class: 'sadeem-menu-search-entry', can_focus: true, reactive: true, x_expand: true });
        this._newGroupEntry.get_clutter_text().connect('activate', () => this._submitNewGroup());
        const createLbl = new St.Label({ text: I18n.t('btn_create'), reactive: false });
        const createBtn = new St.Button({ style_class: 'sadeem-menu-primary-btn', can_focus: true, reactive: true, child: createLbl });
        createBtn.connect('clicked', () => this._submitNewGroup());
        const cancelGroupLbl = new St.Label({ text: I18n.t('btn_cancel'), reactive: false });
        const cancelGroupBtn = new St.Button({ style_class: 'sadeem-menu-footer-btn', can_focus: true, reactive: true, child: cancelGroupLbl });
        cancelGroupBtn.connect('clicked', () => { this._newGroupBar.visible = false; });
        this._newGroupBar.add_child(this._newGroupEntry);
        this._newGroupBar.add_child(createBtn);
        this._newGroupBar.add_child(cancelGroupBtn);

        this._confirmBar = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style_class: 'sadeem-menu-confirm-bar', x_expand: true, visible: false });
        this._confirmLabel = new St.Label({ text: '', x_expand: true, y_align: Clutter.ActorAlign.CENTER, reactive: false });
        this._confirmYesLbl = new St.Label({ text: I18n.t('btn_delete'), reactive: false });
        const yesBtn = new St.Button({ style_class: 'sadeem-menu-confirm-danger', can_focus: true, reactive: true, child: this._confirmYesLbl });
        yesBtn.connect('clicked', () => this._runConfirm());
        const noLbl = new St.Label({ text: I18n.t('btn_cancel'), reactive: false });
        const noBtn = new St.Button({ style_class: 'sadeem-menu-footer-btn', can_focus: true, reactive: true, child: noLbl });
        noBtn.connect('clicked', () => { this._confirmBar.visible = false; this._confirmAction = null; });
        this._confirmBar.add_child(this._confirmLabel);
        this._confirmBar.add_child(yesBtn);
        this._confirmBar.add_child(noBtn);

        this.add_child(this._newGroupBar);
        this.add_child(this._confirmBar);
    }

    openNewGroup() {
        this._confirmBar.visible = false;
        this._newGroupEntry.set_text('');
        this._newGroupBar.visible = true;
    }

    focusNewGroupEntry() {
        this._newGroupEntry.grab_key_focus();
    }

    openConfirm({ kind, group = null, message, btnText }) {
        this._newGroupBar.visible = false;
        this._confirmAction = { kind, group };
        this._confirmLabel.text = message;
        this._confirmYesLbl.text = btnText;
        this._confirmBar.visible = true;
    }

    hideAll() {
        const had = this._newGroupBar.visible || this._confirmBar.visible;
        this._newGroupBar.visible = false;
        this._confirmBar.visible = false;
        this._confirmAction = null;
        return had;
    }

    _submitNewGroup() {
        const name = (this._newGroupEntry.get_text() || '').trim();
        this._newGroupBar.visible = false;
        this._newGroupEntry.set_text('');
        this._onCreateGroup?.(name);
    }

    _runConfirm() {
        const act = this._confirmAction;
        this.hideAll();
        if (act)
            this._onConfirmAction?.(act);
    }
}

export function bindTooltip(actor, text, onShow, onHide) {
    if (!actor || !text)
        return;
    actor.track_hover = true;
    actor.connect('notify::hover', () => {
        if (actor.hover)
            onShow?.(actor, text);
        else
            onHide?.(actor);
    });
    actor.connect('button-press-event', () => {
        onHide?.(actor);
        return Clutter.EVENT_PROPAGATE;
    });
    actor.connect('destroy', () => onHide?.(actor));
}

export class MenuTooltipOverlay extends St.Widget {
    static {
        GObject.registerClass(this);
    }

    constructor() {
        super({ layout_manager: new Clutter.FixedLayout(), reactive: false, x_expand: true, y_expand: true });
        this._activeActor = null;
        this._label = new St.Label({ text: '', style_class: 'sadeem-menu-tooltip', reactive: false, visible: false });
        this.add_child(this._label);
    }

    showForActor(actor, text, containerActor, maxWidth) {
        if (!text) return;
        this._activeActor = actor || null;
        this._label.text = text;
        this._label.visible = true;
        try {
            const [rx, ry] = containerActor.get_transformed_position();
            const [ax, ay] = actor.get_transformed_position();
            const [aw] = actor.get_transformed_size();
            const [, , natW, natH] = this._label.get_preferred_size();
            const tw = natW || 80;
            const th = natH || 24;
            this._label.set_position(
                Math.round(TileLayout.clampNumber((ax - rx) + (aw - tw) / 2, 8, Math.max(8, maxWidth - tw - 8))),
                Math.round(Math.max(8, (ay - ry) - th - 6))
            );
        } catch (_e) {}
    }

    hideTooltip(targetActor = null) {
        if (targetActor && this._activeActor && targetActor !== this._activeActor)
            return;
        this._activeActor = null;
        this._label.visible = false;
    }
}
