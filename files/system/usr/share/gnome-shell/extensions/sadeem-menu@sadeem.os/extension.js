// extension.js - GNOME 51 ESM entrypoint for Sadeem Menu (standalone uiGroup surface, no PopupMenu)
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import { AppDataManager } from './appData.js';
import { SadeemPanelButton } from './menuUI.js';
import { SearchEngine } from './searchEngine.js';

const MUTTER_SCHEMA = 'org.gnome.mutter';

class SuperOverlayBinder {
    constructor(onToggleMenu) {
        this._onToggleMenu = onToggleMenu;
        this._enabled = false;
        this._mutterSettings = new Gio.Settings({ schema_id: MUTTER_SCHEMA });
        this._savedOverlayKey = this._mutterSettings.get_value('overlay-key');
        this._defaultHandlerId = null;
        this._overlaySigId = null;
        this._startupSigId = null;
        this._ignoreChange = false;

        this._mutterChangedId = this._mutterSettings.connect('changed::overlay-key', () => {
            if (!this._ignoreChange)
                this._savedOverlayKey = this._mutterSettings.get_value('overlay-key');
        });
    }

    enable() {
        if (this._enabled)
            return;

        this._enabled = true;
        this._ignoreChange = true;
        try {
            this._mutterSettings.set_string('overlay-key', 'Super_L');
        } catch (_e) {}
        this._ignoreChange = false;

        Main.wm.allowKeybinding('overlay-key', Shell.ActionMode.ALL);

        if (Main.layoutManager?._startingUp) {
            this._startupSigId = Main.layoutManager.connect('startup-complete', () => {
                if (this._startupSigId) {
                    Main.layoutManager.disconnect(this._startupSigId);
                    this._startupSigId = null;
                }
                if (this._enabled)
                    this._hookOverlaySignal();
            });
        } else {
            this._hookOverlaySignal();
        }
    }

    _hookOverlaySignal() {
        if (this._overlaySigId)
            return;

        try {
            const defaultId = GObject.signal_handler_find(global.display, { signalId: 'overlay-key' });
            if (defaultId) {
                this._defaultHandlerId = defaultId;
                GObject.signal_handler_block(global.display, defaultId);
            }
        } catch (_e) {
            this._defaultHandlerId = null;
        }

        Main.wm.allowKeybinding('overlay-key', Shell.ActionMode.ALL);
        this._overlaySigId = global.display.connect('overlay-key', () => {
            this._onToggleMenu();
            Main.wm.allowKeybinding('overlay-key', Shell.ActionMode.ALL);
        });
    }

    disable() {
        if (!this._enabled)
            return;

        this._enabled = false;

        if (this._startupSigId) {
            try {
                Main.layoutManager.disconnect(this._startupSigId);
            } catch (_e) {}
            this._startupSigId = null;
        }

        if (this._overlaySigId) {
            try {
                global.display.disconnect(this._overlaySigId);
            } catch (_e) {}
            this._overlaySigId = null;
        }

        if (this._defaultHandlerId) {
            try {
                GObject.signal_handler_unblock(global.display, this._defaultHandlerId);
            } catch (_e) {}
            this._defaultHandlerId = null;
        }

        this._ignoreChange = true;
        try {
            this._mutterSettings.set_value('overlay-key', this._savedOverlayKey);
        } catch (_e) {}
        this._ignoreChange = false;

        try {
            Main.wm.allowKeybinding('overlay-key', Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW);
        } catch (_e) {}
    }

    destroy() {
        this.disable();
        if (this._mutterChangedId && this._mutterSettings) {
            try {
                this._mutterSettings.disconnect(this._mutterChangedId);
            } catch (_e) {}
            this._mutterChangedId = null;
        }
        this._mutterSettings = null;
        this._onToggleMenu = null;
    }
}

export default class SadeemMenuExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._signals = [];

        this._appSystem = Shell.AppSystem.get_default();
        this._appUsage = Shell.AppUsage.get_default();

        this._appData = new AppDataManager({
            settings: this._settings,
            appSystem: this._appSystem,
            appUsage: this._appUsage,
        });
        this._searchEngine = new SearchEngine();

        this._button = new SadeemPanelButton({
            settings: this._settings,
            appData: this._appData,
            searchEngine: this._searchEngine,
            onOpenExtensionPrefs: () => this._openSettings(),
        });

        Main.panel.addToStatusArea('sadeem-menu', this._button, 0, 'left');

        const instSig = this._appSystem.connect('installed-changed', () => {
            this._button?.markInstalledChanged();
            this._appData?.refreshSeenAppsAsync().then(() => {
                this._button?.refreshStripOnly();
            }).catch(() => {});
        });
        this._signals.push({ obj: this._appSystem, id: instSig });

        this._appData.refreshSeenAppsAsync().catch(() => {});

        // Optional Super key binding (disabled by default in Phase 1 to avoid ArcMenu conflict)
        this._superBinder = new SuperOverlayBinder(() => this._button?.menu?.toggle());
        this._syncSuperKeyBinding();

        const superSig = this._settings.connect('changed::bind-super-key', () => {
            this._syncSuperKeyBinding();
        });
        this._signals.push({ obj: this._settings, id: superSig });
    }

    _syncSuperKeyBinding() {
        if (this._settings?.get_boolean('bind-super-key'))
            this._superBinder?.enable();
        else
            this._superBinder?.disable();
    }

    _openSettings() {
        try {
            if (GLib.find_program_in_path('sadeem-system')) {
                GLib.spawn_command_line_async('sadeem-system --page=menu');
                return;
            }
            this.openPreferences?.();
        } catch (_e) {}
    }

    disable() {
        for (const sig of (this._signals || [])) {
            try {
                sig.obj.disconnect(sig.id);
            } catch (_e) {}
        }
        this._signals = [];

        this._superBinder?.destroy();
        this._superBinder = null;

        this._button?.destroy();
        this._button = null;

        if (Main.panel?.statusArea && 'sadeem-menu' in Main.panel.statusArea)
            delete Main.panel.statusArea['sadeem-menu'];

        this._searchEngine?.destroy();
        this._searchEngine = null;

        this._appData?.destroy();
        this._appData = null;

        this._appSystem = null;
        this._appUsage = null;
        this._settings = null;
    }
}
