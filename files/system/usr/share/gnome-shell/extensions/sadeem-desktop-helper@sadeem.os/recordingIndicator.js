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

        // Container Pill Box
        this._box = new St.BoxLayout({
            style_class: 'sadeem-recording-pill',
            reactive: true,
            can_focus: true,
            style: 'background-color: rgba(220, 38, 38, 0.9); border: 1.5px solid rgba(255, 255, 255, 0.35); border-radius: 9999px; padding: 2px 10px; margin: 3px;',
        });

        // 1. Red Recording Dot (with pulse)
        this._dot = new St.Icon({
            icon_name: 'media-record-symbolic',
            icon_size: 12,
            style: 'color: #ffffff;',
        });
        this._box.add_child(this._dot);

        // 2. Timer Label (00:00)
        this._timerLabel = new St.Label({
            text: '00:00',
            y_align: Clutter.ActorAlign.CENTER,
            style: 'font-weight: bold; font-size: 12px; color: #ffffff; padding: 0 6px;',
        });
        this._box.add_child(this._timerLabel);

        // 3. Stop Icon
        this._stopIcon = new St.Icon({
            icon_name: 'media-playback-stop-symbolic',
            icon_size: 12,
            style: 'color: #ffffff;',
        });
        this._box.add_child(this._stopIcon);

        this.add_child(this._box);
        this.visible = false;

        // Clicking the indicator emits stop signal
        this.connect('button-press-event', () => {
            this._requestStop();
            return Clutter.EVENT_STOP;
        });

        this.connect('touch-event', () => {
            this._requestStop();
            return Clutter.EVENT_STOP;
        });
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
});
