import Clutter from 'gi://Clutter';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export class CursorHaloManager {
    constructor() {
        this._actor = null;
        this._capturedEventId = null;
        this._isActive = false;
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
        if (Main.layoutManager && Main.layoutManager.uiGroup) {
            Main.layoutManager.uiGroup.add_child(this._actor);
        }
    }

    disable() {
        this.setActive(false);
        if (this._actor) {
            this._actor.destroy();
            this._actor = null;
        }
    }

    setActive(active) {
        this._isActive = Boolean(active);
        if (!this._actor) return;

        if (this._isActive) {
            this._actor.visible = true;
            this._updatePosition();
            if (!this._capturedEventId && global.stage) {
                this._capturedEventId = global.stage.connect('captured-event', (stage, event) => {
                    const type = event.type();
                    if (type === Clutter.EventType.MOTION) {
                        this._updatePosition();
                    } else if (type === Clutter.EventType.BUTTON_PRESS) {
                        this._pulse();
                    }
                    return Clutter.EVENT_PROPAGATE;
                });
            }
        } else {
            this._actor.visible = false;
            if (this._capturedEventId && global.stage) {
                global.stage.disconnect(this._capturedEventId);
                this._capturedEventId = null;
            }
        }
    }

    _updatePosition() {
        if (!this._actor || !this._isActive) return;
        const [x, y] = global.get_pointer();
        this._actor.set_position(x - 24, y - 24);
    }

    _pulse() {
        if (!this._actor || !this._isActive) return;
        this._actor.ease({
            scale_x: 1.35,
            scale_y: 1.35,
            duration: 100,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._actor) {
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
