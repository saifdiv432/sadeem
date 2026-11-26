// contextMenu.js - Native local context menu overlay with instant click-outside dismissal
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';

import * as I18n from './i18n.js';
import * as TileLayout from './tileLayout.js';

const CORE_CRITICAL_EXCLUSIONS = new Set([
    'org.gnome.Settings',
    'org.gnome.Nautilus',
    'org.gnome.Software',
    'org.gnome.Shell.Extensions',
    'org.gnome.Ptyxis',
    'gnome-initial-setup',
    'rumman',
]);

let _layeredPackages = new Set();

export function queryLayeredPackagesAsync() {
    try {
        const proc = new Gio.Subprocess({
            argv: ['rpm-ostree', 'status', '--json'],
            flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
        });
        proc.init(null);
        proc.communicate_utf8_async(null, null, (obj, res) => {
            try {
                const [ok, stdout] = obj.communicate_utf8_finish(res);
                if (ok && stdout) {
                    const data = JSON.parse(stdout);
                    const dep = data?.deployments?.[0];
                    if (dep) {
                        const req = dep['requested-packages'] || [];
                        const layered = dep['layered-packages'] || [];
                        _layeredPackages = new Set([...req, ...layered]);
                    }
                }
            } catch (_e) {}
        });
    } catch (_e) {}
}

export function isCoreExcluded(cleanId) {
    if (!cleanId) return true;
    if (cleanId.startsWith('org.sadeem.') || cleanId.startsWith('sadeem-')) return true;
    return CORE_CRITICAL_EXCLUSIONS.has(cleanId) || CORE_CRITICAL_EXCLUSIONS.has(cleanId.toLowerCase());
}

export function canUninstallApp(rec) {
    const appId = rec?.id || '';
    if (!appId) return false;
    try {
        const cleanId = appId.endsWith('.desktop') ? appId.slice(0, -8) : appId;
        if (isCoreExcluded(cleanId)) return false;

        const home = GLib.get_home_dir();
        if (
            GLib.file_test(`/var/lib/flatpak/app/${cleanId}`, GLib.FileTest.IS_DIR) ||
            GLib.file_test(`${home}/.local/share/flatpak/app/${cleanId}`, GLib.FileTest.IS_DIR) ||
            GLib.file_test(`/var/lib/flatpak/exports/share/applications/${cleanId}.desktop`, GLib.FileTest.EXISTS) ||
            GLib.file_test(`${home}/.local/share/flatpak/exports/share/applications/${cleanId}.desktop`, GLib.FileTest.EXISTS)
        ) {
            return true;
        }
        if (
            GLib.file_test(`${home}/.local/share/applications/${cleanId}.desktop`, GLib.FileTest.EXISTS) ||
            (rec?.filename && rec.filename.startsWith(`${home}/.local/share/applications/`))
        ) {
            return true;
        }
        if (_layeredPackages.has(cleanId))
            return true;
    } catch (_e) {}
    return false;
}

export function launchUninstaller(rec) {
    const target = rec?.id || rec?.filename;
    if (!target)
        return false;
    try {
        GLib.spawn_command_line_async(`sadeem-uninstaller ${GLib.shell_quote(target)}`);
        return true;
    } catch (err) {
        console.error(`[SadeemMenu] Failed launching sadeem-uninstaller for ${target}: ${err}`);
        return false;
    }
}

function hasDiscreteGpu() {
    try {
        return Boolean(global.get_switcheroo_control?.()?.has_dual_gpu);
    } catch (_e) {
        return false;
    }
}

function dockAndGpuItems(rec, onLaunch, onNewWindow) {
    const out = [
        { type: 'action', label: I18n.t('ctx_open'), onActivate: () => onLaunch(rec, false) },
    ];
    if (rec?.shellApp?.can_open_new_window?.() && onNewWindow)
        out.push({ type: 'action', label: I18n.t('ctx_new_window'), onActivate: () => onNewWindow(rec) });
    if (hasDiscreteGpu() && rec?.shellApp)
        out.push({ type: 'action', label: I18n.t('ctx_launch_discrete'), onActivate: () => onLaunch(rec, true) });
    try {
        const favs = AppFavorites.getAppFavorites();
        if (favs) {
            const pinned = favs.isFavorite(rec.id);
            out.push({
                type: 'action',
                label: pinned ? I18n.t('ctx_unpin_dock') : I18n.t('ctx_pin_dock'),
                onActivate: () => (pinned ? favs.removeFavorite(rec.id) : favs.addFavorite(rec.id)),
            });
        }
    } catch (_e) {}
    return out;
}

