import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';

const CaptureHelperIface = `
<node>
  <interface name="org.sadeem.CaptureHelper">
    <method name="Ping">
      <arg type="s" name="reply" direction="out"/>
    </method>
    <method name="OpenUI">
      <arg type="s" name="mode" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="StopRecording">
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="SilentScreenshot">
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="CaptureWindowNow">
      <arg type="u" name="window_id" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="CaptureScreen">
      <arg type="b" name="include_cursor" direction="in"/>
      <arg type="s" name="file_path" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="CaptureArea">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
      <arg type="i" name="width" direction="in"/>
      <arg type="i" name="height" direction="in"/>
      <arg type="b" name="include_cursor" direction="in"/>
      <arg type="s" name="file_path" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="CaptureWindow">
      <arg type="u" name="window_id" direction="in"/>
      <arg type="b" name="include_frame" direction="in"/>
      <arg type="b" name="include_cursor" direction="in"/>
      <arg type="s" name="file_path" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="ListWindows">
      <arg type="s" name="windows_json" direction="out"/>
    </method>
    <method name="GetWindowList">
      <arg type="s" name="windows_json" direction="out"/>
    </method>
    <method name="SetHaloActive">
      <arg type="b" name="active" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="SetRecordingState">
      <arg type="b" name="active" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="SetGnomeIndicatorSuppressed">
      <arg type="b" name="suppressed" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
    <method name="FlashCameraIndicator">
      <arg type="b" name="success" direction="out"/>
    </method>
    <signal name="StopRecordingRequested"/>
    <signal name="SilentScreenshotRequested"/>
  </interface>
</node>`;

export class CaptureHelperService {
    constructor(haloManager = null, recordingIndicator = null, captureUI = null) {
        this._haloManager = haloManager;
        this._recordingIndicator = recordingIndicator;
        this._captureUI = captureUI;
        this._screenshotService = new Shell.Screenshot();
        this._dbusImpl = null;
        this._nameOwnerId = null;
    }

    setCaptureUI(captureUI) {
        this._captureUI = captureUI;
    }

    setRecordingIndicator(indicator) {
        this._recordingIndicator = indicator;
    }

    enable() {
        const nodeInfo = Gio.DBusNodeInfo.new_for_xml(CaptureHelperIface);
        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(nodeInfo.interfaces[0], this);
        this._dbusImpl.export(Gio.DBus.session, '/org/sadeem/CaptureHelper');
        this._nameOwnerId = Gio.DBus.session.own_name(
            'org.sadeem.CaptureHelper',
            Gio.BusNameOwnerFlags.REPLACE,
            null,
            null
        );
    }

    disable() {
        if (this._dbusImpl) {
            this._dbusImpl.unexport();
            this._dbusImpl = null;
        }
        if (this._nameOwnerId) {
            Gio.DBus.session.unown_name(this._nameOwnerId);
            this._nameOwnerId = null;
        }
    }

    Ping() {
        return 'pong';
    }

    OpenUI(mode) {
        try {
            if (this._captureUI) {
                let initialMode = 'selection';
                let initialMedia = 'photo';

                if (mode === 'video' || mode === '--video') {
                    initialMode = 'selection';
                    initialMedia = 'video';
                } else if (mode === 'screen' || mode === '--screen') {
                    initialMode = 'screen';
                    initialMedia = 'photo';
                } else if (mode === 'window' || mode === '--window') {
                    initialMode = 'window';
                    initialMedia = 'photo';
                } else if (mode === 'area' || mode === '--area' || mode === 'selection' || mode === '--selection') {
                    initialMode = 'selection';
                    initialMedia = 'photo';
                }

                this._captureUI.open(initialMode, initialMedia);
                return true;
            }
        } catch (e) {
            console.error('[CaptureHelper] OpenUI error: ' + e);
        }
        return false;
    }

    StopRecording() {
        if (this._captureUI && typeof this._captureUI.stopRecording === 'function') {
            return this._captureUI.stopRecording();
        }
        this.emitStopRecordingRequested();
        return true;
    }

    SilentScreenshot() {
        if (this._captureUI && typeof this._captureUI.captureSilentScreenshot === 'function') {
            this._captureUI.captureSilentScreenshot();
            return true;
        }
        this.emitSilentScreenshotRequested();
        return true;
    }

    CaptureWindowNow(windowId) {
        if (this._captureUI && typeof this._captureUI.captureWindowNow === 'function') {
            return this._captureUI.captureWindowNow(windowId);
        }
        return false;
    }

    CaptureScreenAsync([includeCursor, filePath], invocation) {
        try {
            const file = Gio.File.new_for_path(filePath);
            const parent = file.get_parent();
            if (parent && !parent.query_exists(null)) {
                parent.make_directory_with_parents(null);
            }
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
            this._screenshotService.screenshot(includeCursor, stream, (obj, res) => {
                try {
                    this._screenshotService.screenshot_finish(res);
                    stream.close(null);
                    this._copyPngToClipboard(filePath);
                    invocation.return_value(new GLib.Variant('(b)', [true]));
                } catch (e) {
                    console.error('[CaptureHelper] screenshot_finish error: ' + e);
                    try { stream.close(null); } catch (ce) {}
                    invocation.return_value(new GLib.Variant('(b)', [false]));
                }
            });
        } catch (err) {
            console.error('[CaptureHelper] CaptureScreen error: ' + err);
            invocation.return_value(new GLib.Variant('(b)', [false]));
        }
    }

