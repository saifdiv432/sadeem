import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import { AppMenu } from 'resource:///org/gnome/shell/ui/appMenu.js';
import { CursorHaloManager } from './cursorHalo.js';
import { CaptureHelperService } from './captureHelper.js';
import { CaptureUI } from './captureUI.js';
import { WindowMenuHelper } from './windowMenuHelper.js';
import { RecordingIndicator } from './recordingIndicator.js';

const RTL_ELEMENTS = [
    { element: 'desktopButton', visible: true, position: 'stackedTL' },
    { element: 'systemMenu', visible: true, position: 'stackedTL' },
    { element: 'dateMenu', visible: true, position: 'stackedTL' },
    { element: 'rightBox', visible: true, position: 'stackedTL' },
    { element: 'centerBox', visible: true, position: 'stackedTL' },
    { element: 'taskbar', visible: true, position: 'stackedBR' },
    { element: 'leftBox', visible: true, position: 'stackedBR' },
    { element: 'showAppsButton', visible: false, position: 'stackedBR' },
    { element: 'activitiesButton', visible: false, position: 'stackedBR' },
];

const LTR_ELEMENTS = [
    { element: 'desktopButton', visible: true, position: 'stackedTL' },
    { element: 'showAppsButton', visible: false, position: 'stackedTL' },
    { element: 'activitiesButton', visible: false, position: 'stackedTL' },
    { element: 'leftBox', visible: true, position: 'stackedTL' },
    { element: 'taskbar', visible: true, position: 'stackedTL' },
    { element: 'centerBox', visible: true, position: 'stackedBR' },
    { element: 'rightBox', visible: true, position: 'stackedBR' },
    { element: 'dateMenu', visible: true, position: 'stackedBR' },
    { element: 'systemMenu', visible: true, position: 'stackedBR' },
];

const UNINSTALL_LABELS = {
    ar: 'إلغاء التثبيت',
    en: 'Uninstall',
    fr: 'Désinstaller',
    es: 'Desinstalar',
    de: 'Deinstallieren',
    tr: 'Kaldır',
    ru: 'Удалить',
    pt: 'Desinstalar',
    it: 'Disinstalla',
    zh: '卸载',
};

function getUninstallLabel() {
    try {
        const langs = GLib.get_language_names();
        for (const l of langs) {
            const code = l.split('.')[0].split('_')[0].toLowerCase();
            if (UNINSTALL_LABELS[code]) {
                return UNINSTALL_LABELS[code];
            }
        }
    } catch (e) {}
    return 'Uninstall';
}

const CORE_CRITICAL_EXCLUSIONS = new Set([
    'org.gnome.Settings',
    'org.gnome.Nautilus',
    'org.gnome.Software',
    'org.gnome.Shell.Extensions',
    'org.gnome.Ptyxis',
    'gnome-initial-setup',
    'rumman',
]);

function isCoreExcluded(cleanId) {
    if (!cleanId) return true;
    if (cleanId.startsWith('org.sadeem.') || cleanId.startsWith('sadeem-')) return true;
    if (CORE_CRITICAL_EXCLUSIONS.has(cleanId)) return true;
    if (CORE_CRITICAL_EXCLUSIONS.has(cleanId.toLowerCase())) return true;
    return false;
}

