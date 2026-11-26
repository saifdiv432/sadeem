// resizeManager.js - Smooth 60fps Edge Resize Overlay (handle-only cursor & set_size during MOTION)
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as TileLayout from './tileLayout.js';

export function computeResizeHandleBounds(width, height, isRtl, edgePx = 6, cornerPx = 14) {
    const w = Math.max(0, Math.round(Number(width) || 0));
    const h = Math.max(0, Math.round(Number(height) || 0));
    const rtl = Boolean(isRtl);
    return {
        top: {
            x: rtl ? cornerPx : 0,
            y: 0,
            width: Math.max(1, w - cornerPx),
            height: edgePx,
        },
        side: {
            x: rtl ? 0 : Math.max(0, w - edgePx),
            y: cornerPx,
            width: edgePx,
            height: Math.max(1, h - cornerPx),
        },
        corner: {
            x: rtl ? 0 : Math.max(0, w - cornerPx),
            y: 0,
            width: cornerPx,
            height: cornerPx,
        },
    };
}

export class ResizeOverlay extends St.Widget {
    static {
        GObject.registerClass(this);
    }

    constructor({ menuActor, rootStack, rootContainer, settings, getWorkArea, isRtl, isBlocked, onBeforeStart, onResizeCommitted }) {
        super({
            layout_manager: new Clutter.FixedLayout(),
            text_direction: Clutter.TextDirection.LTR,
            reactive: false,
            x_expand: true,
            y_expand: true,
        });

        this._menuActor = menuActor;
        this._rootStack = rootStack;
        this._rootContainer = rootContainer;
        this._settings = settings;
        this._getWorkArea = getWorkArea;
        this._isRtl = Boolean(isRtl);
        this._isBlocked = isBlocked || (() => false);
        this._onBeforeStart = onBeforeStart || null;
        this._onResizeCommitted = onResizeCommitted || null;

        this._session = null;
        this._captureSigId = null;

        const sideCursor = this._isRtl ? Clutter.CursorType.W_RESIZE : Clutter.CursorType.E_RESIZE;
        const cornerCursor = this._isRtl ? Clutter.CursorType.NW_RESIZE : Clutter.CursorType.NE_RESIZE;

        this._topHandle = new St.Widget({
            style_class: 'sadeem-resize-handle-top',
            reactive: true,
            track_hover: true,
        });
        this._topHandle.set_cursor_type(Clutter.CursorType.N_RESIZE);

        this._sideHandle = new St.Widget({
            style_class: 'sadeem-resize-handle-side',
            reactive: true,
            track_hover: true,
        });
        this._sideHandle.set_cursor_type(sideCursor);

        this._cornerHandle = new St.Widget({
            style_class: 'sadeem-resize-handle-corner',
            reactive: true,
            track_hover: true,
        });
        this._cornerHandle.set_cursor_type(cornerCursor);

        this.add_child(this._topHandle);
        this.add_child(this._sideHandle);
        this.add_child(this._cornerHandle);
        this.set_child_above_sibling(this._cornerHandle, null);

        this.syncBounds(
            this._settings?.get_int?.('menu-width') || TileLayout.DEFAULT_MENU_WIDTH,
            this._settings?.get_int?.('menu-height') || TileLayout.DEFAULT_MENU_HEIGHT,
        );

        this._bindHandle(this._topHandle, 'top');
        this._bindHandle(this._sideHandle, 'side');
        this._bindHandle(this._cornerHandle, 'corner');
    }

    get isResizing() {
        return Boolean(this._session);
    }

    syncBounds(width, height) {
        const w = Math.max(1, Math.round(Number(width) || 0));
        const h = Math.max(1, Math.round(Number(height) || 0));
        const bounds = computeResizeHandleBounds(w, h, this._isRtl);
        this.set_size(w, h);
        this._topHandle.set_position(bounds.top.x, bounds.top.y);
        this._topHandle.set_size(bounds.top.width, bounds.top.height);
        this._sideHandle.set_position(bounds.side.x, bounds.side.y);
        this._sideHandle.set_size(bounds.side.width, bounds.side.height);
        this._cornerHandle.set_position(bounds.corner.x, bounds.corner.y);
        this._cornerHandle.set_size(bounds.corner.width, bounds.corner.height);
    }

