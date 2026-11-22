import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';

const CaptureHelperIface = `
<node>
  <interface name="org.sadeem.CaptureHelper">
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
    <method name="SetHaloActive">
      <arg type="b" name="active" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>
  </interface>
</node>`;

export class CaptureHelperService {
    constructor(haloManager) {
        this._haloManager = haloManager;
        this._screenshotService = new Shell.Screenshot();
        this._dbusImpl = null;
        this._nameOwnerId = null;
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

    CaptureScreen(includeCursor, filePath) {
        return new Promise((resolve) => {
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
                        resolve([true]);
                    } catch (e) {
                        console.error('[CaptureHelper] screenshot_finish error: ' + e);
                        try { stream.close(null); } catch (ce) {}
                        resolve([false]);
                    }
                });
            } catch (err) {
                console.error('[CaptureHelper] CaptureScreen error: ' + err);
                resolve([false]);
            }
        });
    }

    CaptureArea(x, y, width, height, includeCursor, filePath) {
        return new Promise((resolve) => {
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
                        resolve([true]);
                    } catch (e) {
                        console.error('[CaptureHelper] screenshot_area_finish error: ' + e);
                        try { stream.close(null); } catch (ce) {}
                        resolve([false]);
                    }
                });
            } catch (err) {
                console.error('[CaptureHelper] CaptureArea error: ' + err);
                resolve([false]);
            }
        });
    }

    CaptureWindow(windowId, includeFrame, includeCursor, filePath) {
        return new Promise((resolve) => {
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

                if (!targetWin) {
                    console.error('[CaptureHelper] Window ID not found: ' + windowId);
                    resolve([false]);
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
                                resolve([true]);
                            } catch (e) {
                                console.error('[CaptureHelper] screenshot_window_finish error: ' + e);
                                try { stream.close(null); } catch (ce) {}
                                resolve([false]);
                            }
                        });
                    } catch (we) {
                        console.error('[CaptureHelper] screenshot_window error: ' + we);
                        try { stream.close(null); } catch (ce) {}
                        resolve([false]);
                    }
                    return GLib.SOURCE_REMOVE;
                });
            } catch (err) {
                console.error('[CaptureHelper] CaptureWindow error: ' + err);
                resolve([false]);
            }
        });
    }

    ListWindows() {
        try {
            const list = [];
            if (global.get_window_actors) {
                for (const actor of global.get_window_actors()) {
                    const win = actor.meta_window;
                    if (!win || win.is_hidden() || win.is_override_redirect()) continue;
                    const rect = win.get_frame_rect();
                    if (rect.width <= 0 || rect.height <= 0) continue;

                    let appName = win.get_wm_class() || '';
                    let iconName = 'application-x-executable';
                    if (Shell.AppSystem) {
                        const app = Shell.AppSystem.get_default().get_window_app(win);
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
            return [JSON.stringify(list)];
        } catch (e) {
            console.error('[CaptureHelper] ListWindows error: ' + e);
            return ['[]'];
        }
    }

    SetHaloActive(active) {
        if (this._haloManager) {
            this._haloManager.setActive(active);
            return [true];
        }
        return [false];
    }
}