function uninstallItems(rec, onUninstall) {
    if (!onUninstall || !canUninstallApp(rec))
        return [];
    return [
        { type: 'sep' },
        {
            type: 'action',
            label: I18n.t('ctx_uninstall'),
            styleClass: 'sadeem-context-item sadeem-context-item-danger',
            onActivate: () => onUninstall(rec),
        },
    ];
}

function groupLabel(g) {
    return (g.name && g.name.trim()) ? g.name.trim() : I18n.t('folder_default_name');
}

export function buildSidebarAppMenuItems(rec, { allGroups, onLaunch, onNewWindow, onPinLoose, onAddToGroup, onUninstall }) {
    const groups = allGroups.map(g => ({ label: groupLabel(g), onActivate: () => onAddToGroup(g.id, rec.id) }));
    const items = [
        ...dockAndGpuItems(rec, onLaunch, onNewWindow),
        { type: 'sep' },
        { type: 'action', label: I18n.t('ctx_pin_loose'), onActivate: () => onPinLoose(rec.id) },
    ];
    if (groups.length > 0)
        items.push({ type: 'expandable', label: I18n.t('ctx_add_to_group'), subItems: groups });
    items.push(...uninstallItems(rec, onUninstall));
    return items;
}

export function buildLooseAppMenuItems(rec, { allGroups, onLaunch, onNewWindow, onAddToGroup, onRemoveLoose, onUninstall }) {
    const groups = allGroups.map(g => ({ label: groupLabel(g), onActivate: () => onAddToGroup(g.id, rec.id) }));
    const items = [
        ...dockAndGpuItems(rec, onLaunch, onNewWindow),
    ];
    if (groups.length > 0)
        items.push({ type: 'sep' }, { type: 'expandable', label: I18n.t('ctx_add_to_group'), subItems: groups });
    items.push({ type: 'sep' }, { type: 'action', label: I18n.t('ctx_remove_from_board'), onActivate: () => onRemoveLoose(rec.id) });
    items.push(...uninstallItems(rec, onUninstall));
    return items;
}

export function buildGroupAppMenuItems(group, rec, { allGroups, onLaunch, onNewWindow, onExtract, onMoveToGroup, onRemoveFromGroup, onUninstall }) {
    const moves = allGroups.filter(g => g.id !== group.id).map(g => ({
        label: groupLabel(g),
        onActivate: () => onMoveToGroup(group.id, g.id, rec.id),
    }));
    const items = [
        ...dockAndGpuItems(rec, onLaunch, onNewWindow),
        { type: 'sep' },
        { type: 'action', label: I18n.t('ctx_extract_to_board'), onActivate: () => onExtract(group.id, rec.id) },
    ];
    if (moves.length > 0)
        items.push({ type: 'expandable', label: I18n.t('ctx_move_to_group'), subItems: moves });
    items.push({ type: 'sep' }, { type: 'action', label: I18n.t('ctx_remove_from_group'), onActivate: () => onRemoveFromGroup(group.id, rec.id) });
    items.push(...uninstallItems(rec, onUninstall));
    return items;
}

export function buildGroupCardMenuItems(group, { onResize, onOpen, onRename, onDelete }) {
    return [
        {
            type: 'size-picker',
            label: I18n.t('ctx_resize'),
            currentSize: group.cardSize,
            options: [
                { key: '2x2', label: I18n.t('group_size_2x2') },
                { key: '3x2', label: I18n.t('group_size_3x2') },
                { key: '3x3', label: I18n.t('group_size_3x3') },
                { key: '4x3', label: I18n.t('group_size_4x3') },
            ],
            onSelectSize: sz => onResize(group.id, sz),
        },
        { type: 'sep' },
        { type: 'action', label: I18n.t('ctx_open_group'), onActivate: () => onOpen(group) },
        { type: 'action', label: I18n.t('ctx_rename_group'), onActivate: () => onRename(group) },
        { type: 'sep' },
        { type: 'action', label: I18n.t('ctx_delete_group'), onActivate: () => onDelete(group, groupLabel(group)) },
    ];
}

export function buildBackgroundMenuItems({ onNewGroup, onToggleSidebar, onReset, onSettings }) {
    return [
        { type: 'action', label: I18n.t('ctx_new_group'), onActivate: onNewGroup },
        { type: 'action', label: I18n.t('ctx_toggle_sidebar'), onActivate: onToggleSidebar },
        { type: 'sep' },
        { type: 'action', label: I18n.t('ctx_reset_layout'), onActivate: onReset },
        { type: 'action', label: I18n.t('ctx_menu_settings'), onActivate: onSettings },
    ];
}

