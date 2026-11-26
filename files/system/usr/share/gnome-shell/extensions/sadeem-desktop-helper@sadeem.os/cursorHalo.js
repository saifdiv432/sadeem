import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export class CursorHaloManager {
    constructor() {
        this._actor = null;
        this._cursorTracker = null;
        this._cursorSigId = null;
        this._capturedEventId = null;
        this._wasPrimaryPressed = false;
        this._isActive = false;
    }

    _getCursorTracker() {
        try {
            if (global.backend && typeof global.backend.get_cursor_tracker === 'function')
                return global.backend.get_cursor_tracker();
        } catch (_e) {}
        try {
            if (typeof Meta.CursorTracker?.get_for_display === 'function' && global.display)
                return Meta.CursorTracker.get_for_display(global.display);
        } catch (_e) {}
        return null;
    }

    _readPointerAndMods() {
        if (this._cursorTracker && typeof this._cursorTracker.get_pointer === 'function') {
            try {
                const [coords, mods] = this._cursorTracker.get_pointer();
                if (coords && Number.isFinite(coords.x) && Number.isFinite(coords.y))
                    return [coords.x, coords.y, mods || 0];
            } catch (_e) {}
        }
        try {
            const [x, y, mods] = global.get_pointer();
            return [x, y, mods || 0];
        } catch (_e) {}
        return [0, 0, 0];
    }

    enable() {
        this._actor = new St.Widget({
            name: 'sadeem-cursor-halo',
            reactive: false,
            can_focus: false,
            visible: false,
            width: 48,
            height: 48,
            style: 'background-color: rgba(6, 182, 212, 0.3); border: 2.5px solid rgba(6, 182, 212, 0.85); border-radius: 9999px;',
        });
        this._actor.set_pivot_point(0.5, 0.5);
        if (Main.layoutManager && Main.layoutManager.uiGroup)
            Main.layoutManager.uiGroup.add_child(this._actor);
    }

    disable() {
        this.setActive(false);
        this._cursorTracker = null;
        if (this._actor) {
            this._actor.destroy();
            this._actor = null;
        }
    }

    setActive(active) {
        this._isActive = Boolean(active);
        if (!this._actor)
            return;

        if (this._isActive) {
            this._cursorTracker = this._getCursorTracker();
            this._wasPrimaryPressed = false;
            if (Main.layoutManager?.uiGroup && this._actor.get_parent() === Main.layoutManager.uiGroup)
                Main.layoutManager.uiGroup.set_child_above_sibling(this._actor, null);
            this._actor.visible = true;
            this._updatePosition(false);

            if (!this._cursorSigId && this._cursorTracker) {
                this._cursorSigId = this._cursorTracker.connect('position-invalidated', () => {
                    this._updatePosition(true);
                });
            }
            if (!this._capturedEventId && global.stage) {
                this._capturedEventId = global.stage.connect('captured-event', (_stage, event) => {
                    const type = event.type();
                    if (type === Clutter.EventType.BUTTON_PRESS) {
                        if (!this._wasPrimaryPressed)
                            this._pulse();
                        this._wasPrimaryPressed = true;
                    } else if (type === Clutter.EventType.BUTTON_RELEASE) {
                        this._wasPrimaryPressed = false;
                    }
                    return Clutter.EVENT_PROPAGATE;
                });
            }
        } else {
            this._wasPrimaryPressed = false;
            this._actor.remove_all_transitions?.();
            this._actor.set_scale(1.0, 1.0);
            this._actor.visible = false;
            if (this._cursorSigId && this._cursorTracker) {
                try { this._cursorTracker.disconnect(this._cursorSigId); } catch (_e) {}
                this._cursorSigId = null;
            }
            if (this._capturedEventId && global.stage) {
                try { global.stage.disconnect(this._capturedEventId); } catch (_e) {}
                this._capturedEventId = null;
            }
        }
    }

    _updatePosition(checkClickMask = false) {
        if (!this._actor || !this._isActive)
            return;
        const [x, y, mods] = this._readPointerAndMods();
        this._actor.set_position(Math.round(x - 24), Math.round(y - 24));
        if (checkClickMask) {
            const primaryDown = (mods & Clutter.ModifierType.BUTTON1_MASK) !== 0;
            if (primaryDown && !this._wasPrimaryPressed)
                this._pulse();
            this._wasPrimaryPressed = primaryDown;
        }
    }

    _pulse() {
        if (!this._actor || !this._isActive)
            return;
        this._actor.remove_all_transitions?.();
        this._actor.ease({
            scale_x: 1.35,
            scale_y: 1.35,
            duration: 100,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._actor && this._isActive) {
                    this._actor.ease({
                        scale_x: 1.0,
                        scale_y: 1.0,
                        duration: 120,
                        mode: Clutter.AnimationMode.EASE_IN_QUAD,
                    });
                }
            },
        });
    }
}
