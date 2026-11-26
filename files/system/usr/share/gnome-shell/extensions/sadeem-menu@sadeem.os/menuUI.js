// menuUI.js - Modular Sadeem PanelMenu.Button orchestrator (GNOME 51 ESM)
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import { BoardView } from './boardView.js';
import { BottomStripView, MenuPromptBars, MenuTooltipOverlay, bindTooltip, loadSadeemPanelGicon } from './bottomStrip.js';
import { ContextMenuOverlay, buildBackgroundMenuItems, buildGroupAppMenuItems, buildGroupCardMenuItems, buildLooseAppMenuItems, buildSidebarAppMenuItems, launchUninstaller, queryLayeredPackagesAsync } from './contextMenu.js';
import { DragManager, applyBoardDrop } from './dragManager.js';
import { GroupModalOverlay } from './groupModal.js';
import * as I18n from './i18n.js';
import { ResizeOverlay } from './resizeManager.js';
import { SidebarView } from './sidebarView.js';
import * as TileLayout from './tileLayout.js';

export class SadeemPanelButton extends PanelMenu.Button {
    static {
        GObject.registerClass(this);
    }

    constructor({ settings, appData, searchEngine, onOpenExtensionPrefs }) {
        super(0.5, I18n.t('menu_title'), false);
        this.add_style_class_name('sadeem-menu-panel-button');

        this._isRtl = I18n.isRtl();
        this._settings = settings;
        this._appData = appData;
        this._searchEngine = searchEngine;
        this._onOpenExtensionPrefs = onOpenExtensionPrefs;
        this._viewMode = 'home';
        this._isLightTheme = null;
        this._searchDebounceId = null;
        this._focusIdleId = null;
        this._boardDirty = true;
        this._sidebarDirty = true;
        this._stripKey = '';
        this._cachedRecords = null;
        this._lastShowSidebar = null;
        this._appliedMenuW = 0;
        this._appliedMenuH = 0;
        this._currentMenuW = 1140;
        this._currentMenuH = 680;
        this._currentBoardW = 0;
        this._settingSignals = [];
        this._ifaceSignals = [];
        try { this._prevDisabledSmart = new Set(this._settings.get_strv('disabled-smart-groups') || []); } catch (_e) { this._prevDisabledSmart = new Set(); }
        queryLayeredPackagesAsync();

        const box = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style_class: 'panel-status-menu-box' });
        box.add_child(new St.Icon({
            gicon: loadSadeemPanelGicon(), fallback_icon_name: 'start-here-symbolic',
            icon_size: 24, style_class: 'sadeem-menu-panel-icon', y_align: Clutter.ActorAlign.CENTER, reactive: false,
        }));
        this.add_child(box);

        this.menu.actor.add_style_class_name('sadeem-popup-menu');
        if (this.menu._boxPointer)
            this.menu._boxPointer.style = '-arrow-base: 0px; -arrow-rise: 0px; -boxpointer-gap: 6px; -arrow-border-radius: 20px;';

        this._buildMenuContents();
        this._connectSignals();
        this._syncTheme();
        this._bottomStrip.setPowerVisible(this._settings.get_boolean('show-power-buttons'));
    }

    _buildMenuContents() {
        const textDir = this._isRtl ? Clutter.TextDirection.RTL : Clutter.TextDirection.LTR;
        this._menuRootStack = new St.Widget({ layout_manager: new Clutter.BinLayout(), reactive: false, x_expand: true, y_expand: true });
        this._menuRootStack.set_text_direction(textDir);
        this._menuRootStack.clip_to_allocation = true;
        this._rootContainer = new St.BoxLayout({ orientation: Clutter.Orientation.VERTICAL, style_class: 'sadeem-menu-root', x_expand: true, y_expand: true });
        this._rootContainer.set_text_direction(textDir);

        const topBar = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style_class: 'sadeem-menu-topbar', x_expand: true });
        const sidebarIcon = new St.Icon({ icon_name: 'open-menu-symbolic', icon_size: 16, reactive: false });
        this._sidebarToggleBtn = new St.Button({ style_class: 'sadeem-menu-icon-btn', can_focus: true, reactive: true, child: sidebarIcon });
        this._sidebarToggleBtn.accessible_name = I18n.t('toggle_sidebar_tooltip');
        this._sidebarToggleBtn.connect('clicked', () => { this._hideTooltip(); this._settings.set_boolean('show-all-apps-sidebar', !this._settings.get_boolean('show-all-apps-sidebar')); });
        bindTooltip(this._sidebarToggleBtn, I18n.t('toggle_sidebar_tooltip'), (a, t) => this._showTooltip(a, t), target => this._hideTooltip(target));

        this._clearSearchIcon = new St.Icon({ icon_name: 'edit-clear-symbolic', style_class: 'sadeem-menu-search-icon', reactive: true, visible: false });
        this._searchEntry = new St.Entry({ hint_text: I18n.t('search_placeholder'), style_class: 'sadeem-menu-search-entry', can_focus: true, reactive: true, x_expand: true });
        this._searchEntry.set_primary_icon(new St.Icon({ icon_name: 'edit-find-symbolic', style_class: 'sadeem-menu-search-icon', reactive: false }));
        this._searchEntry.set_secondary_icon(this._clearSearchIcon);
        this._searchEntry.connect('secondary-icon-clicked', () => { this._searchEntry.set_text(''); this._searchEntry.grab_key_focus(); });
        this._searchEntry.get_clutter_text().connect('text-changed', () => this._onSearchChanged());
        this._searchEntry.get_clutter_text().connect('activate', () => this._activateSearchSelection());
        topBar.add_child(this._sidebarToggleBtn);
        topBar.add_child(this._searchEntry);
        this._rootContainer.add_child(topBar);

        this._promptBars = new MenuPromptBars({ onCreateGroup: name => this._appData.createGroup(name), onConfirmAction: act => this._runConfirmedAction(act) });
        this._rootContainer.add_child(this._promptBars);

        this._mainBody = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, style_class: 'sadeem-menu-main-body', style: 'min-width: 0px; min-height: 0px;', x_expand: true, y_expand: true });
        this._sidebarView = new SidebarView();
        this._boardView = new BoardView();
        this._mainBody.add_child(this._sidebarView);
        this._mainBody.add_child(this._boardView);
        this._rootContainer.add_child(this._mainBody);

        this._bottomStrip = new BottomStripView({ onNewGroup: () => this._openNewGroupBar(), onOpenSettings: () => { this.menu.close(); this._onOpenExtensionPrefs?.(); }, onPowerAction: () => this.menu.close(), onShowTooltip: (a, t) => this._showTooltip(a, t), onHideTooltip: target => this._hideTooltip(target) });
        this._rootContainer.add_child(this._bottomStrip);

        this._resizeOverlay = new ResizeOverlay({ menuActor: this.menu.actor, rootStack: this._menuRootStack, rootContainer: this._rootContainer, settings: this._settings, getWorkArea: () => this._getWorkArea(), isRtl: this._isRtl, isBlocked: () => this._groupModal.isOpen || this._contextMenu.isOpen || this._dragManager?.isDragging, onBeforeStart: () => { this._hideTooltip(); this._contextMenu.close(); this._boardView?.beginResizeAnchor(); }, onResizeMotion: () => { this._boardView?.syncResizeAnchor(); }, onResizeCancelled: () => { this._boardView?.endResizeAnchor(); }, onResizeCommitted: () => { this._boardView?.endResizeAnchor(); this._applyGeometry(); this.renderCurrentView(); } });
        this._groupModal = new GroupModalOverlay();
        this._dragOverlayLayer = new St.Widget({ layout_manager: new Clutter.FixedLayout(), reactive: false, x_expand: true, y_expand: true });
        this._dragManager = new DragManager({ menuActor: this.menu.actor, rootStack: this._menuRootStack, overlayLayer: this._dragOverlayLayer, isResizing: () => this._resizeOverlay.isResizing, onBeforeStart: p => { this._hideTooltip(); this._contextMenu.close(); if (p.kind === 'group-modal-app') this._groupModal.close(); }, onDrop: (drag, res) => applyBoardDrop(this._appData, this._getRecords(), drag, res) });
        this._contextMenu = new ContextMenuOverlay();
        this._tooltipLayer = new MenuTooltipOverlay();
        for (const layer of [this._rootContainer, this._resizeOverlay, this._groupModal, this._dragOverlayLayer, this._tooltipLayer, this._contextMenu])
            this._menuRootStack.add_child(layer);
        const syncResizeVis = () => { if (this._resizeOverlay) this._resizeOverlay.visible = !this._groupModal.visible && !this._contextMenu.visible; };
        this._groupModal.connect('notify::visible', syncResizeVis);
        this._contextMenu.connect('notify::visible', syncResizeVis);

        const section = new PopupMenu.PopupMenuSection();
        section.actor.add_child(this._menuRootStack);
        this.menu.addMenuItem(section);
    }

    _connectSignals() {
        this._openStateSigId = this.menu.connect('open-state-changed', (_m, isOpen) => (isOpen ? this._onMenuOpened() : this._onMenuClosed()));
        this._keyPressSigId = this.menu.actor.connect('key-press-event', (_a, ev) => this._onMenuKeyPress(ev));
        for (const k of ['icon-size-level', 'show-all-apps-sidebar', 'show-most-used', 'show-recently-installed', 'most-used-count', 'recently-installed-count', 'bottom-section-count', 'auto-categorize', 'disabled-smart-groups', 'layout-config', 'menu-width', 'menu-height']) {
            this._settingSignals.push(this._settings.connect(`changed::${k}`, () => {
                if (k === 'disabled-smart-groups') this._syncRestoredSmartGroups();
                if (['icon-size-level', 'auto-categorize', 'disabled-smart-groups', 'layout-config', 'show-all-apps-sidebar'].includes(k)) this._boardDirty = true;
                if (k === 'show-all-apps-sidebar') this._sidebarDirty = true;
                if (['show-most-used', 'show-recently-installed', 'most-used-count', 'recently-installed-count', 'bottom-section-count'].includes(k)) this._stripKey = '';
                if (!this.menu.isOpen) return;
                this._applyGeometry();
                this.renderCurrentView();
                if (this._groupModal.isOpen && (k === 'layout-config' || k === 'auto-categorize' || k === 'disabled-smart-groups')) this._refreshOpenModal();
            }));
        }
        this._settingSignals.push(this._settings.connect('changed::show-power-buttons', () => this._bottomStrip.setPowerVisible(this._settings.get_boolean('show-power-buttons'))));
        this._settingSignals.push(this._settings.connect('changed::menu-opacity', () => this._syncSurfaceOpacity()));
        try {
            this._ifaceSettings = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });
            for (const k of ['color-scheme', 'gtk-theme'])
                this._ifaceSignals.push(this._ifaceSettings.connect(`changed::${k}`, () => this._syncTheme()));
        } catch (_e) {}
    }

    _syncRestoredSmartGroups() {
        let curr = [];
        try { curr = this._settings.get_strv('disabled-smart-groups') || []; } catch (_e) {}
        const currSet = new Set(curr);
        for (const id of this._prevDisabledSmart) { if (!currSet.has(id)) this._appData.restoreSmartGroup(id, this._cachedRecords); }
        this._prevDisabledSmart = currSet;
    }

    _syncSurfaceOpacity() {
        const raw = this._settings?.get_int('menu-opacity');
        const clamped = TileLayout.clampNumber(Number.isFinite(raw) ? raw : 96, 10, 100);
        const alpha = (clamped / 100).toFixed(2);
        const rgb = this._isLightTheme ? '248, 248, 250' : '28, 28, 32';
        if (this.menu?.box)
            this.menu.box.style = `background-color: rgba(${rgb}, ${alpha});`;
    }

    _syncTheme() {
        let isLight = false;
        try {
            const scheme = (this._ifaceSettings?.get_string('color-scheme') || '').toLowerCase();
            const gtk = (this._ifaceSettings?.get_string('gtk-theme') || '').toLowerCase();
            isLight = scheme === 'prefer-light' || (scheme !== 'prefer-dark' && Boolean(gtk) && !gtk.includes('dark'));
        } catch (_e) {}
        if (this._isLightTheme !== isLight) {
            this._isLightTheme = isLight;
            this.menu.actor[isLight ? 'add_style_class_name' : 'remove_style_class_name']('sadeem-surface-light');
            this._menuRootStack[isLight ? 'add_style_class_name' : 'remove_style_class_name']('sadeem-surface-light');
        }
        this._syncSurfaceOpacity();
    }

    _getWorkArea() {
        try {
            const mon = Main.layoutManager.findMonitorForActor(this);
            const wa = Main.layoutManager.getWorkAreaForMonitor(mon ? mon.index : Main.layoutManager.primaryIndex);
            if (wa?.width > 0 && wa?.height > 0) return wa;
        } catch (_e) {}
        return { x: 0, y: 0, width: 1920, height: 1040 };
    }

    _applyGeometry() {
        const wa = this._getWorkArea();
        const showSidebar = this._settings.get_boolean('show-all-apps-sidebar');
        const geom = TileLayout.computeMenuGeometry({ workAreaWidth: Math.max(360, wa.width - 4), workAreaHeight: Math.max(360, wa.height), showAllAppsSidebar: showSidebar, desiredWidth: this._settings.get_int('menu-width'), desiredHeight: this._settings.get_int('menu-height') });
        if (geom.boardWidth !== this._currentBoardW) this._boardDirty = true;
        this._currentMenuW = geom.totalWidth;
        this._currentMenuH = geom.totalHeight;
        this._currentBoardW = geom.boardWidth;
        if (geom.totalWidth !== this._appliedMenuW || geom.totalHeight !== this._appliedMenuH) {
            this._appliedMenuW = geom.totalWidth;
            this._appliedMenuH = geom.totalHeight;
            this._menuRootStack.set_size(geom.totalWidth, geom.totalHeight);
            this._rootContainer.set_size(geom.totalWidth, geom.totalHeight);
        }
        this._resizeOverlay.syncBounds(geom.totalWidth, geom.totalHeight);
        if (showSidebar !== this._lastShowSidebar) {
            this._lastShowSidebar = showSidebar;
            this._mainBody[showSidebar ? 'remove_style_class_name' : 'add_style_class_name']('sadeem-menu-main-body-no-sidebar');
            this._sidebarToggleBtn[showSidebar ? 'add_style_class_name' : 'remove_style_class_name']('sadeem-menu-icon-btn-active');
        }
    }

    _getRecords() { return this._cachedRecords || (this._cachedRecords = this._appData.getInstalledRecords()); }

    markInstalledChanged() {
        this._cachedRecords = null; this._boardDirty = true; this._sidebarDirty = true; this._stripKey = '';
        if (this.menu.isOpen) this.renderCurrentView();
    }

    refreshStripOnly() { if (this.menu.isOpen && this._viewMode === 'home') this._syncBottomStrip(this._getRecords()); }

    _onMenuOpened() {
        if (this._sidebarView.mode !== 'list') { this._sidebarView.resetMode(); this._sidebarDirty = true; }
        if (this._viewMode === 'search') { this._viewMode = 'home'; this._boardDirty = true; }
        this._onMenuClosed();
        if (this._searchEntry.get_text()) this._searchEntry.set_text('');
        this._syncTheme();
        this._applyGeometry();
        try { this.renderCurrentView(); } catch (err) { console.error('[SadeemMenu] renderCurrentView failed:', err); }
        this._scheduleIdleFocus(() => this._searchEntry?.grab_key_focus());
        this._appData.refreshSeenAppsAsync().then(() => this.refreshStripOnly()).catch(() => {});
    }

    _onMenuClosed() {
        this._dragManager?.cancel(); this._resizeOverlay?.cancel();
        this._contextMenu.close(); this._groupModal.close(); this._hideTooltip();
        this._cancelSearchDebounce(); this._searchEngine.cancelPending(); this._promptBars.hideAll();
    }

    refreshContent() {
        this._boardDirty = true; this._sidebarDirty = true; this._stripKey = '';
        if (this.menu.isOpen) this.renderCurrentView();
    }

    _baseAppCtxOpts(allGroups) {
        return {
            allGroups,
            onLaunch: (app, d) => this._launchApp(app, d),
            onNewWindow: app => this._launchApp(app, false, true),
            onUninstall: app => { this.menu.close(BoxPointer.PopupAnimation.NONE); launchUninstaller(app); },
        };
    }

    _openSidebarAppCtx(rec, sx, sy, records = null) {
        const recs = records || this._getRecords();
        const base = this._baseAppCtxOpts(this._appData.getBoardModel(recs).allGroups);
        this._openCtx(sx, sy, buildSidebarAppMenuItems(rec, { ...base, onPinLoose: id => this._appData.pinLooseApp(id, null, null, recs), onAddToGroup: (gid, id) => this._appData.addAppToGroup({ targetGroupId: gid, appId: id }, recs) }));
    }

    renderCurrentView() {
        const records = this._getRecords();
        if (this._sidebarDirty) {
            this._sidebarView.render(records, { show: this._settings.get_boolean('show-all-apps-sidebar'), isRtl: this._isRtl, onLaunchApp: (r, d) => this._launchApp(r, d), onAppContext: (r, sx, sy) => this._openSidebarAppCtx(r, sx, sy, records), dragManager: this._dragManager });
            this._sidebarDirty = false;
        }
        if (this._viewMode === 'search') { this._bottomStrip.setStripVisible(false); return; }
        if (this._boardDirty) {
            const board = this._appData.getBoardModel(records);
            const base = this._baseAppCtxOpts(board.allGroups);
            this._boardView.renderHome(board.items, {
                boardWidth: this._currentBoardW,
                iconSizeLevel: this._settings.get_int('icon-size-level'),
                isRtl: this._isRtl,
                dragManager: this._dragManager,
                onLaunchApp: (r, d) => this._launchApp(r, d),
                onLooseAppContext: (r, sx, sy) => this._openCtx(sx, sy, buildLooseAppMenuItems(r, { ...base, onAddToGroup: (gid, id) => this._appData.addAppToGroup({ targetGroupId: gid, appId: id, removeLoose: true }, records), onRemoveLoose: id => this._appData.removeLooseApp(id, records) })),
                onGroupAppContext: (g, r, sx, sy) => this._openGroupAppCtx(g, r, sx, sy, records),
                onOpenGroupModal: grp => this._openGroupModal(grp, false),
                onGroupCardContext: (grp, sx, sy) => this._openCtx(sx, sy, buildGroupCardMenuItems(grp, { onResize: (gid, sz) => this._appData.setGroupCardSize(gid, sz, records), onOpen: g => this._openGroupModal(g, false), onRename: g => this._openGroupModal(g, true), onDelete: (g, label) => this._promptBars.openConfirm({ kind: 'delete_group', group: g, message: I18n.t('confirm_delete_group', { name: label }), btnText: I18n.t('btn_delete') }) })),
                onBackgroundContext: (sx, sy) => this._openCtx(sx, sy, buildBackgroundMenuItems({ onNewGroup: () => this._openNewGroupBar(), onToggleSidebar: () => this._settings.set_boolean('show-all-apps-sidebar', !this._settings.get_boolean('show-all-apps-sidebar')), onReset: () => this._promptBars.openConfirm({ kind: 'reset_layout', message: I18n.t('confirm_reset_layout'), btnText: I18n.t('btn_reset') }), onSettings: () => { this.menu.close(BoxPointer.PopupAnimation.NONE); this._onOpenExtensionPrefs?.(); } })),
                onShowTooltip: (a, t) => this._showTooltip(a, t),
                onHideTooltip: target => this._hideTooltip(target),
            });
            this._boardDirty = false;
        }
        this._syncBottomStrip(records);
    }

    _syncBottomStrip(records) {
        const mostCount = TileLayout.clampNumber(this._settings.get_int('most-used-count'), 1, 4);
        const recentCount = TileLayout.clampNumber(this._settings.get_int('recently-installed-count'), 1, 4);
        const showMost = this._settings.get_boolean('show-most-used');
        const showRecent = this._settings.get_boolean('show-recently-installed');
        const most = showMost ? this._appData.getMostUsedRecords(records, mostCount) : [];
        const recent = showRecent ? this._appData.getRecentlyInstalledRecords(records, recentCount) : [];
        const nextKey = `${showMost}:${showRecent}:${mostCount}:${recentCount}:${most.map(r => r.id).join(',')}|${recent.map(r => r.id).join(',')}`;
        if (nextKey === this._stripKey) {
            if (this._bottomStrip.hasStripContent) this._bottomStrip.setStripVisible(true);
            return;
        }
        this._stripKey = nextKey;
        this._bottomStrip.renderStrip(most, recent, { mostCount, recentCount, onLaunchApp: (r, d) => this._launchApp(r, d), onAppContext: (r, sx, sy) => this._openSidebarAppCtx(r, sx, sy, records), dragManager: this._dragManager });
    }

    _openGroupAppCtx(group, rec, sx, sy, records = null) {
        const recs = records || this._getRecords();
        const base = this._baseAppCtxOpts(this._appData.getBoardModel(recs).allGroups);
        this._openCtx(sx, sy, buildGroupAppMenuItems(group, rec, { ...base, onExtract: (gid, id) => this._appData.extractAppToBoard(gid, id, null, null, recs), onMoveToGroup: (srcGid, dstGid, id) => this._appData.addAppToGroup({ targetGroupId: dstGid, appId: id, sourceGroupId: srcGid }, recs), onRemoveFromGroup: (gid, id) => this._appData.removeAppFromGroup(gid, id, recs) }));
    }

    _openGroupModal(group, focusRename = false) {
        this._hideTooltip();
        this._contextMenu.close();
        this._groupModal.open(group, { containerW: this._currentMenuW, containerH: this._currentMenuH, isRtl: this._isRtl, isLight: this._isLightTheme, dragManager: this._dragManager, onRename: (gid, name) => this._appData.renameGroup(gid, name), onLaunchApp: (r, d) => this._launchApp(r, d), onAppContext: (g, r, sx, sy) => this._openGroupAppCtx(g, r, sx, sy) });
        if (focusRename) this._scheduleIdleFocus(() => this._groupModal.focusNameEntry());
    }

    _refreshOpenModal() {
        const gid = this._groupModal.groupId;
        const updated = gid ? this._appData.getBoardModel().allGroups.find(g => g.id === gid) : null;
        if (updated && (updated.apps.length > 0 || !updated.isSmart)) this._openGroupModal(updated, false);
        else this._groupModal.close();
    }

    _cancelSearchDebounce() {
        if (this._searchDebounceId) { GLib.source_remove(this._searchDebounceId); this._searchDebounceId = null; }
    }

    _onSearchChanged() {
        const text = this._searchEntry.get_text() || '';
        const trimmed = text.trim();
        this._clearSearchIcon.visible = text.length > 0;
        this._searchEntry[text.length > 0 ? 'add_style_class_name' : 'remove_style_class_name']('sadeem-search-active');
        this._cancelSearchDebounce();
        this._searchEngine.cancelPending();
        if (!trimmed) {
            if (this._viewMode === 'search') { this._viewMode = 'home'; this.renderCurrentView(); }
            return;
        }
        this._viewMode = 'search';
        this._boardDirty = true;
        this._groupModal.close();
        this._bottomStrip.setStripVisible(false);
        const records = this._getRecords();
        const appResults = this._searchEngine.searchApps(records, trimmed, 14);
        const renderFn = (files, pending) => this._boardView.renderSearch(appResults, files, pending, {
            onLaunchApp: (r, d) => this._launchApp(r, d),
            onAppContext: (r, sx, sy) => this._openSidebarAppCtx(r, sx, sy, records),
            onActivateFile: fRes => { this.menu.close(BoxPointer.PopupAnimation.NONE); this._searchEngine.activateFileResult(fRes, trimmed, global.create_app_launch_context(global.get_current_time(), -1)); },
        });
        renderFn([], true);
        this._searchDebounceId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
            this._searchDebounceId = null;
            this._searchEngine.searchFilesAsync(trimmed, 6).then(files => {
                if (this._viewMode === 'search' && this.menu.isOpen && (this._searchEntry.get_text() || '').trim() === trimmed) renderFn(files, false);
            }).catch(() => { if (this._viewMode === 'search' && this.menu.isOpen) renderFn([], false); });
            return GLib.SOURCE_REMOVE;
        });
    }

    _activateSearchSelection() {
        const sel = this._boardView.getSelectedSearchItem();
        if (!sel) return;
        if (sel.type === 'app') this._launchApp(sel.record, false);
        else if (sel.type === 'file') {
            this.menu.close(BoxPointer.PopupAnimation.NONE);
            this._searchEngine.activateFileResult(sel.fileResult, this._searchEntry.get_text() || '', global.create_app_launch_context(global.get_current_time(), -1));
        }
    }

    _onMenuKeyPress(ev) {
        const sym = ev.get_key_symbol();
        if (sym === Clutter.KEY_Escape) {
            if (this._contextMenu.isOpen) { this._contextMenu.close(); return Clutter.EVENT_STOP; }
            if (this._groupModal.isOpen) { this._groupModal.close(); return Clutter.EVENT_STOP; }
            if (this._sidebarView.mode === 'jump') { this._sidebarView.resetMode(); this._sidebarDirty = true; this.renderCurrentView(); return Clutter.EVENT_STOP; }
            if (this._promptBars.hideAll()) return Clutter.EVENT_STOP;
            if (this._searchEntry.get_text()) { this._searchEntry.set_text(''); return Clutter.EVENT_STOP; }
            return Clutter.EVENT_PROPAGATE;
        }
        if (this._viewMode === 'search') {
            if (sym === Clutter.KEY_Down && this._boardView.moveSearchSelection(1)) return Clutter.EVENT_STOP;
            if (sym === Clutter.KEY_Up && this._boardView.moveSearchSelection(-1)) return Clutter.EVENT_STOP;
            if (sym === Clutter.KEY_Return || sym === Clutter.KEY_KP_Enter) { this._activateSearchSelection(); return Clutter.EVENT_STOP; }
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _openCtx(sx, sy, items) {
        this._hideTooltip();
        this._menuRootStack.set_child_above_sibling(this._contextMenu, null);
        this._contextMenu.openAt(sx, sy, { containerActor: this._menuRootStack, isRtl: this._isRtl, isLight: this._isLightTheme, items });
    }

    _runConfirmedAction(act) {
        if (act.kind === 'delete_group' && act.group) {
            if (this._groupModal.isOpen && this._groupModal.groupId === act.group.id) this._groupModal.close();
            this._appData.deleteGroup(act.group.id);
        } else if (act.kind === 'reset_layout') {
            this._groupModal.close();
            this._appData.resetLayout();
        }
    }

    _openNewGroupBar() {
        this._promptBars.openNewGroup();
        this._scheduleIdleFocus(() => this._promptBars.focusNewGroupEntry());
    }

    _showTooltip(actor, text) {
        this._tooltipLayer.showForActor(actor, text, this._menuRootStack, this._currentMenuW);
    }

    _hideTooltip(target = null) { this._tooltipLayer?.hideTooltip(target); }

    _scheduleIdleFocus(fn) {
        if (this._focusIdleId) GLib.source_remove(this._focusIdleId);
        this._focusIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => { this._focusIdleId = null; fn(); return GLib.SOURCE_REMOVE; });
    }

    _launchApp(rec, useDiscrete = false, forceNewWindow = false) {
        this._hideTooltip();
        this.menu.close(BoxPointer.PopupAnimation.NONE);
        try {
            const now = global.get_current_time();
            if (useDiscrete && rec.shellApp) rec.shellApp.launch(now, -1, Shell.AppLaunchGpu.DISCRETE);
            else if (forceNewWindow && rec.shellApp) rec.shellApp.open_new_window(-1);
            else if (rec.shellApp) rec.shellApp.activate();
            else if (rec.appInfo) rec.appInfo.launch([], global.create_app_launch_context(now, -1));
        } catch (err) { console.error(`[SadeemMenu] Failed launching ${rec?.id}: ${err}`); }
    }

    destroy() {
        this._onMenuClosed();
        this._dragManager?.destroy(); this._dragManager = null; this._resizeOverlay = null;
        if (this._focusIdleId) { GLib.source_remove(this._focusIdleId); this._focusIdleId = null; }
        if (this._openStateSigId) { try { this.menu.disconnect(this._openStateSigId); } catch (_e) {} this._openStateSigId = null; }
        if (this._keyPressSigId) { try { this.menu.actor.disconnect(this._keyPressSigId); } catch (_e) {} this._keyPressSigId = null; }
        for (const id of this._settingSignals) { try { this._settings.disconnect(id); } catch (_e) {} }
        this._settingSignals = [];
        if (this._ifaceSettings) { for (const id of this._ifaceSignals) { try { this._ifaceSettings.disconnect(id); } catch (_e) {} } this._ifaceSettings = null; }
        this._ifaceSignals = []; this._onOpenExtensionPrefs = null;
        super.destroy();
    }
}