export class ContextMenuOverlay extends St.Widget {
    static {
        GObject.registerClass(this);
    }

    constructor() {
        super({
            layout_manager: new Clutter.FixedLayout(),
            reactive: false,
            x_expand: true,
            y_expand: true,
            visible: false,
        });
        this._isOpen = false;
        this._isRtl = false;
        this._anchorX = 0;
        this._anchorY = 0;
        this._containerW = 900;
        this._containerH = 600;
        this._repositionIdleId = null;
        this._cleanupIdleId = null;

        this._dismissBackdrop = new St.Widget({
            reactive: true,
        });
        this._dismissBackdrop.connect('button-press-event', () => {
            this.close();
            return Clutter.EVENT_STOP;
        });

        this._menuBox = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-context-menu',
            reactive: true,
            can_focus: true,
            x_expand: false,
            y_expand: false,
        });

        this.add_child(this._dismissBackdrop);
        this.add_child(this._menuBox);
    }

    get isOpen() {
        return this._isOpen;
    }

    openAt(stageX, stageY, { containerActor, isRtl, isLight, items = [] }) {
        this._clearRepositionIdle();
        this._clearCleanupIdle();
        this._isOpen = false;
        this.visible = false;
        this._menuBox.destroy_all_children();

        this._isRtl = Boolean(isRtl);
        this._menuBox.text_direction = this._isRtl ? Clutter.TextDirection.RTL : Clutter.TextDirection.LTR;
        if (isLight)
            this._menuBox.add_style_class_name('sadeem-surface-light');
        else
            this._menuBox.remove_style_class_name('sadeem-surface-light');

        let localX = stageX;
        let localY = stageY;
        let cw = 900;
        let ch = 600;
        try {
            const targetParent = containerActor || this.get_parent() || this;
            const [w, h] = targetParent.get_transformed_size();
            if (w > 40 && h > 40) {
                cw = w;
                ch = h;
            }
            const [ok, tx, ty] = targetParent.transform_stage_point(stageX, stageY);
            if (ok) {
                localX = tx;
                localY = ty;
            } else {
                const [cx, cy] = targetParent.get_transformed_position();
                localX = stageX - cx;
                localY = stageY - cy;
            }
        } catch (_e) {}

        this._anchorX = localX;
        this._anchorY = localY;
        this._containerW = cw;
        this._containerH = ch;
        this.set_size(cw, ch);
        this._dismissBackdrop.set_position(0, 0);
        this._dismissBackdrop.set_size(cw, ch);

        for (const entry of items) {
            if (!entry)
                continue;
            if (entry.type === 'sep')
                this._menuBox.add_child(new St.Widget({ style_class: 'sadeem-context-sep', x_expand: true, reactive: false }));
            else if (entry.type === 'size-picker')
                this._menuBox.add_child(this._buildSizePickerRow(entry));
            else if (entry.type === 'expandable')
                this._menuBox.add_child(this._buildExpandableSection(entry));
            else if (entry.type === 'action')
                this._menuBox.add_child(this._buildActionButton(entry.label, entry.onActivate, entry.styleClass));
        }

        this.visible = true;
        this._isOpen = true;
        this.set_child_above_sibling(this._menuBox, this._dismissBackdrop);
        this._reposition();
    }

    _clearRepositionIdle() {
        if (this._repositionIdleId) {
            GLib.source_remove(this._repositionIdleId);
            this._repositionIdleId = null;
        }
    }

    _updateCardPosition() {
        if (!this._isOpen)
            return;
        try {
            this._menuBox.ensure_style();
            const [, natW] = this._menuBox.get_preferred_width(-1);
            const [, natH] = this._menuBox.get_preferred_height(natW || -1);
            const [allocW, allocH] = this._menuBox.get_transformed_size();
            const menuW = Math.max(Math.ceil(natW || 0), Math.ceil(allocW || 0), 220);
            const menuH = Math.max(Math.ceil(natH || 0), Math.ceil(allocH || 0), 40);

            let rawX = this._isRtl ? (this._anchorX - menuW - 4) : (this._anchorX + 4);
            if (this._isRtl && rawX < 8)
                rawX = this._anchorX + 4;
            else if (!this._isRtl && (rawX + menuW) > (this._containerW - 8))
                rawX = this._anchorX - menuW - 4;

            let rawY = this._anchorY + 4;
            if ((rawY + menuH) > (this._containerH - 8))
                rawY = this._anchorY - menuH - 4;

            const x = Math.round(TileLayout.clampNumber(rawX, 8, Math.max(8, this._containerW - menuW - 8)));
            const y = Math.round(TileLayout.clampNumber(rawY, 8, Math.max(8, this._containerH - menuH - 8)));
            this._menuBox.set_position(x, y);
        } catch (_e) {}
    }

    _reposition() {
        if (!this._isOpen)
            return;
        this._updateCardPosition();
        this._clearRepositionIdle();
        this._repositionIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._repositionIdleId = null;
            this._updateCardPosition();
            return GLib.SOURCE_REMOVE;
        });
    }

    _buildActionButton(labelText, onActivate, styleClass = 'sadeem-context-item') {
        const lbl = new St.Label({
            text: labelText,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        const btn = new St.Button({
            style_class: styleClass || 'sadeem-context-item',
            button_mask: St.ButtonMask.PRIMARY,
            can_focus: true,
            reactive: true,
            track_hover: true,
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            child: lbl,
        });
        btn.connect('clicked', () => {
            this.close();
            onActivate?.();
        });
        return btn;
    }

    _buildSizePickerRow({ label, currentSize, options, onSelectSize }) {
        const wrap = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-context-size-grid',
            x_expand: true,
            style: 'spacing: 6px; padding: 4px 6px;',
        });
        wrap.add_child(new St.Label({
            text: label,
            style: 'font-size: 8.5pt; opacity: 0.72;',
            reactive: false,
        }));

        for (let i = 0; i < options.length; i += 2) {
            const row = new St.BoxLayout({
                orientation: Clutter.Orientation.HORIZONTAL,
                style_class: 'sadeem-context-size-row',
                x_expand: true,
                style: 'spacing: 6px;',
            });
            row.layout_manager.homogeneous = true;
            for (const opt of options.slice(i, i + 2)) {
                const chipStyle = currentSize === opt.key
                    ? 'sadeem-context-size-chip sadeem-context-size-chip-active'
                    : 'sadeem-context-size-chip';
                const chipLbl = new St.Label({
                    text: opt.label,
                    x_expand: true,
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                    reactive: false,
                });
                chipLbl.clutter_text.single_line_mode = true;
                chipLbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                const chipBtn = new St.Button({
                    style_class: chipStyle,
                    button_mask: St.ButtonMask.PRIMARY,
                    can_focus: true,
                    reactive: true,
                    track_hover: true,
                    x_expand: true,
                    x_align: Clutter.ActorAlign.FILL,
                    child: chipLbl,
                });
                chipBtn.connect('clicked', () => {
                    this.close();
                    onSelectSize?.(opt.key);
                });
                row.add_child(chipBtn);
            }
            wrap.add_child(row);
        }
        return wrap;
    }

    _buildExpandableSection({ label, subItems = [] }) {
        const wrap = new St.BoxLayout({ orientation: Clutter.Orientation.VERTICAL, x_expand: true });
        const arrow = this._isRtl ? '◂' : '▸';
        const toggleLbl = new St.Label({
            text: `${label}  ${arrow}`,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        const toggleBtn = new St.Button({
            style_class: 'sadeem-context-item',
            button_mask: St.ButtonMask.PRIMARY,
            can_focus: true,
            reactive: true,
            track_hover: true,
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            child: toggleLbl,
        });
        const subBox = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-context-sub-box',
            x_expand: true,
            visible: false,
        });
        for (const sub of subItems)
            subBox.add_child(this._buildActionButton(sub.label, sub.onActivate));

        toggleBtn.connect('clicked', () => {
            subBox.visible = !subBox.visible;
            this._reposition();
        });
        wrap.add_child(toggleBtn);
        wrap.add_child(subBox);
        return wrap;
    }

    _clearCleanupIdle() {
        if (this._cleanupIdleId) {
            GLib.source_remove(this._cleanupIdleId);
            this._cleanupIdleId = null;
        }
    }

    close() {
        this._clearRepositionIdle();
        this._clearCleanupIdle();
        this._isOpen = false;
        this.visible = false;
        this._cleanupIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._cleanupIdleId = null;
            if (!this._isOpen)
                this._menuBox?.destroy_all_children();
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        this._clearRepositionIdle();
        this._clearCleanupIdle();
        this._isOpen = false;
        this.visible = false;
        this._menuBox?.destroy_all_children();
        super.destroy();
    }
}