    CaptureAreaAsync([x, y, width, height, includeCursor, filePath], invocation) {
        try {
            const file = Gio.File.new_for_path(filePath);
            const parent = file.get_parent();
            if (parent && !parent.query_exists(null)) {
                parent.make_directory_with_parents(null);
            }
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);
            this._screenshotService.screenshot_area(x, y, width, height, stream, (obj, res) => {
                try {
                    this._screenshotService.screenshot_area_finish(res);
                    stream.close(null);
                    this._copyPngToClipboard(filePath);
                    invocation.return_value(new GLib.Variant('(b)', [true]));
                } catch (e) {
                    console.error('[CaptureHelper] screenshot_area_finish error: ' + e);
                    try { stream.close(null); } catch (ce) {}
                    invocation.return_value(new GLib.Variant('(b)', [false]));
                }
            });
        } catch (err) {
            console.error('[CaptureHelper] CaptureArea error: ' + err);
            invocation.return_value(new GLib.Variant('(b)', [false]));
        }
    }

    CaptureWindowAsync([windowId, includeFrame, includeCursor, filePath], invocation) {
        try {
            let targetWin = null;
            if (typeof global !== 'undefined' && global.get_window_actors) {
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

            if (!targetWin) {
                console.error('[CaptureHelper] Window ID not found: ' + windowId);
                invocation.return_value(new GLib.Variant('(b)', [false]));
                return;
            }

            targetWin.activate(global.get_current_time());

            const file = Gio.File.new_for_path(filePath);
            const parent = file.get_parent();
            if (parent && !parent.query_exists(null)) {
                parent.make_directory_with_parents(null);
            }
            const stream = file.replace(null, false, Gio.FileCreateFlags.NONE, null);

            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
                try {
                    this._screenshotService.screenshot_window(includeFrame, includeCursor, stream, (obj, res) => {
                        try {
                            this._screenshotService.screenshot_window_finish(res);
                            stream.close(null);
                            this._copyPngToClipboard(filePath);
                            invocation.return_value(new GLib.Variant('(b)', [true]));
                        } catch (e) {
                            console.error('[CaptureHelper] screenshot_window_finish error: ' + e);
                            try { stream.close(null); } catch (ce) {}
                            invocation.return_value(new GLib.Variant('(b)', [false]));
                        }
                    });
                } catch (we) {
                    console.error('[CaptureHelper] screenshot_window error: ' + we);
                    try { stream.close(null); } catch (ce) {}
                    invocation.return_value(new GLib.Variant('(b)', [false]));
                }
                return GLib.SOURCE_REMOVE;
            });
        } catch (err) {
            console.error('[CaptureHelper] CaptureWindow error: ' + err);
            invocation.return_value(new GLib.Variant('(b)', [false]));
        }
    }

    GetWindowList() {
        return this.ListWindows();
    }

    ListWindows() {
        try {
            const list = [];
            if (typeof global !== 'undefined' && global.get_window_actors) {
                for (const actor of global.get_window_actors()) {
                    const win = actor.meta_window;
                    if (!win || win.is_hidden() || win.is_override_redirect()) continue;
                    const rect = win.get_frame_rect();
                    if (rect.width <= 0 || rect.height <= 0) continue;

                    let appName = win.get_wm_class() || '';
                    let iconName = 'application-x-executable';
                    const tracker = Shell.WindowTracker ? Shell.WindowTracker.get_default() : null;
                    if (tracker) {
                        const app = tracker.get_window_app(win);
                        if (app) {
                            appName = app.get_name();
                            const gicon = app.get_app_info()?.get_icon();
                            if (gicon) {
                                iconName = gicon.to_string();
                            }
                        }
                    }

                    const wid = win.get_id ? win.get_id() : win.get_stable_sequence();

                    list.push({
                        id: Number(wid),
                        title: win.get_title() || '',
                        appName: appName,
                        iconName: iconName,
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height,
                        monitor: win.get_monitor ? win.get_monitor() : 0,
                    });
                }
            }
            return JSON.stringify(list);
        } catch (e) {
            console.error('[CaptureHelper] ListWindows error: ' + e);
            return '[]';
        }
    }

    SetHaloActive(active) {
        if (this._haloManager) {
            this._haloManager.setActive(active);
            return true;
        }
        return false;
    }

    SetRecordingState(active) {
        if (this._recordingIndicator) {
            this._recordingIndicator.setRecordingActive(active);
            return true;
        }
        return false;
    }

    SetGnomeIndicatorSuppressed(suppressed) {
        if (this._recordingIndicator && typeof this._recordingIndicator.setGnomeIndicatorSuppressed === 'function') {
            this._recordingIndicator.setGnomeIndicatorSuppressed(suppressed);
            return true;
        }
        return false;
    }

    FlashCameraIndicator() {
        if (this._recordingIndicator && this._recordingIndicator.flashCameraIcon) {
            this._recordingIndicator.flashCameraIcon();
            return true;
        }
        return false;
    }

    _copyPngToClipboard(filePath) {
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
            console.error('[CaptureHelper] Clipboard image copy error: ' + e);
        }
    }

    emitStopRecordingRequested() {
        if (this._dbusImpl) {
            this._dbusImpl.emit_signal(
                'StopRecordingRequested',
                null
            );
        }
    }

    emitSilentScreenshotRequested() {
        if (this._dbusImpl) {
            this._dbusImpl.emit_signal(
                'SilentScreenshotRequested',
                null
            );
        }
    }
}