export default class SadeemDesktopHelperExtension extends Extension {
    enable() {
        this._signals = [];
        this._hookedMenus = new Map();
        this._interfaceSettings = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });

        // 1. Initial panel RTL/LTR orientation
        this._updatePanelPositions();

        // 2. Listen for text-direction and locale changes
        if (global.stage) {
            const stageSig = global.stage.connect('notify::text-direction', () => {
                this._updatePanelPositions();
            });
            this._signals.push({ obj: global.stage, id: stageSig });
        }

        const ifaceSig = this._interfaceSettings.connect('changed', () => {
            this._updatePanelPositions();
        });
        this._signals.push({ obj: this._interfaceSettings, id: ifaceSig });

        // 3. Setup cursor anchoring for clipboard and emoji menus
        this._setupCursorPopups();

        if (Main.extensionManager) {
            const extSig = Main.extensionManager.connect('extension-state-changed', () => {
                this._setupCursorPopups();
            });
            this._signals.push({ obj: Main.extensionManager, id: extSig });
        }

        // 4. Layered packages async cache
        this._layeredPackages = new Set();
        this._queryLayeredPackagesAsync();

        // 5. Hook AppMenu for context menu "Uninstall" option
        this._hookAppMenu();

        // 6. Hook Quick Settings screenshot button to launch sadeem-capture
        this._hookQuickSettingsScreenshot();

        // 7. Wayland screen capture bridge, cursor halo, recording indicator, capture UI, and window menu capture
        this._cursorHalo = new CursorHaloManager();
        this._cursorHalo.enable();

        this._recordingIndicator = new RecordingIndicator();
        this._recordingIndicator.enable();

        this._captureUI = new CaptureUI(null, this._cursorHalo, this._recordingIndicator);

        this._captureHelper = new CaptureHelperService(this._cursorHalo, this._recordingIndicator, this._captureUI);
        this._captureHelper.enable();

        this._captureUI._captureHelper = this._captureHelper;
        this._recordingIndicator.setCaptureUI(this._captureUI);
        this._recordingIndicator._captureHelper = this._captureHelper;

        this._windowMenuHelper = new WindowMenuHelper(this._captureUI);
        this._windowMenuHelper.enable();
    }

    disable() {
        // Disconnect all registered signals
        if (this._signals) {
            for (const sig of this._signals) {
                try {
                    sig.obj.disconnect(sig.id);
                } catch (e) {
                    // Ignore already disconnected signals
                }
            }
            this._signals = [];
        }

        // Restore hooked indicator menus
        if (this._hookedMenus) {
            for (const [menu, originalOpen] of this._hookedMenus.entries()) {
                try {
                    menu.open = originalOpen;
                    if (menu._sadeemIndicator) {
                        menu.sourceActor = menu._sadeemIndicator;
                        delete menu._sadeemIndicator;
                    }
                } catch (e) {
                    // Ignore errors during cleanup
                }
            }
            this._hookedMenus.clear();
        }

        // Restore AppMenu.prototype.open
        if (this._origAppMenuOpen) {
            AppMenu.prototype.open = this._origAppMenuOpen;
            this._origAppMenuOpen = null;
        }

        // Restore Main.screenshotUI.open
        if (this._origScreenshotUIOpen && Main.screenshotUI) {
            Main.screenshotUI.open = this._origScreenshotUIOpen;
            this._origScreenshotUIOpen = null;
        }

        this._layeredPackages = null;

        // 5. Disable Capture UI, Capture Helper, Recording Indicator, Cursor Halo, and Window Menu
        if (this._captureUI) {
            this._captureUI.destroy();
            this._captureUI = null;
        }

        if (this._windowMenuHelper) {
            this._windowMenuHelper.disable();
            this._windowMenuHelper = null;
        }

        if (this._captureHelper) {
            this._captureHelper.disable();
            this._captureHelper = null;
        }

        if (this._recordingIndicator) {
            this._recordingIndicator.disable();
            this._recordingIndicator = null;
        }

        if (this._cursorHalo) {
            this._cursorHalo.disable();
            this._cursorHalo = null;
        }

        this._interfaceSettings = null;
    }

    _updatePanelPositions() {
        try {
            const schemaSource = Gio.SettingsSchemaSource.get_default();
            if (!schemaSource || !schemaSource.lookup('org.gnome.shell.extensions.dash-to-panel', true)) {
                return;
            }

            const isRtl = Clutter.get_default_text_direction() === Clutter.TextDirection.RTL;
            const elements = isRtl ? RTL_ELEMENTS : LTR_ELEMENTS;

            const dtpSettings = new Gio.Settings({ schema_id: 'org.gnome.shell.extensions.dash-to-panel' });
            let currentRaw = dtpSettings.get_string('panel-element-positions');
            let currentObj = {};
            try {
                currentObj = JSON.parse(currentRaw || '{}');
            } catch (e) {
                currentObj = {};
            }

            let changed = false;

            // Ensure monitors sync setting
            try {
                if (!dtpSettings.get_boolean('panel-element-positions-monitors-sync')) {
                    dtpSettings.set_boolean('panel-element-positions-monitors-sync', true);
                }
            } catch (e) {}

            // Update all existing monitor keys (connectors or IDs)
            for (const key of Object.keys(currentObj)) {
                const existingStr = JSON.stringify(currentObj[key] || []);
                const newStr = JSON.stringify(elements);
                if (existingStr !== newStr) {
                    currentObj[key] = elements;
                    changed = true;
                }
            }

            // Also guarantee monitors 0 through 7
            for (let i = 0; i < 8; i++) {
                const key = String(i);
                const existingStr = JSON.stringify(currentObj[key] || []);
                const newStr = JSON.stringify(elements);
                if (existingStr !== newStr) {
                    currentObj[key] = elements;
                    changed = true;
                }
            }

            if (changed) {
                dtpSettings.set_string('panel-element-positions', JSON.stringify(currentObj));
            }
        } catch (e) {
            console.error('[SadeemDesktopHelper] Error updating panel positions: ' + e);
        }
    }

    _setupCursorPopups() {
        try {
            if (!Main.panel || !Main.panel.statusArea) return;

            const indicators = [
                Main.panel.statusArea.clipboardIndicator,
                Main.panel.statusArea['clipboard-indicator@tudmotu.com'],
                Main.panel.statusArea['emoji-copy@felipeftn'],
                Main.panel.statusArea.emojiCopy,
            ];

            for (const ind of indicators) {
                if (ind && ind.menu && !this._hookedMenus.has(ind.menu)) {
                    this._hookMenuToCursor(ind, ind.menu);
                }
            }
        } catch (e) {
            console.error('[SadeemDesktopHelper] Error setting up cursor popups: ' + e);
        }
    }

    _hookMenuToCursor(indicator, menu) {
        const originalOpen = menu.open;
        menu._sadeemIndicator = indicator;
        this._hookedMenus.set(menu, originalOpen);

        menu.open = function(animate) {
            try {
                if (global.get_pointer && Main.layoutManager.dummyCursor) {
                    const [x, y] = global.get_pointer();
                    Main.layoutManager.dummyCursor.set_position(x, y);
                    menu.sourceActor = Main.layoutManager.dummyCursor;
                }
            } catch (err) {
                console.error('[SadeemDesktopHelper] Error anchoring to cursor: ' + err);
            }
            return originalOpen.call(this, animate);
        };
    }

    _hookAppMenu() {
        if (!this._origAppMenuOpen) {
            this._origAppMenuOpen = AppMenu.prototype.open;
            const self = this;

            AppMenu.prototype.open = function(animate) {
                try {
                    self._injectUninstallerItem(this);
                } catch (e) {
                    console.error('[SadeemDesktopHelper] Error injecting uninstaller item in AppMenu: ' + e);
                }
                return self._origAppMenuOpen.call(this, animate);
            };
        }
    }

    _hookQuickSettingsScreenshot() {
        if (this._origScreenshotUIOpen) return;

        if (Main.screenshotUI && Main.screenshotUI.open) {
            this._origScreenshotUIOpen = Main.screenshotUI.open;
            const self = this;
            Main.screenshotUI.open = async function(mode) {
                try {
                    if (Main.panel.closeQuickSettings) {
                        Main.panel.closeQuickSettings();
                    } else if (Main.panel.statusArea.quickSettings?.menu) {
                        Main.panel.statusArea.quickSettings.menu.close(BoxPointer.PopupAnimation.NONE);
                    }
                } catch (e) {}

                if (self._captureUI) {
                    self._captureUI.open(mode || 'selection');
                    return;
                }

                return self._origScreenshotUIOpen.call(this, mode);
            };
        }
    }

    _queryLayeredPackagesAsync() {
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
                        const deployments = data?.deployments || [];
                        if (deployments.length > 0) {
                            const req = deployments[0]['requested-packages'] || [];
                            const layered = deployments[0]['layered-packages'] || [];
                            this._layeredPackages = new Set([...req, ...layered]);
                        }
                    }
                } catch (e) {
                    // Silently ignore background status parse error
                }
            });
        } catch (e) {
            // Silently ignore if rpm-ostree is unavailable
        }
    }

    _canUninstallApp(appId) {
        if (!appId) return false;
        try {
            const cleanId = appId.endsWith('.desktop') ? appId.slice(0, -8) : appId;

            // 1. Instant core system exclusions
            if (isCoreExcluded(cleanId)) {
                return false;
            }

            // 2. Instant directory check for Flatpak (system or user)
            const home = GLib.get_home_dir();
            if (GLib.file_test(`/var/lib/flatpak/app/${cleanId}`, GLib.FileTest.IS_DIR) ||
                GLib.file_test(`${home}/.local/share/flatpak/app/${cleanId}`, GLib.FileTest.IS_DIR) ||
                GLib.file_test(`/var/lib/flatpak/exports/share/applications/${cleanId}.desktop`, GLib.FileTest.EXISTS) ||
                GLib.file_test(`${home}/.local/share/flatpak/exports/share/applications/${cleanId}.desktop`, GLib.FileTest.EXISTS)) {
                return true;
            }

            // 3. Instant check for user desktop files
            if (GLib.file_test(`${home}/.local/share/applications/${cleanId}.desktop`, GLib.FileTest.EXISTS)) {
                return true;
            }

            // 4. In-memory check for layered rpm-ostree packages from background query
            if (this._layeredPackages && this._layeredPackages.has(cleanId)) {
                return true;
            }
        } catch (e) {
            console.error('[SadeemDesktopHelper] _canUninstallApp error: ' + e);
        }
        return false;
    }

    _injectUninstallerItem(menu) {
        try {
            const app = menu._app || menu.sourceActor?.app || menu.sourceActor?._app;
            if (!app) return;

            const appId = app.get_id ? app.get_id() : (app.id || '');
            if (!appId) return;

            const canUninstall = this._canUninstallApp(appId);

            if (!canUninstall) {
                if (menu._sadeemUninstallItem) {
                    menu._sadeemUninstallItem.visible = false;
                }
                if (menu._sadeemUninstallSep) {
                    menu._sadeemUninstallSep.visible = false;
                }
                return;
            }

            const labelText = getUninstallLabel();

            if (menu._sadeemUninstallItem) {
                if (menu._sadeemUninstallItem.label) {
                    menu._sadeemUninstallItem.label.text = labelText;
                }
                menu._sadeemUninstallItem.visible = true;
                if (menu._sadeemUninstallSep) {
                    menu._sadeemUninstallSep.visible = true;
                }
                return;
            }

            // Create separator and uninstaller action item
            const sep = new PopupMenu.PopupSeparatorMenuItem();
            menu.addMenuItem(sep);

            const item = menu.addAction(labelText, () => {
                try {
                    if (typeof menu.closeMenus === 'function') {
                        menu.closeMenus();
                    } else {
                        menu.close();
                    }
                } catch (ce) {}
                try {
                    GLib.spawn_command_line_async(`sadeem-uninstaller ${GLib.shell_quote(appId)}`);
                } catch (err) {
                    console.error('[SadeemDesktopHelper] Failed to launch uninstaller: ' + err);
                }
            });

            const trashIcon = new St.Icon({
                icon_name: 'user-trash-symbolic',
                style_class: 'popup-menu-icon',
            });

            try {
                item.insert_child_at_index(trashIcon, 0);
            } catch (e) {
                item.add_child(trashIcon);
            }

            item.add_style_class_name('destructive-action');
            item.style = 'color: #e01b24;';
            trashIcon.style = 'color: #e01b24;';

            menu._sadeemUninstallItem = item;
            menu._sadeemUninstallSep = sep;
        } catch (err) {
            console.error('[SadeemDesktopHelper] Error in _injectUninstallerItem: ' + err);
        }
    }
}
