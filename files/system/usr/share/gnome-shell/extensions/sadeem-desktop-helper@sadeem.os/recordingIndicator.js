import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

export const RecordingIndicator = GObject.registerClass(
class RecordingIndicator extends PanelMenu.Button {
    _init(captureHelper) {
        super._init(0.5, 'Sadeem Recording Indicator', false);
        this._captureHelper = captureHelper;
        this._timerSourceId = null;
        this._elapsedSeconds = 0;
        this._watchId = null;

        this.y_align = Clutter.ActorAlign.CENTER;

        // Container Pill Box with two adjacent buttons
        this._box = new St.BoxLayout({
            style_class: 'sadeem-recording-pill',
            reactive: true,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'background-color: rgba(220, 38, 38, 0.95); border: 1px solid rgba(255, 255, 255, 0.4); border-radius: 9999px; padding: 1px 3px; margin: 2px 4px;',
        });

        // 1. Silent Camera Snapshot Button
        this._camBtn = new St.Button({
            style_class: 'button sadeem-cam-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'padding: 3px 7px; border-radius: 9999px; background-color: rgba(255, 255, 255, 0.15); margin-right: 2px;',
        });
        this._camBtn.set_accessible_name('Silent Screenshot (Print)');
        this._camIcon = new St.Icon({
            icon_name: 'camera-photo-symbolic',
            icon_size: 13,
            style: 'color: #ffffff;',
        });
        this._camBtn.set_child(this._camIcon);
        this._camBtn.connect('clicked', () => {
            this._requestSnapshot();
            return Clutter.EVENT_STOP;
        });
        this._box.add_child(this._camBtn);

        // Thin subtle divider
        this._divider = new St.Widget({
            style: 'width: 1px; height: 14px; background-color: rgba(255, 255, 255, 0.35); margin: 2px 2px;',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._box.add_child(this._divider);

        // 2. Stop Recording Pill Button (Dot + Timer + Stop Icon)
        this._stopBtn = new St.Button({
            style_class: 'button sadeem-stop-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'padding: 3px 6px; border-radius: 9999px; background-color: transparent;',
        });
        this._stopBtn.set_accessible_name('Stop Recording (Shift+Print)');

        const stopInnerBox = new St.BoxLayout({
            y_align: Clutter.ActorAlign.CENTER,
        });

        // Red Recording Dot (with pulse)
        this._dot = new St.Icon({
            icon_name: 'media-record-symbolic',
            icon_size: 11,
            style: 'color: #ffffff; margin-right: 4px;',
        });
        stopInnerBox.add_child(this._dot);

        // Timer Label (00:00)
        this._timerLabel = new St.Label({
            text: '00:00',
            y_align: Clutter.ActorAlign.CENTER,
            style: 'font-weight: bold; font-size: 12px; color: #ffffff; padding: 0 4px;',
        });
        stopInnerBox.add_child(this._timerLabel);

        // Stop Icon
        this._stopIcon = new St.Icon({
            icon_name: 'media-playback-stop-symbolic',
            icon_size: 11,
            style: 'color: #ffffff; margin-left: 4px;',
        });
        stopInnerBox.add_child(this._stopIcon);

        this._stopBtn.set_child(stopInnerBox);
        this._stopBtn.connect('clicked', () => {
            this._requestStop();
            return Clutter.EVENT_STOP;
        });
        this._box.add_child(this._stopBtn);

        this.add_child(this._box);
        this.visible = false;
    }

    enable() {
        if (Main.panel && Main.panel.addToStatusArea) {
            Main.panel.addToStatusArea('sadeem-recording-indicator', this, 1, 'right');
        }

        // Auto-cleanup: watch org.sadeem.Capture on session bus
        // If the recording application quits or crashes, hide the indicator automatically
        try {
            this._watchId = Gio.bus_watch_name(
                Gio.BusType.SESSION,
                'org.sadeem.Capture',
                Gio.BusNameWatcherFlags.NONE,
                null,
                () => {
                    // Name vanished
                    if (this.visible) {
                        this.setRecordingActive(false);
                    }
                }
            );
        } catch (e) {
            // Bus watch fallback
        }
    }

    disable() {
        this.setRecordingActive(false);

        if (this._watchId) {
            try {
                Gio.bus_unwatch_name(this._watchId);
            } catch (e) {}
            this._watchId = null;
        }

        this.destroy();
    }

    setRecordingActive(active) {
        if (active) {
            this._elapsedSeconds = 0;
            this._updateTimerDisplay();
            this.visible = true;

            if (!this._timerSourceId) {
                let pulseState = false;
                this._timerSourceId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
                    this._elapsedSeconds += 1;
                    this._updateTimerDisplay();

                    // Subtle dot pulse
                    pulseState = !pulseState;
                    if (this._dot) {
                        this._dot.opacity = pulseState ? 140 : 255;
                    }
                    return GLib.SOURCE_CONTINUE;
                });
            }
        } else {
            this.visible = false;
            if (this._timerSourceId) {
                GLib.source_remove(this._timerSourceId);
                this._timerSourceId = null;
            }
            if (this._dot) {
                this._dot.opacity = 255;
            }
        }
    }

    _updateTimerDisplay() {
        const mins = Math.floor(this._elapsedSeconds / 60);
        const secs = this._elapsedSeconds % 60;
        const mm = String(mins).padStart(2, '0');
        const ss = String(secs).padStart(2, '0');
        if (this._timerLabel) {
            this._timerLabel.set_text(`${mm}:${ss}`);
        }
    }

    _requestStop() {
        if (this._captureHelper && this._captureHelper.emitStopRecordingRequested) {
            this._captureHelper.emitStopRecordingRequested();
        }
    }

    _requestSnapshot() {
        this.flashCameraIcon();
        if (this._captureHelper && this._captureHelper.emitSilentScreenshotRequested) {
            this._captureHelper.emitSilentScreenshotRequested();
        }
    }

    flashCameraIcon() {
        if (!this._camIcon) return;
        this._camIcon.opacity = 60;
        if (this._camBtn) {
            this._camBtn.style = 'padding: 3px 7px; border-radius: 9999px; background-color: rgba(255, 255, 255, 0.7); margin-right: 2px;';
        }
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 220, () => {
            if (this._camIcon) {
                this._camIcon.opacity = 255;
            }
            if (this._camBtn) {
                this._camBtn.style = 'padding: 3px 7px; border-radius: 9999px; background-color: rgba(255, 255, 255, 0.15); margin-right: 2px;';
            }
            return GLib.SOURCE_REMOVE;
        });
    }
});
