// captureUI.js - Native GNOME Shell UI for Sadeem Capture
import Cairo from 'gi://cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import * as I18n from './captureI18n.js';

try {
    if (Shell?.Screenshot?.prototype)
        Gio._promisify(Shell.Screenshot.prototype, 'screenshot_stage_to_content');
} catch (_e) {}

export const CaptureUI = GObject.registerClass(
class CaptureUI extends St.Widget {
    _init(captureHelper, haloManager, recordingIndicator) {
        super._init({
            name: 'sadeem-capture-ui',
            reactive: true,
            can_focus: true,
            track_hover: true,
            visible: false,
        });

        this._captureHelper = captureHelper;
        this._haloManager = haloManager;
        this._recordingIndicator = recordingIndicator;

        this._isOpen = false;
        this._grab = null;
        this._mode = 'selection'; // 'selection' | 'screen' | 'window'
        this._mediaMode = 'photo'; // 'photo' | 'video'
        this._includeCursor = true;
        this._haloActive = false;

        // Video Settings
        this._audioMode = 'system'; // 'none' | 'system' | 'mic' | 'both'
        this._resolution = 'native'; // 'native' | '1080p' | '720p'
        this._fps = 60; // 30 | 60
        this._codec = 'h264'; // 'h264' | 'h265'
        this._selectedMic = '';
        this._availableMics = [];
        this._settingsMenuOpen = false;

        // Selection & Interaction
        this._selectionRect = { x: 0, y: 0, width: 0, height: 0 };
        this._dragState = null;
        this._hoveredWindow = null;
        this._hoveredMonitor = null;
        this._lastScreenHighlightMon = null;
        this._lastCursorType = null;
        this._frozenWindows = [];
        this._resButtons = [];
        this._fpsButtons = [];
        this._codecButtons = [];

        // Process & Subprocess State
        this._recorderSubprocess = null;
        this._isRecording = false;
        this._lastSilentShotTime = 0;
        this._frozenContent = null;
        this._frozenScale = 1.0;
        this._cursorInfo = null;
        this._notifSource = null;

        // Build Stage Container and Layers
        this._buildLayers();
        this._buildControls();

        // Connect Key & Pointer events
        this.connect('key-press-event', (actor, event) => this._onKeyPress(event));
        this.connect('button-press-event', (actor, event) => this._onButtonPress(event));
        this.connect('button-release-event', (actor, event) => this._onButtonRelease(event));
        this.connect('motion-event', (actor, event) => this._onMotion(event));

        // Asynchronously load available microphones
        this._loadMicrophonesAsync();
    }

    _buildLayers() {
        // 1. Frozen Screenshot Layer (WYSIWYG from GPU)
        this._frozenContainer = new St.Widget({
            name: 'sadeem-frozen-container',
            reactive: false,
        });
        this._frozenContainer.add_constraint(new Clutter.BindConstraint({
            source: global.stage,
            coordinate: Clutter.BindCoordinate.ALL,
        }));
        this._stageScreenshot = new St.Widget({
            name: 'sadeem-stage-screenshot',
            reactive: false,
        });
        this._stageScreenshot.add_constraint(new Clutter.BindConstraint({
            source: global.stage,
            coordinate: Clutter.BindCoordinate.ALL,
        }));
        this._frozenContainer.add_child(this._stageScreenshot);
        this.add_child(this._frozenContainer);

        // 2. Dimming 4-Bar Layer (clean rectangle cut with no drawing bugs)
        this._dimOverlay = new St.Widget({
            name: 'sadeem-dim-overlay',
            reactive: false,
        });
        this._dimOverlay.add_constraint(new Clutter.BindConstraint({
            source: global.stage,
            coordinate: Clutter.BindCoordinate.ALL,
        }));

        const dimStyle = 'background-color: rgba(0, 0, 0, 0.45);';
        this._dimTop = new St.Widget({ reactive: false, style: dimStyle });
        this._dimBottom = new St.Widget({ reactive: false, style: dimStyle });
        this._dimLeft = new St.Widget({ reactive: false, style: dimStyle });
        this._dimRight = new St.Widget({ reactive: false, style: dimStyle });

        this._dimOverlay.add_child(this._dimTop);
        this._dimOverlay.add_child(this._dimBottom);
        this._dimOverlay.add_child(this._dimLeft);
        this._dimOverlay.add_child(this._dimRight);
        this.add_child(this._dimOverlay);

        // 3. Selection Box & Handles
        this._selectionBox = new St.Widget({
            name: 'sadeem-selection-box',
            reactive: false,
            visible: false,
            style: 'border: 2px solid #ffffff;',
        });

        // Circular Handles
        const handleStyle = 'width: 12px; height: 12px; background-color: #ffffff; border-radius: 9999px; border: 1.5px solid rgba(0,0,0,0.5);';
        this._handleTL = new St.Widget({ reactive: false, style: handleStyle });
        this._handleTR = new St.Widget({ reactive: false, style: handleStyle });
        this._handleBL = new St.Widget({ reactive: false, style: handleStyle });
        this._handleBR = new St.Widget({ reactive: false, style: handleStyle });

        this._selectionBox.add_child(this._handleTL);
        this._selectionBox.add_child(this._handleTR);
        this._selectionBox.add_child(this._handleBL);
        this._selectionBox.add_child(this._handleBR);

        // Dimensions Badge
        this._dimensionsBadge = new St.Label({
            name: 'sadeem-dimensions-badge',
            text: '0 × 0 px',
            reactive: false,
            style: 'background-color: rgba(20, 20, 24, 0.85); color: #ffffff; font-size: 11px; font-weight: bold; padding: 2px 8px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2);',
        });
        this._selectionBox.add_child(this._dimensionsBadge);
        this.add_child(this._selectionBox);

        // 4. Highlight Frames for Screen & Window Modes (GPU-friendly borders, zero CPU blur shadows)
        this._screenHighlight = new St.Widget({
            name: 'sadeem-screen-highlight',
            reactive: false,
            visible: false,
            style: 'border: 3px solid #7a1c33; border-radius: 6px;',
        });
        this.add_child(this._screenHighlight);

        this._windowHighlight = new St.Widget({
            name: 'sadeem-window-highlight',
            reactive: false,
            visible: false,
            style: 'border: 3px solid #7a1c33; border-radius: 6px; background-color: rgba(122, 28, 51, 0.10);',
        });
        this._windowTitleLabel = new St.Label({
            name: 'sadeem-window-title',
            text: '',
            reactive: false,
            style: 'background-color: rgba(20, 20, 24, 0.9); color: #ffffff; font-size: 12px; font-weight: bold; padding: 3px 10px; border-radius: 6px; margin: 6px;',
        });
        this._windowHighlight.add_child(this._windowTitleLabel);
        this.add_child(this._windowHighlight);

        // Enforce internal stacking order (handles, badge, overlays)
        this.set_child_above_sibling(this._selectionBox, this._dimOverlay);
    }

    _buildControls() {
        // Work area container anchored to monitor work area
        this._workAreaContainer = new St.BoxLayout({
            name: 'sadeem-work-area-container',
            orientation: Clutter.Orientation.VERTICAL,
            reactive: false,
        });

        // Top Row: Hint Pill (Top of Work Area, lightweight, reactive: false)
        this._topPill = new St.BoxLayout({
            name: 'sadeem-top-pill',
            style_class: 'sadeem-capture-top-pill',
            orientation: Clutter.Orientation.HORIZONTAL,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.START,
            x_expand: false,
            y_expand: false,
            margin_top: 24,
            reactive: false,
        });

        this._hintLabel = new St.Label({
            style_class: 'sadeem-capture-hint-label',
            text: I18n.t('select_hint'),
            reactive: false,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._topPill.add_child(this._hintLabel);
        this._workAreaContainer.add_child(this._topPill);

        // Flexible transparent spacer absorbing all remaining vertical space to push control card to bottom
        this._workAreaSpacer = new St.Widget({
            name: 'sadeem-work-area-spacer',
            reactive: false,
            x_expand: true,
            y_expand: true,
        });
        this._workAreaContainer.add_child(this._workAreaSpacer);

        // Floating toolbar card at bottom of current monitor work area
        this._controlCard = new St.BoxLayout({
            name: 'sadeem-control-card',
            style_class: 'sadeem-capture-card',
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.END,
            x_expand: false,
            y_expand: false,
            margin_bottom: 24,
            reactive: true,
            can_focus: true,
            track_hover: true,
        });

        // Card Top Header: Close Button in upper corner of card
        const cardHeader = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'margin-bottom: 8px;',
        });
        cardHeader.add_child(new St.Widget({ x_expand: true }));
        this._closeBtn = new St.Button({
            style_class: 'button sadeem-capture-close-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        this._closeBtn.set_accessible_name(I18n.t('tooltip_close'));
        this._closeBtn.set_child(new St.Icon({
            icon_name: 'window-close-symbolic',
            icon_size: 13,
            style: 'color: #ffffff;',
        }));
        this._closeBtn.connect('clicked', () => {
            this.close();
            return Clutter.EVENT_STOP;
        });
        cardHeader.add_child(this._closeBtn);
        this._controlCard.add_child(cardHeader);

        // Row 1: Mode Selector (Selection, Screen, Window)
        this._modesBox = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            style_class: 'sadeem-capture-modes-box',
        });

        this._modeBtnSelection = this._createModeButton('edit-select-all-symbolic', I18n.t('mode_selection'), 'selection');
        this._modeBtnScreen = this._createModeButton('video-display-symbolic', I18n.t('mode_screen'), 'screen');
        this._modeBtnWindow = this._createModeButton('focus-windows-symbolic', I18n.t('mode_window'), 'window');

        this._modesBox.add_child(this._modeBtnSelection);
        this._modesBox.add_child(this._modeBtnScreen);
        this._modesBox.add_child(this._modeBtnWindow);
        this._controlCard.add_child(this._modesBox);

        // Row 2: Symmetric Actions Row
        // [ Photo | Video Capsule ] --- [ Capture Button ] --- [ Cursor | Halo Capsule ]
        const actionsRow = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'spacing: 18px; margin-bottom: 4px;',
        });

        // Left Capsule: Media Mode (Photo / Video)
        this._mediaBox = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'sadeem-capture-capsule',
        });
        this._photoBtn = this._createToggleIconButton('camera-photo-symbolic', I18n.t('tab_photo'), () => this._setMediaMode('photo'));
        this._videoBtn = this._createToggleIconButton('camera-video-symbolic', I18n.t('tab_video'), () => this._setMediaMode('video'));
        this._mediaBox.add_child(this._photoBtn);
        this._mediaBox.add_child(this._videoBtn);
        actionsRow.add_child(this._mediaBox);

        // Center: Circular Capture / Record Button
        this._captureBtn = new St.Button({
            style_class: 'button sadeem-capture-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._captureBtnIcon = new St.Icon({
            icon_name: 'camera-photo-symbolic',
            icon_size: 20,
            style: 'color: #ffffff;',
        });
        this._captureBtn.set_child(this._captureBtnIcon);
        this._captureBtn.connect('clicked', () => {
            this._triggerCapture();
            return Clutter.EVENT_STOP;
        });
        actionsRow.add_child(this._captureBtn);

        // Right Capsule: Cursor & Halo Toggles
        this._cursorBox = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'sadeem-capture-capsule',
        });
        this._cursorToggleBtn = this._createToggleIconButton('input-mouse-symbolic', I18n.t('tooltip_cursor'), () => this._toggleCursor());
        this._haloToggleBtn = this._createToggleIconButton('find-location-symbolic', I18n.t('tooltip_halo'), () => this._toggleHalo());
        this._cursorBox.add_child(this._cursorToggleBtn);
        this._cursorBox.add_child(this._haloToggleBtn);
        actionsRow.add_child(this._cursorBox);

        this._controlCard.add_child(actionsRow);

        // Row 3: Video Settings Row (shown only in video mode)
        this._videoSettingsRow = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            y_align: Clutter.ActorAlign.CENTER,
            visible: false,
            style_class: 'sadeem-capture-video-row',
        });

        // Audio System Toggle
        this._audioSysBtn = new St.Button({
            style_class: 'button sadeem-capture-pill-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        const audioSysBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, y_align: Clutter.ActorAlign.CENTER, style: 'spacing: 5px;' });
        audioSysBox.add_child(new St.Icon({ icon_name: 'audio-volume-high-symbolic', icon_size: 13, style: 'color: #ffffff;' }));
        audioSysBox.add_child(new St.Label({ text: I18n.t('audio_system'), style: 'color: #ffffff; font-size: 11px;' }));
        this._audioSysBtn.set_child(audioSysBox);
        this._audioSysBtn.connect('clicked', () => this._toggleAudioSys());
        this._videoSettingsRow.add_child(this._audioSysBtn);

        // Microphone Toggle
        this._audioMicBtn = new St.Button({
            style_class: 'button sadeem-capture-pill-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        const audioMicBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, y_align: Clutter.ActorAlign.CENTER, style: 'spacing: 5px;' });
        audioMicBox.add_child(new St.Icon({ icon_name: 'audio-input-microphone-symbolic', icon_size: 13, style: 'color: #ffffff;' }));
        audioMicBox.add_child(new St.Label({ text: I18n.t('audio_mic'), style: 'color: #ffffff; font-size: 11px;' }));
        this._audioMicBtn.set_child(audioMicBox);
        this._audioMicBtn.connect('clicked', () => this._toggleAudioMic());
        this._videoSettingsRow.add_child(this._audioMicBtn);

        this._videoSettingsRow.add_child(new St.Widget({ x_expand: true }));

        // Settings / Codec / Resolution popup button
        this._settingsMenuBtn = new St.Button({
            style_class: 'button sadeem-capture-pill-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        const settingsBtnBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, y_align: Clutter.ActorAlign.CENTER, style: 'spacing: 5px;' });
        settingsBtnBox.add_child(new St.Icon({ icon_name: 'emblem-system-symbolic', icon_size: 13, style: 'color: #ffffff;' }));
        this._settingsBtnLabel = new St.Label({ text: '1080p | H.264', style: 'color: #ffffff; font-size: 11px;' });
        settingsBtnBox.add_child(this._settingsBtnLabel);
        this._settingsMenuBtn.set_child(settingsBtnBox);
        this._settingsMenuBtn.connect('clicked', () => this._toggleSettingsPopup());
        this._videoSettingsRow.add_child(this._settingsMenuBtn);

        this._controlCard.add_child(this._videoSettingsRow);

        // Quick Settings Popup Menu
        this._settingsPopup = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            visible: false,
            style_class: 'sadeem-capture-settings-popup',
        });
        this._buildSettingsPopupContents();
        this._controlCard.add_child(this._settingsPopup);

        this._workAreaContainer.add_child(this._controlCard);
        this.add_child(this._workAreaContainer);
        this._syncToggleButtons();
        this._ensureLayerOrder();
    }

    _ensureLayerOrder() {
        try {
            if (this._frozenContainer && this._frozenContainer.get_parent() === this) {
                this.set_child_below_sibling(this._frozenContainer, null);
            }
            if (this._dimOverlay && this._frozenContainer && this._dimOverlay.get_parent() === this) {
                this.set_child_above_sibling(this._dimOverlay, this._frozenContainer);
            }
            if (this._screenHighlight && this._dimOverlay && this._screenHighlight.get_parent() === this) {
                this.set_child_above_sibling(this._screenHighlight, this._dimOverlay);
            }
            if (this._windowHighlight && this._screenHighlight && this._windowHighlight.get_parent() === this) {
                this.set_child_above_sibling(this._windowHighlight, this._screenHighlight);
            }
            if (this._selectionBox && this._dimOverlay && this._selectionBox.get_parent() === this) {
                this.set_child_above_sibling(this._selectionBox, this._dimOverlay);
                if (this._handleTL) this._selectionBox.set_child_above_sibling(this._handleTL, null);
                if (this._handleTR) this._selectionBox.set_child_above_sibling(this._handleTR, null);
                if (this._handleBL) this._selectionBox.set_child_above_sibling(this._handleBL, null);
                if (this._handleBR) this._selectionBox.set_child_above_sibling(this._handleBR, null);
                if (this._dimensionsBadge) this._selectionBox.set_child_above_sibling(this._dimensionsBadge, null);
            }
            if (this._workAreaContainer && this._workAreaContainer.get_parent() === this) {
                this.set_child_above_sibling(this._workAreaContainer, null);
            }
        } catch (e) {
            console.error('[CaptureUI] _ensureLayerOrder error: ' + e);
        }
    }

    _setDragVisualState(isDragging) {
        if (this._controlCard) {
            this._controlCard.opacity = isDragging ? 60 : 255;
            this._controlCard.reactive = !isDragging;
        }
        if (this._topPill) {
            this._topPill.opacity = isDragging ? 60 : 255;
        }
    }

    _setActorClassState(actor, className, active) {
        if (!actor)
            return;
        if (active)
            actor.add_style_class_name(className);
        else
            actor.remove_style_class_name(className);
    }

    _setCursorType(cursorType) {
        if (this._lastCursorType === cursorType)
            return;
        this._lastCursorType = cursorType;
        try {
            this.set_cursor_type(cursorType);
        } catch (_e) {}
    }

    _createModeButton(iconName, labelText, mode) {
        const btn = new St.Button({
            style_class: 'button sadeem-capture-mode-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
            x_expand: true,
        });
        const box = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'spacing: 4px;',
        });
        box.add_child(new St.Icon({
            icon_name: iconName,
            icon_size: 18,
            style: 'color: #ffffff;',
        }));
        box.add_child(new St.Label({
            text: labelText,
            style: 'color: #ffffff; font-size: 11px; font-weight: bold; text-align: center;',
        }));
        btn.set_child(box);
        btn.connect('clicked', () => {
            this._setMode(mode);
            return Clutter.EVENT_STOP;
        });
        return btn;
    }

    _createToggleIconButton(iconName, tooltip, onClick) {
        const btn = new St.Button({
            style_class: 'button sadeem-capture-icon-btn',
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        btn.set_accessible_name(tooltip);
        btn.set_child(new St.Icon({
            icon_name: iconName,
            icon_size: 15,
            style: 'color: #ffffff;',
        }));
        btn.connect('clicked', () => {
            onClick();
            return Clutter.EVENT_STOP;
        });
        return btn;
    }

    _buildSettingsPopupContents() {
        this._resButtons = [];
        this._fpsButtons = [];
        this._codecButtons = [];

        // Resolution Selector
        const resBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, y_align: Clutter.ActorAlign.CENTER, style: 'margin-bottom: 4px; spacing: 4px;' });
        resBox.add_child(new St.Label({ text: I18n.t('setting_resolution'), style: 'color: rgba(255,255,255,0.7); font-size: 11px; min-width: 80px;' }));
        for (const [key, label] of [['native', I18n.t('res_native')], ['1080p', '1080p'], ['720p', '720p']]) {
            const b = new St.Button({
                label: label,
                style_class: 'button sadeem-capture-setting-chip',
            });
            b.connect('clicked', () => {
                this._resolution = key;
                this._updateSettingsDisplay();
            });
            this._resButtons.push({ key, btn: b });
            resBox.add_child(b);
        }
        this._settingsPopup.add_child(resBox);

        // Framerate Selector
        const fpsBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, y_align: Clutter.ActorAlign.CENTER, style: 'margin-bottom: 4px; spacing: 4px;' });
        fpsBox.add_child(new St.Label({ text: I18n.t('setting_framerate'), style: 'color: rgba(255,255,255,0.7); font-size: 11px; min-width: 80px;' }));
        for (const [fpsVal, label] of [[60, '60 fps'], [30, '30 fps']]) {
            const b = new St.Button({
                label: label,
                style_class: 'button sadeem-capture-setting-chip',
            });
            b.connect('clicked', () => {
                this._fps = fpsVal;
                this._updateSettingsDisplay();
            });
            this._fpsButtons.push({ key: fpsVal, btn: b });
            fpsBox.add_child(b);
        }
        this._settingsPopup.add_child(fpsBox);

        // Codec Selector
        const codecBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, y_align: Clutter.ActorAlign.CENTER, style: 'margin-bottom: 4px; spacing: 4px;' });
        codecBox.add_child(new St.Label({ text: I18n.t('setting_codec'), style: 'color: rgba(255,255,255,0.7); font-size: 11px; min-width: 80px;' }));
        for (const [cVal, label] of [['h264', 'H.264'], ['h265', 'H.265']]) {
            const b = new St.Button({
                label: label,
                style_class: 'button sadeem-capture-setting-chip',
            });
            b.connect('clicked', () => {
                this._codec = cVal;
                this._updateSettingsDisplay();
            });
            this._codecButtons.push({ key: cVal, btn: b });
            codecBox.add_child(b);
        }
        this._settingsPopup.add_child(codecBox);
    }

    _loadMicrophonesAsync() {
        try {
            const sub = new Gio.Subprocess({
                argv: ['pactl', 'list', 'sources', 'short'],
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            });
            sub.init(null);
            sub.communicate_utf8_async(null, null, (proc, res) => {
                try {
                    const [, stdout] = proc.communicate_utf8_finish(res);
                    if (stdout) {
                        const mics = [];
                        const lines = stdout.trim().split('\n');
                        for (const line of lines) {
                            const parts = line.split('\t');
                            if (parts.length >= 2) {
                                const name = parts[1];
                                if (!name.endsWith('.monitor')) {
                                    mics.push({ id: parts[0], name: name });
                                }
                            }
                        }
                        this._availableMics = mics;
                        if (mics.length > 0 && !this._selectedMic) {
                            this._selectedMic = mics[0].name;
                        }
                    }
                } catch (e) {
                    // Non-fatal microphone list error
                }
            });
        } catch (err) {
            // Non-fatal
        }
    }

    // --- State & Mode Transitions ---

    _setMode(mode) {
        this._mode = mode;
        this._setActorClassState(this._modeBtnSelection, 'sadeem-capture-mode-btn-active', mode === 'selection');
        this._setActorClassState(this._modeBtnScreen, 'sadeem-capture-mode-btn-active', mode === 'screen');
        this._setActorClassState(this._modeBtnWindow, 'sadeem-capture-mode-btn-active', mode === 'window');

        if (mode === 'selection') {
            this._setCursorType(Clutter.CursorType.CROSSHAIR);
            this._hintLabel.text = I18n.t('select_hint');
            this._selectionBox.visible = (this._selectionRect.width > 5 && this._selectionRect.height > 5);
            this._screenHighlight.visible = false;
            this._windowHighlight.visible = false;
            this._updateDimming();
        } else if (mode === 'screen') {
            this._setCursorType(Clutter.CursorType.POINTER);
            this._hintLabel.text = I18n.t('screen_hint');
            this._selectionBox.visible = false;
            this._windowHighlight.visible = false;
            this._screenHighlight.visible = true;
            this._updateScreenHighlight();
            this._clearDimming();
        } else if (mode === 'window') {
            this._setCursorType(Clutter.CursorType.POINTER);
            this._hintLabel.text = I18n.t('window_hint');
            this._selectionBox.visible = false;
            this._screenHighlight.visible = false;
            this._windowHighlight.visible = false;
            this._hoveredWindow = null;
            this._clearDimming();
            this._updateWindowUnderCursor();
        }
    }

    _setMediaMode(mediaMode) {
        this._mediaMode = mediaMode;
        this._setActorClassState(this._photoBtn, 'sadeem-capture-icon-btn-active', mediaMode === 'photo');
        this._setActorClassState(this._videoBtn, 'sadeem-capture-icon-btn-active', mediaMode === 'video');
        this._setActorClassState(this._captureBtn, 'sadeem-capture-btn-video', mediaMode === 'video');

        if (mediaMode === 'photo') {
            this._captureBtnIcon.icon_name = 'camera-photo-symbolic';
            this._videoSettingsRow.visible = false;
            this._settingsPopup.visible = false;
            this._settingsMenuOpen = false;
        } else {
            this._captureBtnIcon.icon_name = 'media-record-symbolic';
            this._videoSettingsRow.visible = true;
        }
        this._updateSettingsDisplay();
    }

    _toggleMediaMode() {
        this._setMediaMode(this._mediaMode === 'photo' ? 'video' : 'photo');
    }

    _toggleCursor() {
        this._includeCursor = !this._includeCursor;
        this._syncToggleButtons();
    }

    _toggleHalo() {
        this._haloActive = !this._haloActive;
        if (this._haloActive && !this._includeCursor)
            this._includeCursor = true;
        this._syncToggleButtons();
    }

    _syncToggleButtons() {
        this._setActorClassState(this._cursorToggleBtn, 'sadeem-capture-icon-btn-active', this._includeCursor);
        this._setActorClassState(this._haloToggleBtn, 'sadeem-capture-halo-btn-active', this._haloActive);
        this._updateAudioButtons();
    }

    _toggleAudioSys() {
        if (this._audioMode === 'both') {
            this._audioMode = 'mic';
        } else if (this._audioMode === 'system') {
            this._audioMode = 'none';
        } else if (this._audioMode === 'mic') {
            this._audioMode = 'both';
        } else {
            this._audioMode = 'system';
        }
        this._updateAudioButtons();
    }

    _toggleAudioMic() {
        if (this._audioMode === 'both') {
            this._audioMode = 'system';
        } else if (this._audioMode === 'mic') {
            this._audioMode = 'none';
        } else if (this._audioMode === 'system') {
            this._audioMode = 'both';
        } else {
            this._audioMode = 'mic';
        }
        this._updateAudioButtons();
    }

    _updateAudioButtons() {
        const sysActive = (this._audioMode === 'system' || this._audioMode === 'both');
        const micActive = (this._audioMode === 'mic' || this._audioMode === 'both');
        this._setActorClassState(this._audioSysBtn, 'sadeem-capture-pill-btn-active', sysActive);
        this._setActorClassState(this._audioMicBtn, 'sadeem-capture-pill-btn-active', micActive);
    }

    _toggleSettingsPopup() {
        this._settingsMenuOpen = !this._settingsMenuOpen;
        this._settingsPopup.visible = this._settingsMenuOpen;
    }

    _updateSettingsDisplay() {
        if (this._settingsBtnLabel) {
            this._settingsBtnLabel.text = `${this._resolution} | ${this._codec.toUpperCase()} | ${this._fps}fps`;
        }
        for (const item of this._resButtons)
            this._setActorClassState(item.btn, 'sadeem-capture-setting-chip-active', item.key === this._resolution);
        for (const item of this._fpsButtons)
            this._setActorClassState(item.btn, 'sadeem-capture-setting-chip-active', item.key === this._fps);
        for (const item of this._codecButtons)
            this._setActorClassState(item.btn, 'sadeem-capture-setting-chip-active', item.key === this._codec);
    }

    _snapshotFrozenWindows() {
        const snapshot = [];
        try {
            const activeWorkspace = global.workspace_manager.get_active_workspace();
            const rawWindows = activeWorkspace.list_windows();
            const sortedWindows = global.display.sort_windows_by_stacking(rawWindows).reverse();
            for (const win of sortedWindows) {
                if (!win || win.is_hidden() || win.is_override_redirect())
                    continue;
                const type = win.get_window_type();
                if (type === Meta.WindowType.DOCK || type === Meta.WindowType.DESKTOP)
                    continue;
                const rect = win.get_frame_rect();
                snapshot.push({
                    win,
                    rect,
                    title: win.get_title() || win.get_wm_class() || 'Window',
                });
            }
        } catch (_e) {}
        this._frozenWindows = snapshot;
    }

    // --- Open, Close & Modal Lifecycle ---

    async open(initialMode = 'selection', initialMedia = 'photo') {
        if (this._isOpen) return;

        // If recording is already active: take silent screenshot immediately
        if (this._isRecording) {
            this.captureSilentScreenshot();
            return;
        }

        this._snapshotFrozenWindows();

        try {
            // Freeze screen directly in GPU memory
            const shooter = new Shell.Screenshot();
            const [content, scale, cursorContent, cursorPoint, cursorScale] = await shooter.screenshot_stage_to_content();

            this._frozenContent = content;
            this._frozenScale = scale || 1.0;
            this._cursorInfo = {
                content: cursorContent,
                point: cursorPoint,
                scale: cursorScale || 1.0,
            };

            this._stageScreenshot.set_content(content);
        } catch (err) {
            console.error('[CaptureUI] Error capturing stage to content: ' + err);
        }

        // Add to uiGroup if not added and always raise above all GNOME layers (ArcMenu, Dash-to-Dock, panel, cursorHalo, popups)
        if (Main.layoutManager && Main.layoutManager.uiGroup) {
            if (!this.get_parent()) {
                Main.layoutManager.uiGroup.add_child(this);
            }
            Main.layoutManager.uiGroup.set_child_above_sibling(this, null);
        }

        this.set_position(0, 0);
        this.set_size(global.stage.width, global.stage.height);
        this._ensureLayerOrder();
        this._setDragVisualState(false);
        this.visible = true;
        this._isOpen = true;
        this._lastCursorType = null;
        this._lastScreenHighlightMon = null;

        // Safely push modal
        try {
            this._grab = Main.pushModal(this);
        } catch (e) {
            console.error('[CaptureUI] pushModal failed: ' + e);
        }

        this._setCursorType(Clutter.CursorType.CROSSHAIR);

        // Position control card on monitor under cursor
        this._positionControlCard();

        // Initialize Modes & sync visual toggle button state
        this._syncToggleButtons();
        this._setMode(initialMode);
        this._setMediaMode(initialMedia);
    }

    close() {
        if (!this._isOpen && !this.visible) return;

        try {
            if (this._grab) {
                Main.popModal(this._grab);
                this._grab = null;
            }
        } catch (e) {
            console.error('[CaptureUI] popModal error: ' + e);
        }

        this._setCursorType(Clutter.CursorType.DEFAULT);
        this._lastCursorType = null;

        this.visible = false;
        this._isOpen = false;
        this._dragState = null;
        this._hoveredWindow = null;
        this._lastScreenHighlightMon = null;
        this._frozenWindows = [];
        this._settingsMenuOpen = false;
        if (this._settingsPopup) {
            this._settingsPopup.visible = false;
        }
        this._setDragVisualState(false);

        if (this._stageScreenshot) {
            this._stageScreenshot.set_content(null);
        }
        this._frozenContent = null;
        this._frozenScale = 1.0;
        this._cursorInfo = null;
    }

    destroy() {
        this.close();
        if (this._notifSource) {
            try {
                this._notifSource.destroy();
            } catch (e) {}
            this._notifSource = null;
        }
        super.destroy();
    }

    _positionControlCard() {
        const [cx, cy] = global.get_pointer();
        const monitor = this._findMonitorAt(cx, cy) || Main.layoutManager.currentMonitor || Main.layoutManager.primaryMonitor;
        this._hoveredMonitor = monitor;

        const monitorIndex = Main.layoutManager.monitors ? Math.max(0, Main.layoutManager.monitors.indexOf(monitor)) : 0;
        const workArea = (Main.layoutManager.getWorkAreaForMonitor ? Main.layoutManager.getWorkAreaForMonitor(monitorIndex) : null) || monitor;

        this._workAreaContainer.set_position(workArea.x, workArea.y);
        this._workAreaContainer.set_size(workArea.width, workArea.height);
    }

    _isPointInsideActor(actor, x, y) {
        if (!actor || !actor.visible) return false;
        try {
            const [ax, ay] = actor.get_transformed_position();
            const [aw, ah] = actor.get_transformed_size();
            return (x >= ax && x <= ax + aw && y >= ay && y <= ay + ah);
        } catch (e) {
            const [ax, ay] = actor.get_position();
            return (x >= ax && x <= ax + actor.width && y >= ay && y <= ay + actor.height);
        }
    }

    _findMonitorAt(x, y) {
        if (!Main.layoutManager || !Main.layoutManager.monitors) return null;
        for (const m of Main.layoutManager.monitors) {
            if (x >= m.x && x < m.x + m.width && y >= m.y && y < m.y + m.height) {
                return m;
            }
        }
        return Main.layoutManager.primaryMonitor;
    }

    // --- Dimming & Selection Rendering ---

    _updateDimming() {
        if (this._dimOverlay && !this._dimOverlay.visible)
            this._dimOverlay.visible = true;
        const sw = global.stage.width;
        const sh = global.stage.height;
        const r = this._selectionRect;

        if (r.width <= 0 || r.height <= 0) {
            // Full dimming
            this._dimTop.set_position(0, 0);
            this._dimTop.set_size(sw, sh);
            this._dimBottom.set_size(0, 0);
            this._dimLeft.set_size(0, 0);
            this._dimRight.set_size(0, 0);
            if (this._selectionBox) {
                this._selectionBox.visible = false;
                this._selectionBox.set_position(r.x, r.y);
                this._selectionBox.set_size(0, 0);
            }
            return;
        }

        // Ensure selection box is visible and stays above dimming overlay
        if (this._selectionBox) {
            this._selectionBox.visible = (this._mode === 'selection');
        }

        // 4 bars around selection
        this._dimTop.set_position(0, 0);
        this._dimTop.set_size(sw, Math.max(0, r.y));

        this._dimBottom.set_position(0, r.y + r.height);
        this._dimBottom.set_size(sw, Math.max(0, sh - (r.y + r.height)));

        this._dimLeft.set_position(0, r.y);
        this._dimLeft.set_size(Math.max(0, r.x), r.height);

        this._dimRight.set_position(r.x + r.width, r.y);
        this._dimRight.set_size(Math.max(0, sw - (r.x + r.width)), r.height);

        // Update selection box
        this._selectionBox.set_position(r.x, r.y);
        this._selectionBox.set_size(r.width, r.height);
        if (this._dimOverlay && this._selectionBox.get_parent() === this) {
            this.set_child_above_sibling(this._selectionBox, this._dimOverlay);
        }

        // Handles at corners
        const hw = 12;
        this._handleTL.set_position(-hw / 2, -hw / 2);
        this._handleTR.set_position(r.width - hw / 2, -hw / 2);
        this._handleBL.set_position(-hw / 2, r.height - hw / 2);
        this._handleBR.set_position(r.width - hw / 2, r.height - hw / 2);

        // Dimensions Badge (stay inside top corner when selection approaches top screen edge)
        this._dimensionsBadge.text = `${r.width} × ${r.height} px`;
        this._dimensionsBadge.set_position(6, r.y < 28 ? 6 : -24);
    }

    _clearDimming() {
        if (this._dimOverlay)
            this._dimOverlay.visible = false;
    }

    _updateScreenHighlight(pointerX = null, pointerY = null) {
        let cx = pointerX;
        let cy = pointerY;
        if (cx === null || cy === null)
            [cx, cy] = global.get_pointer();
        const m = this._findMonitorAt(cx, cy);
        if (m) {
            this._hoveredMonitor = m;
            if (m !== this._lastScreenHighlightMon) {
                this._lastScreenHighlightMon = m;
                this._screenHighlight.set_position(m.x + 4, m.y + 4);
                this._screenHighlight.set_size(m.width - 8, m.height - 8);
            }
        }
    }

    _updateWindowUnderCursor(pointerX = null, pointerY = null) {
        let cx = pointerX;
        let cy = pointerY;
        if (cx === null || cy === null)
            [cx, cy] = global.get_pointer();
        try {
            if (!this._frozenWindows || this._frozenWindows.length === 0)
                this._snapshotFrozenWindows();

            let targetEntry = null;
            for (const entry of this._frozenWindows) {
                const rect = entry.rect;
                if (cx >= rect.x && cx <= rect.x + rect.width && cy >= rect.y && cy <= rect.y + rect.height) {
                    targetEntry = entry;
                    break;
                }
            }

            const nextWin = targetEntry ? targetEntry.win : null;
            if (nextWin === this._hoveredWindow && Boolean(nextWin) === this._windowHighlight.visible)
                return;

            this._hoveredWindow = nextWin;
            if (targetEntry) {
                const rect = targetEntry.rect;
                this._windowHighlight.visible = true;
                this._windowHighlight.set_position(rect.x, rect.y);
                this._windowHighlight.set_size(rect.width, rect.height);
                this._windowTitleLabel.text = targetEntry.title;
            } else {
                this._windowHighlight.visible = false;
            }
        } catch (e) {
            // Ignore window query error
        }
    }

    // --- Pointer & Keyboard Handling ---

    _onKeyPress(event) {
        try {
            const sym = event.get_key_symbol();
            if (sym === Clutter.KEY_Escape) {
                this.close();
                return Clutter.EVENT_STOP;
            }
            if (sym === Clutter.KEY_Return || sym === Clutter.KEY_KP_Enter) {
                this._triggerCapture();
                return Clutter.EVENT_STOP;
            }
            if (sym === Clutter.KEY_1) {
                this._setMode('selection');
                return Clutter.EVENT_STOP;
            }
            if (sym === Clutter.KEY_2) {
                this._setMode('screen');
                return Clutter.EVENT_STOP;
            }
            if (sym === Clutter.KEY_3) {
                this._setMode('window');
                return Clutter.EVENT_STOP;
            }
            if (sym === Clutter.KEY_v || sym === Clutter.KEY_V) {
                this._toggleMediaMode();
                return Clutter.EVENT_STOP;
            }
            if (sym === Clutter.KEY_c || sym === Clutter.KEY_C) {
                this._toggleCursor();
                return Clutter.EVENT_STOP;
            }
            if (sym === Clutter.KEY_h || sym === Clutter.KEY_H) {
                this._toggleHalo();
                return Clutter.EVENT_STOP;
            }
        } catch (err) {
            console.error('[CaptureUI] Key press handling error: ' + err);
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _onButtonPress(event) {
        const [x, y] = event.get_coords();

        // If clicking inside control card or top pill, do not interfere
        if (this._isPointInsideActor(this._controlCard, x, y) || this._isPointInsideActor(this._topPill, x, y)) {
            return Clutter.EVENT_PROPAGATE;
        }

        if (this._mode === 'screen') {
            this._triggerCapture();
            return Clutter.EVENT_STOP;
        }

        if (this._mode === 'window') {
            if (this._hoveredWindow) {
                this._triggerCapture();
            }
            return Clutter.EVENT_STOP;
        }

        // Selection mode interaction
        if (this._mode === 'selection') {
            const r = this._selectionRect;
            const hw = 16;

            // Check corner resize handles
            if (r.width > 5 && r.height > 5) {
                if (Math.hypot(x - r.x, y - r.y) <= hw) {
                    this._dragState = { type: 'resize', handle: 'TL', startX: x, startY: y, initialRect: { ...r } };
                    this._setDragVisualState(true);
                    return Clutter.EVENT_STOP;
                }
                if (Math.hypot(x - (r.x + r.width), y - r.y) <= hw) {
                    this._dragState = { type: 'resize', handle: 'TR', startX: x, startY: y, initialRect: { ...r } };
                    this._setDragVisualState(true);
                    return Clutter.EVENT_STOP;
                }
                if (Math.hypot(x - r.x, y - (r.y + r.height)) <= hw) {
                    this._dragState = { type: 'resize', handle: 'BL', startX: x, startY: y, initialRect: { ...r } };
                    this._setDragVisualState(true);
                    return Clutter.EVENT_STOP;
                }
                if (Math.hypot(x - (r.x + r.width), y - (r.y + r.height)) <= hw) {
                    this._dragState = { type: 'resize', handle: 'BR', startX: x, startY: y, initialRect: { ...r } };
                    this._setDragVisualState(true);
                    return Clutter.EVENT_STOP;
                }

                // Check inside rectangle for move or double click
                if (x >= r.x && x <= r.x + r.width && y >= r.y && y <= r.y + r.height) {
                    if (event.get_click_count() === 2) {
                        this._triggerCapture();
                        return Clutter.EVENT_STOP;
                    }
                    this._dragState = { type: 'move', startX: x, startY: y, initialRect: { ...r } };
                    this._setDragVisualState(true);
                    return Clutter.EVENT_STOP;
                }
            }

            // Start new selection drag
            this._dragState = { type: 'draw', startX: x, startY: y };
            this._selectionRect = { x, y, width: 0, height: 0 };
            this._setDragVisualState(true);
            this._updateDimming();
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    _onMotion(event) {
        const [x, y] = event.get_coords();
        const overControls = this._isPointInsideActor(this._controlCard, x, y) || this._isPointInsideActor(this._topPill, x, y);

        // Control card / top pill hover cursor (cached via _lastCursorType)
        if (overControls) {
            this._setCursorType(Clutter.CursorType.DEFAULT);
        } else if (this._mode === 'selection' && !this._dragState) {
            const r = this._selectionRect;
            const hw = 16;
            if (r.width > 5 && r.height > 5) {
                if (Math.hypot(x - r.x, y - r.y) <= hw || Math.hypot(x - (r.x + r.width), y - (r.y + r.height)) <= hw) {
                    this._setCursorType(Clutter.CursorType.NWSE_RESIZE);
                } else if (Math.hypot(x - (r.x + r.width), y - r.y) <= hw || Math.hypot(x - r.x, y - (r.y + r.height)) <= hw) {
                    this._setCursorType(Clutter.CursorType.NESW_RESIZE);
                } else if (x >= r.x && x <= r.x + r.width && y >= r.y && y <= r.y + r.height) {
                    this._setCursorType(Clutter.CursorType.MOVE);
                } else {
                    this._setCursorType(Clutter.CursorType.CROSSHAIR);
                }
            } else {
                this._setCursorType(Clutter.CursorType.CROSSHAIR);
            }
        } else if (this._mode === 'screen' || this._mode === 'window') {
            this._setCursorType(Clutter.CursorType.POINTER);
        }

        if (this._mode === 'screen') {
            if (!overControls)
                this._updateScreenHighlight(x, y);
            return Clutter.EVENT_PROPAGATE;
        }

        if (this._mode === 'window') {
            if (overControls) {
                this._hoveredWindow = null;
                if (this._windowHighlight.visible)
                    this._windowHighlight.visible = false;
                return Clutter.EVENT_PROPAGATE;
            }
            this._updateWindowUnderCursor(x, y);
            return Clutter.EVENT_PROPAGATE;
        }

        if (this._mode === 'selection' && this._dragState) {
            const ds = this._dragState;
            const monitor = this._findMonitorAt(ds.startX, ds.startY) || Main.layoutManager.primaryMonitor;

            if (ds.type === 'draw') {
                const norm = this._normalizeRect(ds.startX, ds.startY, x, y, monitor);
                this._selectionRect = norm;
                this._updateDimming();
            } else if (ds.type === 'move') {
                const dx = x - ds.startX;
                const dy = y - ds.startY;
                const newX = Math.max(monitor.x, Math.min(monitor.x + monitor.width - ds.initialRect.width, ds.initialRect.x + dx));
                const newY = Math.max(monitor.y, Math.min(monitor.y + monitor.height - ds.initialRect.height, ds.initialRect.y + dy));
                this._selectionRect = { x: newX, y: newY, width: ds.initialRect.width, height: ds.initialRect.height };
                this._updateDimming();
            } else if (ds.type === 'resize') {
                let x1 = ds.initialRect.x;
                let y1 = ds.initialRect.y;
                let x2 = ds.initialRect.x + ds.initialRect.width;
                let y2 = ds.initialRect.y + ds.initialRect.height;

                if (ds.handle === 'TL') { x1 = x; y1 = y; }
                else if (ds.handle === 'TR') { x2 = x; y1 = y; }
                else if (ds.handle === 'BL') { x1 = x; y2 = y; }
                else if (ds.handle === 'BR') { x2 = x; y2 = y; }

                this._selectionRect = this._normalizeRect(x1, y1, x2, y2, monitor);
                this._updateDimming();
            }
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    _onButtonRelease(event) {
        if (this._dragState) {
            this._dragState = null;
            this._setDragVisualState(false);
            if (this._selectionRect.width < 5 || this._selectionRect.height < 5) {
                this._selectionBox.visible = false;
                this._clearDimming();
            }
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _normalizeRect(x1, y1, x2, y2, monitor) {
        const minX = Math.max(monitor.x, Math.min(x1, x2));
        const maxX = Math.min(monitor.x + monitor.width, Math.max(x1, x2));
        const minY = Math.max(monitor.y, Math.min(y1, y2));
        const maxY = Math.min(monitor.y + monitor.height, Math.max(y1, y2));
        return {
            x: Math.round(minX),
            y: Math.round(minY),
            width: Math.round(Math.max(0, maxX - minX)),
            height: Math.round(Math.max(0, maxY - minY)),
        };
    }

    // --- Capture & Recording Execution ---

    _triggerCapture() {
        if (this._mediaMode === 'photo') {
            this._capturePhoto();
        } else {
            this._startVideoRecording();
        }
    }

    _getScreenshotsDir() {
        const picturesDir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) || `${GLib.get_home_dir()}/Pictures`;
        const folderName = I18n.t('folder_screenshots') || 'Screenshots';
        const screenshotsDir = `${picturesDir}/${folderName}`;
        GLib.mkdir_with_parents(screenshotsDir, 0o755);
        return screenshotsDir;
    }

    _uniquePngPath(screenshotsDir, prefix, timeStr) {
        let candidate = `${screenshotsDir}/${prefix}_${timeStr}.png`;
        let suffix = 1;
        while (Gio.File.new_for_path(candidate).query_exists(null)) {
            candidate = `${screenshotsDir}/${prefix}_${timeStr}_${suffix}.png`;
            suffix++;
        }
        return candidate;
    }

    _drawHaloOnPng(targetPath, targetRect, cursorInfo, frozenScale = 1.0) {
        const pt = cursorInfo?.point;
        if (!pt || !targetRect)
            return;
        if (pt.x < targetRect.x || pt.x > (targetRect.x + targetRect.width) ||
            pt.y < targetRect.y || pt.y > (targetRect.y + targetRect.height))
            return;
        try {
            const surface = Cairo.ImageSurface.createFromPNG(targetPath);
            const cr = new Cairo.Context(surface);
            const cx = (pt.x - targetRect.x) * frozenScale;
            const cy = (pt.y - targetRect.y) * frozenScale;
            const radius = 24 * frozenScale;
            cr.newPath();
            cr.arc(cx, cy, radius, 0, 2 * Math.PI);
            cr.setSourceRGBA(6 / 255, 182 / 255, 212 / 255, 0.30);
            cr.fillPreserve();
            cr.setSourceRGBA(6 / 255, 182 / 255, 212 / 255, 0.85);
            cr.setLineWidth(2.5 * frozenScale);
            cr.stroke();
            cr.$dispose();
            surface.writeToPNG(targetPath);
            surface.finish();
        } catch (err) {
            console.error('[CaptureUI] Failed drawing cursor halo onto PNG: ' + err);
        }
    }

    _preparePhotoHalo(targetPath, stream, haloActive, targetRect, cursorInfo, frozenScale) {
        try { stream.close(null); } catch (_e) {}
        if (haloActive)
            this._drawHaloOnPng(targetPath, targetRect, cursorInfo, frozenScale);
    }

    _finishPhotoSuccess(targetPath, stream) {
        try { stream.close(null); } catch (_e) {}
        this._copyImageToClipboard(targetPath);
        this._notifyCaptureComplete(targetPath, 'photo');
    }

    _capturePhotoFallback(targetPath, targetRect, captureMode, includeCursor, haloActive = false, cursorInfo = null, frozenScale = 1.0) {
        let stream = null;
        try {
            const file = Gio.File.new_for_path(targetPath);
            stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
        } catch (err) {
            console.error('[CaptureUI] Fallback file stream error: ' + err);
            return;
        }
        const shooter = new Shell.Screenshot();
        if (captureMode === 'screen') {
            shooter.screenshot(includeCursor, stream, (_o, res) => {
                try {
                    shooter.screenshot_finish(res);
                    this._preparePhotoHalo(targetPath, stream, haloActive, targetRect, cursorInfo, frozenScale);
                    this._finishPhotoSuccess(targetPath, stream);
                } catch (err) {
                    console.error('[CaptureUI] screenshot fallback error: ' + err);
                    try { stream.close(null); } catch (_e) {}
                }
            });
        } else if (captureMode === 'window') {
            shooter.screenshot_window(true, includeCursor, stream, (_o, res) => {
                try {
                    shooter.screenshot_window_finish(res);
                    this._preparePhotoHalo(targetPath, stream, haloActive, targetRect, cursorInfo, frozenScale);
                    this._finishPhotoSuccess(targetPath, stream);
                } catch (err) {
                    console.error('[CaptureUI] screenshot_window fallback error: ' + err);
                    try { stream.close(null); } catch (_e) {}
                }
            });
        } else {
            shooter.screenshot_area(targetRect.x, targetRect.y, targetRect.width, targetRect.height, stream, (_o, res) => {
                try {
                    shooter.screenshot_area_finish(res);
                    this._preparePhotoHalo(targetPath, stream, haloActive, targetRect, cursorInfo, frozenScale);
                    this._finishPhotoSuccess(targetPath, stream);
                } catch (err) {
                    console.error('[CaptureUI] screenshot_area fallback error: ' + err);
                    try { stream.close(null); } catch (_e) {}
                }
            });
        }
    }

    _capturePhoto() {
        const [cx, cy] = global.get_pointer();
        const monitor = this._findMonitorAt(cx, cy) || Main.layoutManager.primaryMonitor;
        const captureMode = this._mode;
        const includeCursor = this._includeCursor;
        const haloActive = this._haloActive;
        const frozenContent = this._frozenContent;
        const frozenScale = this._frozenScale || 1.0;
        const cursorInfo = this._cursorInfo;

        let targetRect = { x: monitor.x, y: monitor.y, width: monitor.width, height: monitor.height };

        if (captureMode === 'selection') {
            if (this._selectionRect.width >= 5 && this._selectionRect.height >= 5) {
                targetRect = { ...this._selectionRect };
            }
        } else if (captureMode === 'window') {
            if (this._hoveredWindow) {
                const rect = this._hoveredWindow.get_frame_rect();
                targetRect = { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
            }
        }

        // Target path (collision-safe for bursts in the same second)
        const screenshotsDir = this._getScreenshotsDir();

        const now = GLib.DateTime.new_now_local();
        const timeStr = now.format('%Y-%m-%d_%H-%M-%S');
        const prefix = I18n.t('filename_prefix');
        const targetPath = this._uniquePngPath(screenshotsDir, prefix, timeStr);

        // Hide UI cleanly before async file write/fallback
        this.close();

        // Shutter sound
        this._playShutterSound();

        // Prefer GPU-frozen composite_to_stream so cursor toggle and frozen menus/tooltips are preserved accurately
        const texture = frozenContent?.get_texture ? frozenContent.get_texture() : frozenContent;
        if (texture && typeof Shell.Screenshot.composite_to_stream === 'function') {
            let stream = null;
            try {
                const file = Gio.File.new_for_path(targetPath);
                stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
                const rawCursorContent = includeCursor ? cursorInfo?.content : null;
                const cursorTexture = rawCursorContent?.get_texture ? rawCursorContent.get_texture() : (rawCursorContent || null);
                const cursorX = Math.round((cursorInfo?.point?.x || 0) * frozenScale);
                const cursorY = Math.round((cursorInfo?.point?.y || 0) * frozenScale);
                const cursorScale = cursorInfo?.scale || 1.0;

                Shell.Screenshot.composite_to_stream(
                    texture,
                    Math.round(targetRect.x * frozenScale),
                    Math.round(targetRect.y * frozenScale),
                    Math.round(targetRect.width * frozenScale),
                    Math.round(targetRect.height * frozenScale),
                    frozenScale,
                    cursorTexture,
                    cursorX,
                    cursorY,
                    cursorScale,
                    stream,
                    (_obj, res) => {
                        try {
                            Shell.Screenshot.composite_to_stream_finish(res);
                            try { stream.close(null); } catch (_e) {}
                            if (haloActive)
                                this._drawHaloOnPng(targetPath, targetRect, cursorInfo, frozenScale);
                            this._finishPhotoSuccess(targetPath, stream);
                        } catch (err) {
                            console.error('[CaptureUI] composite_to_stream failed, falling back: ' + err);
                            try { stream.close(null); } catch (_e) {}
                            this._capturePhotoFallback(targetPath, targetRect, captureMode, includeCursor, haloActive, cursorInfo, frozenScale);
                        }
                    }
                );
                return;
            } catch (err) {
                console.error('[CaptureUI] composite_to_stream init failed, falling back: ' + err);
                try { stream?.close(null); } catch (_e) {}
            }
        }

        this._capturePhotoFallback(targetPath, targetRect, captureMode, includeCursor, haloActive, cursorInfo, frozenScale);
    }

    captureSilentScreenshot() {
        const now = GLib.get_monotonic_time();
        if (now - this._lastSilentShotTime < 350000) return; // Debounce 350ms
        this._lastSilentShotTime = now;

        if (this._recordingIndicator && this._recordingIndicator.flashCameraIcon) {
            this._recordingIndicator.flashCameraIcon();
        }

        this._playShutterSound();

        const screenshotsDir = this._getScreenshotsDir();

        const dt = GLib.DateTime.new_now_local();
        const timeStr = dt.format('%Y-%m-%d_%H-%M-%S');
        const targetPath = this._uniquePngPath(screenshotsDir, I18n.t('filename_prefix'), timeStr);

        const file = Gio.File.new_for_path(targetPath);
        const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);

        const shooter = new Shell.Screenshot();
        shooter.screenshot(this._includeCursor, stream, (obj, res) => {
            try {
                shooter.screenshot_finish(res);
                this._finishPhotoSuccess(targetPath, stream);
            } catch (err) {
                try { stream.close(null); } catch (e) {}
            }
        });
    }

    captureWindowNow(windowId) {
        try {
            let targetWin = null;
            if (global.get_window_actors) {
                for (const actor of global.get_window_actors()) {
                    const win = actor.meta_window;
                    if (!win) continue;
                    const wid = win.get_id ? win.get_id() : win.get_stable_sequence();
                    if (Number(wid) === Number(windowId)) {
                        targetWin = win;
                        break;
                    }
                }
            }

            if (!targetWin) return false;

            targetWin.activate(global.get_current_time());

            const screenshotsDir = this._getScreenshotsDir();

            const dt = GLib.DateTime.new_now_local();
            const timeStr = dt.format('%Y-%m-%d_%H-%M-%S');
            const targetPath = this._uniquePngPath(screenshotsDir, I18n.t('filename_prefix'), timeStr);

            this._playShutterSound();

            const file = Gio.File.new_for_path(targetPath);
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);

            const shooter = new Shell.Screenshot();
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 80, () => {
                shooter.screenshot_window(true, this._includeCursor, stream, (obj, res) => {
                    try {
                        shooter.screenshot_window_finish(res);
                        stream.close(null);
                        this._copyImageToClipboard(targetPath);
                        this._notifyCaptureComplete(targetPath, 'photo');
                    } catch (e) {
                        try { stream.close(null); } catch (ce) {}
                    }
                });
                return GLib.SOURCE_REMOVE;
            });
            return true;
        } catch (err) {
            console.error('[CaptureUI] captureWindowNow error: ' + err);
            return false;
        }
    }

    _playShutterSound() {
        try {
            GLib.spawn_command_line_async('canberra-gtk-play -i camera-shutter');
        } catch (e) {
            // Sound fallback
        }
    }

    _copyImageToClipboard(filePath) {
        try {
            const [ok, contents] = Gio.File.new_for_path(filePath).load_contents(null);
            if (ok && contents && contents.length > 0) {
                const pngBytes = new GLib.Bytes(contents);
                St.Clipboard.get_default().set_content(
                    St.ClipboardType.CLIPBOARD,
                    'image/png',
                    pngBytes
                );
            }
        } catch (e) {
            console.error('[CaptureUI] Clipboard image copy error: ' + e);
        }
    }

    _getNotificationSource(mediaType = 'photo') {
        const iconName = mediaType === 'video' ? 'camera-video-symbolic' : 'camera-photo-symbolic';
        if (!this._notifSource) {
            this._notifSource = new MessageTray.Source({
                title: I18n.t('app_name'),
                iconName: iconName,
            });
            this._notifSource.connect('destroy', () => {
                this._notifSource = null;
            });
            Main.messageTray.add(this._notifSource);
        }
        return this._notifSource;
    }

    _launchBackgroundCommand(argv) {
        try {
            const scoped = new Gio.Subprocess({
                argv: ['systemd-run', '--user', '--scope', '--quiet', ...argv],
                flags: Gio.SubprocessFlags.NONE,
            });
            scoped.init(null);
            return;
        } catch (err) {
            try {
                const sub = new Gio.Subprocess({
                    argv: argv,
                    flags: Gio.SubprocessFlags.NONE,
                });
                sub.init(null);
            } catch (e) {
                console.error('[CaptureUI] Failed to launch background command: ' + e);
            }
        }
    }

    _showFileInFolder(filePath) {
        const file = Gio.File.new_for_path(filePath);
        const uri = file.get_uri();
        try {
            Gio.DBus.session.call(
                'org.freedesktop.FileManager1',
                '/org/freedesktop/FileManager1',
                'org.freedesktop.FileManager1',
                'ShowItems',
                new GLib.Variant('(ass)', [[uri], '']),
                null,
                Gio.DBusCallFlags.NONE,
                3000,
                null,
                (conn, res) => {
                    try {
                        conn.call_finish(res);
                    } catch (err) {
                        this._openParentFolderFallback(file);
                    }
                }
            );
        } catch (e) {
            this._openParentFolderFallback(file);
        }
    }

    _openParentFolderFallback(file) {
        try {
            const parent = file.get_parent();
            if (parent) {
                Gio.AppInfo.launch_default_for_uri(
                    parent.get_uri(),
                    global.create_app_launch_context(global.get_current_time(), -1)
                );
            }
        } catch (err) {
            console.error('[CaptureUI] Failed to open parent folder: ' + err);
        }
    }

    _notifyCaptureComplete(filePath, mediaType = 'photo') {
        try {
            const isVideo = (mediaType === 'video');
            const source = this._getNotificationSource(mediaType);
            const title = isVideo ? I18n.t('notif_video_title') : I18n.t('notif_photo_title');
            const body = isVideo
                ? `${GLib.path_get_basename(filePath)} — ${I18n.t('notif_video_body')}`
                : I18n.t('notif_photo_body');

            let gicon = null;
            if (!isVideo) {
                try {
                    const photoFile = Gio.File.new_for_path(filePath);
                    if (photoFile.query_exists(null)) {
                        gicon = Gio.FileIcon.new(photoFile);
                    }
                } catch (e) {}
                if (!gicon) {
                    gicon = new Gio.ThemedIcon({ name: 'camera-photo-symbolic' });
                }
            } else {
                gicon = new Gio.ThemedIcon({ name: 'camera-video-symbolic' });
            }

            const notification = new MessageTray.Notification({
                source,
                title,
                body,
                gicon,
            });

            notification.addAction(I18n.t('notif_action_edit'), () => {
                try { Main.overview?.hide(); } catch (e) {}
                try { Main.panel?.closeCalendar?.(); } catch (e) {}
                if (isVideo) {
                    this._launchBackgroundCommand(['sadeem-video-editor', filePath]);
                } else {
                    this._launchBackgroundCommand(['sadeem-gallery', '--edit', filePath]);
                }
            });

            notification.addAction(I18n.t('notif_action_show_folder'), () => {
                try { Main.overview?.hide(); } catch (e) {}
                try { Main.panel?.closeCalendar?.(); } catch (e) {}
                this._showFileInFolder(filePath);
            });

            notification.connect('activated', () => {
                try { Main.overview?.hide(); } catch (e) {}
                try { Main.panel?.closeCalendar?.(); } catch (e) {}
                this._launchBackgroundCommand(['sadeem-gallery', filePath]);
            });

            source.addNotification(notification);
        } catch (err) {
            console.error('[CaptureUI] _notifyCaptureComplete error: ' + err);
        }
    }

    // --- Video Recorder Integration ---

    _startVideoRecording() {
        const [cx, cy] = global.get_pointer();
        const monitor = this._findMonitorAt(cx, cy) || Main.layoutManager.primaryMonitor;
        const monitorIndex = (Main.layoutManager.monitors ? Main.layoutManager.monitors.indexOf(monitor) : 0);

        // Close UI first
        this.close();

        // Suppress yellow GNOME indicator immediately before Portal starts
        if (this._recordingIndicator && typeof this._recordingIndicator.setGnomeIndicatorSuppressed === 'function') {
            this._recordingIndicator.setGnomeIndicatorSuppressed(true);
        }

        // Enable Halo if toggled
        if (this._haloActive && this._haloManager) {
            this._haloManager.setActive(true);
        }

        // Build command line arguments for recorder.py
        const argv = ['/usr/share/sadeem-capture/recorder.py'];
        argv.push('--mode', this._mode);

        if (this._mode === 'selection' && this._selectionRect.width >= 5 && this._selectionRect.height >= 5) {
            const locX = Math.max(0, Math.round(this._selectionRect.x - (monitor?.x || 0)));
            const locY = Math.max(0, Math.round(this._selectionRect.y - (monitor?.y || 0)));
            const locW = Math.max(2, Math.round(this._selectionRect.width));
            const locH = Math.max(2, Math.round(this._selectionRect.height));
            argv.push('--crop', `${locX},${locY},${locW},${locH}`);
        }

        if (monitor?.width > 0 && monitor?.height > 0) {
            argv.push('--monitor-size', `${Math.round(monitor.width)},${Math.round(monitor.height)}`);
        }
        argv.push('--monitor', String(Math.max(0, monitorIndex)));
        argv.push('--resolution', this._resolution);
        argv.push('--fps', String(this._fps));
        argv.push('--codec', this._codec);
        argv.push('--audio', this._audioMode);

        if (this._selectedMic) {
            argv.push('--mic', this._selectedMic);
        }
        if (this._includeCursor) {
            argv.push('--cursor');
        }

        try {
            this._recorderSubprocess = new Gio.Subprocess({
                argv: argv,
                flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
            });
            this._recorderSubprocess.init(null);

            // Read output asynchronously
            const pipe = this._recorderSubprocess.get_stdout_pipe();
            const dataStream = new Gio.DataInputStream({ base_stream: pipe });
            this._readRecorderOutput(dataStream);

            // Await process termination
            this._recorderSubprocess.wait_check_async(null, (proc, res) => {
                let success = false;
                try {
                    proc.wait_check_finish(res);
                    success = true;
                } catch (e) {
                    success = false;
                }

                const exitStatus = proc.get_exit_status();
                this._onRecorderFinished(exitStatus, success);
            });
        } catch (err) {
            console.error('[CaptureUI] Failed to start recorder.py: ' + err);
            this._cleanupRecordingState();
            Main.notify(I18n.t('app_name'), I18n.t('error_rec_start_failed'));
        }
    }

    _readRecorderOutput(dataStream) {
        dataStream.read_line_async(GLib.PRIORITY_DEFAULT, null, (stream, res) => {
            try {
                const [line] = stream.read_line_finish_utf8(res);
                if (line !== null) {
                    this._processRecorderLine(line);
                    this._readRecorderOutput(stream); // Continue reading next line
                }
            } catch (e) {
                // End of stream or error
            }
        });
    }

    _processRecorderLine(line) {
        if (!line) return;
        const trimmed = line.trim();

        if (trimmed === 'STATUS:RECORDING') {
            this._isRecording = true;
            if (this._recordingIndicator) {
                this._recordingIndicator.setRecordingActive(true);
            }
        } else if (trimmed.startsWith('STATUS:SAVED:')) {
            // STATUS:SAVED:<size>:<path>
            const parts = trimmed.split(':');
            if (parts.length >= 4) {
                const size = parts[2];
                const path = parts.slice(3).join(':');
                this._savedVideoInfo = { size, path };
            }
        }
    }

    _onRecorderFinished(exitStatus, isOk) {
        this._cleanupRecordingState();

        if (exitStatus === 0 && this._savedVideoInfo) {
            const { path } = this._savedVideoInfo;
            this._notifyCaptureComplete(path, 'video');
            this._savedVideoInfo = null;
        } else if (exitStatus === 2) {
            // User canceled Portal prompt: silent exit, no notification
            this._savedVideoInfo = null;
        } else {
            // Real technical error
            Main.notify(I18n.t('app_name'), I18n.t('error_rec_start_failed'));
            this._savedVideoInfo = null;
        }
    }

    _cleanupRecordingState() {
        this._isRecording = false;
        this._recorderSubprocess = null;

        if (this._recordingIndicator) {
            this._recordingIndicator.setRecordingActive(false);
            this._recordingIndicator.setGnomeIndicatorSuppressed(false);
        }
        if (this._haloManager) {
            this._haloManager.setActive(false);
        }
    }

    stopRecording() {
        if (this._recorderSubprocess) {
            try {
                this._recorderSubprocess.send_signal(2 /* SIGINT */);
            } catch (e) {
                try {
                    this._recorderSubprocess.send_signal(15 /* SIGTERM */);
                } catch (ce) {}
            }
            return true;
        }
        return false;
    }
});