    _bindHandle(handle, edge) {
        handle.connect('button-press-event', (_h, ev) => {
            if (ev.get_button() !== Clutter.BUTTON_PRIMARY || this._isBlocked() || this._session)
                return Clutter.EVENT_PROPAGATE;
            this._onBeforeStart?.();
            const [startX, startY] = ev.get_coords();
            const [w, h] = this._rootStack.get_transformed_size();
            const startW = Math.round(w || this._settings.get_int('menu-width'));
            const startH = Math.round(h || this._settings.get_int('menu-height'));
            const workArea = this._getWorkArea?.() || { width: 1920, height: 1040 };
            this._session = {
                edge,
                startX,
                startY,
                startW,
                startH,
                activeW: startW,
                activeH: startH,
                workArea,
            };
            this._disconnectCapture();
            this._captureSigId = this._menuActor.connect('captured-event', (_m, e) => this._onCapturedEvent(e));
            return Clutter.EVENT_STOP;
        });
    }

    _disconnectCapture() {
        if (this._captureSigId && this._menuActor) {
            try {
                this._menuActor.disconnect(this._captureSigId);
            } catch (_e) {}
        }
        this._captureSigId = null;
    }

    _onResizeMotion(ev) {
        const s = this._session;
        if (!s)
            return Clutter.EVENT_PROPAGATE;
        const [sx, sy] = ev.get_coords();
        const dx = sx - s.startX;
        const dy = sy - s.startY;
        const minW = TileLayout.MIN_MENU_WIDTH;
        const minH = TileLayout.MIN_MENU_HEIGHT;
        const maxW = Math.min(TileLayout.MAX_MENU_WIDTH, Math.max(minW, s.workArea.width - 20));
        const maxH = Math.min(TileLayout.MAX_MENU_HEIGHT, Math.max(minH, s.workArea.height - 20));

        if (s.edge === 'side' || s.edge === 'corner') {
            const signedDx = this._isRtl ? -dx : dx;
            s.activeW = Math.round(TileLayout.clampNumber(s.startW + signedDx, minW, maxW));
        }
        if (s.edge === 'top' || s.edge === 'corner')
            s.activeH = Math.round(TileLayout.clampNumber(s.startH - dy, minH, maxH));

        const activeW = s.activeW;
        const activeH = s.activeH;
        this._rootStack.set_size(activeW, activeH);
        this._rootContainer.set_size(activeW, activeH);
        this.syncBounds(activeW, activeH);
        return Clutter.EVENT_STOP;
    }

    _onCapturedEvent(ev) {
        const s = this._session;
        if (!s) {
            this._disconnectCapture();
            return Clutter.EVENT_PROPAGATE;
        }

        const type = ev.type();
        if (type === Clutter.EventType.KEY_PRESS && ev.get_key_symbol() === Clutter.KEY_Escape) {
            this._rootStack.set_size(s.startW, s.startH);
            this._rootContainer.set_size(s.startW, s.startH);
            this.syncBounds(s.startW, s.startH);
            this.cancel();
            return Clutter.EVENT_STOP;
        }

        if (type === Clutter.EventType.MOTION)
            return this._onResizeMotion(ev);

        if (type === Clutter.EventType.BUTTON_RELEASE) {
            const finalW = s.activeW;
            const finalH = s.activeH;
            this._disconnectCapture();
            this._session = null;
            this.syncBounds(finalW, finalH);
            this._settings.set_int('menu-width', finalW);
            this._settings.set_int('menu-height', finalH);
            this._onResizeCommitted?.(finalW, finalH);
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    cancel() {
        this._disconnectCapture();
        this._session = null;
    }

    destroy() {
        this.cancel();
        this._menuActor = null;
        this._rootStack = null;
        this._rootContainer = null;
        this._settings = null;
        this._getWorkArea = null;
        this._onBeforeStart = null;
        this._onResizeCommitted = null;
        super.destroy();
    }
}
