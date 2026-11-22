import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { WindowMenu } from 'resource:///org/gnome/shell/ui/windowMenu.js';

const SCREENSHOT_LABELS = {
    ar: 'التقاط لقطة شاشة',
    en: 'Take Screenshot',
    fr: "Prendre une capture d'écran",
    es: 'Tomar captura de pantalla',
    de: 'Bildschirmfoto aufnehmen',
    tr: 'Ekran Görüntüsü Al',
    ru: 'Сделать снимок экрана',
    pt: 'Tirar captura de ecrã',
    it: 'Cattura schermata',
    zh: '截取屏幕',
};

function getSystemLanguage() {
    for (const key of ['LC_ALL', 'LC_MESSAGES', 'LANGUAGE', 'LANG']) {
        const val = GLib.getenv(key);
        if (val) {
            const code = val.split(':')[0].split('.')[0].split('_')[0].split('@')[0].toLowerCase();
            if (code in SCREENSHOT_LABELS) {
                return code;
            }
        }
    }
    return 'ar';
}

export class WindowMenuHelper {
    constructor() {
        this._origScreenshotOpen = null;
        this._origBuildMenu = null;
    }

    enable() {
        // 1. Reroute Main.screenshotUI.open to launch sadeem-capture
        const hookScreenshot = () => {
            if (Main.screenshotUI && !this._origScreenshotOpen) {
                this._origScreenshotOpen = Main.screenshotUI.open;
                this._origScreenshotOpenObj = Main.screenshotUI;
                Main.screenshotUI.open = function(...args) {
                    try {
                        GLib.spawn_command_line_async('sadeem-capture');
                    } catch (e) {
                        console.error('[WindowMenuHelper] Failed to launch sadeem-capture: ' + e);
                    }
                };
            }
        };

        hookScreenshot();
        if (!this._origScreenshotOpen) {
            this._idleHookId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                hookScreenshot();
                return GLib.SOURCE_REMOVE;
            });
        }

        // 2. Intercept WindowMenu._buildMenu
        if (WindowMenu && WindowMenu.prototype && !this._origBuildMenu) {
            this._origBuildMenu = WindowMenu.prototype._buildMenu;
            const self = this;

            WindowMenu.prototype._buildMenu = function(window) {
                self._origBuildMenu.call(this, window);
                self._enhanceWindowMenu(this, window);
            };
        }
    }

    disable() {
        if (this._idleHookId) {
            GLib.source_remove(this._idleHookId);
            this._idleHookId = null;
        }

        // Restore Main.screenshotUI.open
        if (this._origScreenshotOpen) {
            if (this._origScreenshotOpenObj) {
                this._origScreenshotOpenObj.open = this._origScreenshotOpen;
            } else if (Main.screenshotUI) {
                Main.screenshotUI.open = this._origScreenshotOpen;
            }
            this._origScreenshotOpen = null;
            this._origScreenshotOpenObj = null;
        }

        // Restore WindowMenu.prototype._buildMenu
        if (WindowMenu && WindowMenu.prototype && this._origBuildMenu) {
            WindowMenu.prototype._buildMenu = this._origBuildMenu;
            this._origBuildMenu = null;
        }
    }

    _enhanceWindowMenu(menu, window) {
        if (!menu || !window) return;

        const lang = getSystemLanguage();
        const localizedLabel = SCREENSHOT_LABELS[lang] || SCREENSHOT_LABELS.ar;
        const winId = window.get_id ? window.get_id() : window.get_stable_sequence();

        // Check if an existing screenshot menu item exists to replace/re-label
        let existingItem = null;
        const children = menu._getMenuItems ? menu._getMenuItems() : (menu.box ? menu.box.get_children() : []);

        for (const item of children) {
            if (item && item.label && item.label.get_text) {
                const txt = item.label.get_text().toLowerCase();
                if (txt.includes('screenshot') || txt.includes('شاشة') || txt.includes('capture') || txt.includes('bildschirmfoto')) {
                    existingItem = item;
                    break;
                }
            }
        }

        if (existingItem) {
            existingItem.label.set_text(localizedLabel);
            // Replace click action
            if (existingItem._sadeemCaptureHandler) {
                existingItem.disconnect(existingItem._sadeemCaptureHandler);
            }
            existingItem._sadeemCaptureHandler = existingItem.connect('activate', () => {
                menu.close();
                try {
                    GLib.spawn_command_line_async(`sadeem-capture --window-id ${winId}`);
                } catch (e) {
                    console.error('[WindowMenuHelper] Failed to launch sadeem-capture: ' + e);
                }
            });
        } else {
            // Append Take Screenshot item
            menu.addAction(localizedLabel, () => {
                menu.close();
                try {
                    GLib.spawn_command_line_async(`sadeem-capture --window-id ${winId}`);
                } catch (e) {
                    console.error('[WindowMenuHelper] Failed to launch sadeem-capture: ' + e);
                }
            });
        }
    }
}
