import GLib from 'gi://GLib';
import { WindowMenu } from 'resource:///org/gnome/shell/ui/windowMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

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

const MATCH_TOKENS = [
    'screenshot',
    'شاشة',
    'لقطة',
    'capture',
    'captura',
    'bildschirmfoto',
    'ekran',
    'снимок',
    'schermata',
    '截',
];

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
    constructor(captureUI = null) {
        this._captureUI = captureUI;
        this._origBuildMenu = null;
    }

    setCaptureUI(captureUI) {
        this._captureUI = captureUI;
    }

    enable() {
        // Intercept WindowMenu._buildMenu to add/enhance Take Screenshot action
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

        // Find GNOME Shell's built-in "Take Screenshot" menu item so we can replace it completely.
        // Reusing it in-place leaves GNOME's original activate handler (Screenshot.captureScreenshot)
        // connected, causing every click to save a duplicate "Screenshot From ..." file.
        let existingItem = null;
        let existingIdx = -1;
        const children = menu._getMenuItems ? menu._getMenuItems() : (menu.box ? menu.box.get_children() : []);

        for (let i = 0; i < children.length; i++) {
            const item = children[i];
            if (item?._isSadeemCaptureItem) {
                existingItem = item;
                existingIdx = i;
                break;
            }
            const txt = item?.label?.get_text ? item.label.get_text().toLowerCase() : '';
            if (txt && MATCH_TOKENS.some(tok => txt.includes(tok))) {
                existingItem = item;
                existingIdx = i;
                break;
            }
        }

        const triggerCapture = () => {
            menu.close();
            if (this._captureUI && typeof this._captureUI.captureWindowNow === 'function') {
                this._captureUI.captureWindowNow(winId);
                return;
            }
            try {
                GLib.spawn_command_line_async(`sadeem-capture --window-id ${winId}`);
            } catch (e) {
                console.error('[WindowMenuHelper] Failed to launch sadeem-capture: ' + e);
            }
        };

        if (existingItem) {
            try {
                existingItem.destroy();
            } catch (_e) {}
        }

        const newItem = new PopupMenu.PopupMenuItem(localizedLabel);
        newItem._isSadeemCaptureItem = true;
        newItem.connect('activate', triggerCapture);
        if (typeof menu.addMenuItem === 'function') {
            if (existingIdx >= 0) {
                menu.addMenuItem(newItem, existingIdx);
            } else {
                menu.addMenuItem(newItem);
            }
        } else if (typeof menu.addAction === 'function') {
            menu.addAction(localizedLabel, triggerCapture);
        }
    }
}
