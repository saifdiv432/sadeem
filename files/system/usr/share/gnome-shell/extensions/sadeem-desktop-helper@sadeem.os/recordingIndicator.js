import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

export const RecordingIndicator = GObject.registerClass(
class RecordingIndicator extends PanelMenu.Button {
    _init(captureHelper = null, captureUI = null) {
        super._init(0.5, 'Sadeem Recording Indicator', true);
        this._captureHelper = captureHelper;
        this._captureUI = captureUI;
        this._timerSourceId = null;
        this._elapsedSeconds = 0;
        this._watchId = null;
        this._gnomeIndicatorWatches = [];
        this._indicatorSuppressed = false;
        this._restoreTimerId = null;
        this._flashTimerId = null;

        this.reactive = false;
        this.can_focus = false;
        this.track_hover = false;
        this.y_align = Clutter.ActorAlign.CENTER;

        // Container Pill Box with two adjacent buttons
        this._box = new St.BoxLayout({
            style_class: 'sadeem-recording-pill',
            reactive: false,
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
            reactive: false,
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
            reactive: false,
            y_align: Clutter.ActorAlign.CENTER,
        });

        // Red Recording Dot (with pulse)
        this._dot = new St.Icon({
            icon_name: 'media-record-symbolic',
            icon_size: 11,
            reactive: false,
            style: 'color: #ffffff; margin-right: 4px;',
        });
        stopInnerBox.add_child(this._dot);

        // Timer Label (00:00)
        this._timerLabel = new St.Label({
            text: '00:00',
            reactive: false,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'font-weight: bold; font-size: 12px; color: #ffffff; padding: 0 4px;',
        });
        stopInnerBox.add_child(this._timerLabel);

        // Stop Icon
        this._stopIcon = new St.Icon({
            icon_name: 'media-playback-stop-symbolic',
            icon_size: 11,
            reactive: false,
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

    setCaptureUI(captureUI) {
        this._captureUI = captureUI;
    }

    enable() {
        if (Main.panel && Main.panel.addToStatusArea) {
            Main.panel.addToStatusArea('sadeem-recording-indicator', this, 1, 'right');
        }

        // Auto-cleanup: watch org.sadeem.Capture on session bus
        try {
            this._watchId = Gio.bus_watch_name(
                Gio.BusType.SESSION,
                'org.sadeem.Capture',
                Gio.BusNameWatcherFlags.NONE,
                null,
                () => {
                    if (this.visible && !this._captureUI?._isRecording) {
                        this.setRecordingActive(false);
                    }
                }
            );
        } catch (e) {
            // Bus watch fallback
        }
    }

    disable() {
        if (this._flashTimerId) {
            GLib.source_remove(this._flashTimerId);
            this._flashTimerId = null;
        }
        if (this._restoreTimerId) {
            GLib.source_remove(this._restoreTimerId);
            this._restoreTimerId = null;
        }
        if (this._timerSourceId) {
            GLib.source_remove(this._timerSourceId);
            this._timerSourceId = null;
        }

        this._indicatorSuppressed = false;
        this.setRecordingActive(false);
        this._restoreGnomeIndicators();

        if (this._watchId) {
            try {
                Gio.bus_unwatch_name(this._watchId);
            } catch (e) {}
            this._watchId = null;
        }

        this.destroy();
    }

    setGnomeIndicatorSuppressed(suppressed) {
        if (this._restoreTimerId) {
            GLib.source_remove(this._restoreTimerId);
            this._restoreTimerId = null;
        }

        if (suppressed) {
            this._indicatorSuppressed = true;
            this._suppressGnomeIndicators();
        } else {
            this._indicatorSuppressed = false;
            // Safe 500ms delay to prevent yellow indicator flash during Mutter screencast teardown
            this._restoreTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
                this._restoreTimerId = null;
                if (!this._indicatorSuppressed && !this.visible) {
                    this._restoreGnomeIndicators();
                }
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    setRecordingActive(active) {
        if (active) {
            this._elapsedSeconds = 0;
            this._updateTimerDisplay();
            this.visible = true;
            this._suppressGnomeIndicators();

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
            if (!this._indicatorSuppressed) {
                this._restoreGnomeIndicators();
            }
        }
    }

    _suppressGnomeIndicators() {
        this._restoreGnomeIndicators();

        const targets = [];
        if (Main.panel && Main.panel.statusArea) {
            if (Main.panel.statusArea.screenSharing) {
                targets.push(Main.panel.statusArea.screenSharing);
            }
            if (Main.panel.statusArea.screenRecording) {
                targets.push(Main.panel.statusArea.screenRecording);
            }
            const qs = Main.panel.statusArea.quickSettings;
            if (qs && qs._remoteAccess && qs._remoteAccess._indicator) {
                targets.push(qs._remoteAccess._indicator);
            }
        }

        for (const item of targets) {
            try {
                const wasVisible = item.visible;
                item.visible = false;
                const id = item.connect('notify::visible', () => {
                    if ((this.visible || this._indicatorSuppressed) && item.visible) {
                        item.visible = false;
                    }
                });
                this._gnomeIndicatorWatches.push({ item, id, wasVisible });
            } catch (e) {
                // Ignore item connection issues
            }
        }
    }

    _restoreGnomeIndicators() {
        if (!this._gnomeIndicatorWatches) return;
        for (const { item, id, wasVisible } of this._gnomeIndicatorWatches) {
            try {
                item.disconnect(id);
                if (typeof item._sync === 'function') {
                    item._sync();
                } else if (typeof item._onScreencastInProgressChanged === 'function') {
                    item._onScreencastInProgressChanged();
                } else {
                    item.visible = wasVisible;
                }
            } catch (e) {
                // Ignore disconnect issues
            }
        }
        this._gnomeIndicatorWatches = [];
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
        // 1. Direct call inside Shell if captureUI is available
        if (this._captureUI && typeof this._captureUI.stopRecording === 'function') {
            this._captureUI.stopRecording();
            return;
        }

        // 2. D-Bus helper signal fallback
        if (this._captureHelper && this._captureHelper.emitStopRecordingRequested) {
            this._captureHelper.emitStopRecordingRequested();
        }
    }

    _requestSnapshot() {
        this.flashCameraIcon();

        // 1. Direct call inside Shell if captureUI is available
        if (this._captureUI && typeof this._captureUI.captureSilentScreenshot === 'function') {
            this._captureUI.captureSilentScreenshot();
            return;
        }

        // 2. D-Bus helper signal fallback
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
        if (this._flashTimerId) {
            GLib.source_remove(this._flashTimerId);
            this._flashTimerId = null;
        }
        this._flashTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 220, () => {
            this._flashTimerId = null;
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
