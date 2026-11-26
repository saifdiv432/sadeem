// dragManager.js - Safe 2D Drag & Drop for GNOME 51.1 (never blocks St.Button Clutter.ClickGesture)
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as TileLayout from './tileLayout.js';

const DRAG_THRESHOLD_PX = 8;

function fallbackGicon() {
    return Gio.Icon.new_for_string('application-x-executable');
}

export function applyBoardDrop(appData, records, drag, res) {
    if (!appData || !drag || !res)
        return;
    if (drag.kind === 'board-group') {
        if (res.action === 'place-board-item')
            appData.placeBoardItem({ itemType: 'group', itemId: drag.payload.groupId, targetCol: res.targetCol, targetRow: res.targetRow }, records);
        return;
    }
    const srcGroup = drag.payload.sourceGroupId || null;
    if (res.action === 'place-board-item') {
        if (srcGroup)
            appData.extractAppToBoard(srcGroup, drag.payload.itemId, res.targetCol, res.targetRow, records);
        else
            appData.placeBoardItem({ itemType: 'app', itemId: drag.payload.itemId, targetCol: res.targetCol, targetRow: res.targetRow }, records);
    } else if (res.action === 'merge-apps-into-group') {
        appData.mergeAppsIntoGroup({
            targetAppId: res.targetAppId,
            sourceAppId: drag.payload.itemId,
            sourceGroupId: srcGroup,
            targetCol: res.targetCol,
            targetRow: res.targetRow,
        }, records);
    } else if (res.action === 'add-to-group') {
        appData.addAppToGroup({
            targetGroupId: res.targetGroupId,
            appId: drag.payload.itemId,
            sourceGroupId: srcGroup,
            removeLoose: !srcGroup && drag.kind === 'board-app',
        }, records);
    }
}

export class DragManager {
    constructor({ menuActor, rootStack, overlayLayer, isResizing, onBeforeStart, onDrop }) {
        this._menuActor = menuActor;
        this._rootStack = rootStack;
        this._overlayLayer = overlayLayer;
        this._isResizing = isResizing || (() => false);
        this._onBeforeStart = onBeforeStart || null;
        this._onDrop = onDrop || null;

        this._boardCtx = null;
        this._pending = null;
        this._captureSigId = null;
        this._fadeActor = null;
        this._ghost = null;
        this._ghostW = 72;
        this._ghostH = 82;
        this._previewActor = null;
        this._highlightActor = null;
        this._highlightClass = '';
        this._lastDropKey = '';
        this._suppressNextClick = false;
        this._suppressIdleId = null;
    }

    get isDragging() {
        return Boolean(this._pending?.started);
    }

    setBoardContext(ctx) {
        this._boardCtx = ctx || null;
    }

    clearBoardContext() {
        this._clearDropVisuals();
        this._boardCtx = null;
    }

    consumeSuppressedClick() {
        if (!this._suppressNextClick)
            return false;
        this._suppressNextClick = false;
        return true;
    }

    attachDraggable(actor, kind, payload, visualActor = null) {
        if (!actor)
            return;
        actor.connect('button-press-event', (_a, ev) => {
            if (ev.get_button() !== Clutter.BUTTON_PRIMARY || this._isResizing() || this._pending)
                return Clutter.EVENT_PROPAGATE;
            const [startX, startY] = ev.get_coords();
            this._beginPending({ actor, kind, payload, visualActor, startX, startY, started: false });
            return Clutter.EVENT_PROPAGATE;
        });
    }

    _beginPending(entry) {
        this._disconnectCapture();
        this._pending = entry;
        this._captureSigId = this._menuActor.connect('captured-event', (_m, ev) => this._onCapturedEvent(ev));
    }

    _disconnectCapture() {
        if (this._captureSigId && this._menuActor) {
            try {
                this._menuActor.disconnect(this._captureSigId);
            } catch (_e) {}
        }
        this._captureSigId = null;
    }

    _clearSuppressIdle() {
        if (this._suppressIdleId) {
            GLib.source_remove(this._suppressIdleId);
            this._suppressIdleId = null;
        }
    }

    _onCapturedEvent(ev) {
        if (!this._pending) {
            this._disconnectCapture();
            return Clutter.EVENT_PROPAGATE;
        }

        const type = ev.type();
        if (type === Clutter.EventType.SCROLL)
            return Clutter.EVENT_PROPAGATE;

        if (type === Clutter.EventType.KEY_PRESS && ev.get_key_symbol() === Clutter.KEY_Escape) {
            this.cancel();
            return Clutter.EVENT_STOP;
        }

        if (type === Clutter.EventType.MOTION) {
            const [sx, sy] = ev.get_coords();
            if (!this._pending.started) {
                const dist = Math.hypot(sx - this._pending.startX, sy - this._pending.startY);
                if (dist < DRAG_THRESHOLD_PX)
                    return Clutter.EVENT_PROPAGATE;
                this._startDragVisuals(sx, sy);
            } else {
                this._positionGhost(sx, sy);
            }
            this._updateDropTarget(sx, sy);
            return Clutter.EVENT_STOP;
        }

        if (type === Clutter.EventType.BUTTON_RELEASE) {
            if (!this._pending.started) {
                this._disconnectCapture();
                this._pending = null;
                return Clutter.EVENT_PROPAGATE;
            }
            const [sx, sy] = ev.get_coords();
            const resolution = this._computeDropResolution(sx, sy);
            const dragSnapshot = { kind: this._pending.kind, payload: this._pending.payload };
            this._cleanupDragVisuals();
            this._disconnectCapture();
            this._pending = null;
            this._scheduleResetSuppressClick();
            this._onDrop?.(dragSnapshot, resolution);
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    _scheduleResetSuppressClick() {
        this._clearSuppressIdle();
        this._suppressIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._suppressIdleId = null;
            this._suppressNextClick = false;
            return GLib.SOURCE_REMOVE;
        });
    }

    _startDragVisuals(stageX, stageY) {
        const p = this._pending;
        p.started = true;
        this._lastDropKey = '';
        this._suppressNextClick = true;
        this._onBeforeStart?.(p);
        this._boardCtx?.boardView?.beginDragSession?.();

        const fadeActor = p.visualActor || p.payload?.visualActor || p.payload?.fadeActor || p.actor;
        if (fadeActor) {
            this._fadeActor = fadeActor;
            try {
                fadeActor.opacity = 85;
            } catch (_e) {}
        }

        const isGroup = p.kind === 'board-group';
        const ghost = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-drag-ghost',
            reactive: false,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });

        const icon = isGroup
            ? new St.Icon({
                icon_name: 'view-grid-symbolic',
                icon_size: 28,
                x_align: Clutter.ActorAlign.CENTER,
                reactive: false,
            })
            : new St.Icon({
                gicon: p.payload?.gicon || fallbackGicon(),
                icon_size: 34,
                x_align: Clutter.ActorAlign.CENTER,
                reactive: false,
            });
        const lbl = new St.Label({
            text: p.payload?.name || '',
            style: 'font-size: 8.5pt; font-weight: 600;',
            x_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        lbl.clutter_text.single_line_mode = true;
        lbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        ghost.add_child(icon);
        ghost.add_child(lbl);

        const gw = isGroup ? 108 : 76;
        const gh = isGroup ? 66 : 78;
        this._ghostW = gw;
        this._ghostH = gh;
        ghost.set_size(gw, gh);
        this._ghost = ghost;
        this._overlayLayer.add_child(ghost);
        this._positionGhost(stageX, stageY);
    }

    _positionGhost(stageX, stageY) {
        if (!this._ghost || !this._rootStack)
            return;
        try {
            const [ok, lx, ly] = this._rootStack.transform_stage_point(stageX, stageY);
            let px = lx;
            let py = ly;
            if (!ok) {
                const [rx, ry] = this._rootStack.get_transformed_position();
                px = stageX - rx;
                py = stageY - ry;
            }
            this._ghost.set_position(Math.round(px - this._ghostW / 2), Math.round(py - this._ghostH / 2));
        } catch (_e) {}
    }

    _computeDropResolution(stageX, stageY) {
        const ctx = this._boardCtx;
        if (!ctx || !ctx.boardView || !ctx.boardCanvas || !this._pending)
            return null;
        try {
            const boundsActor = ctx.boardScroll || ctx.boardView;
            const [vx, vy] = boundsActor.get_transformed_position();
            const [vw, vh] = boundsActor.get_transformed_size();
            if (stageX < vx || stageX > (vx + vw) || stageY < vy || stageY > (vy + vh))
                return null;

            const [ok, lx, ly] = ctx.boardCanvas.transform_stage_point(stageX, stageY);
            if (!ok)
                return null;

            const hitKind = this._pending.kind === 'board-group' ? 'board-group' : 'board-app';
            return TileLayout.hitTestUnifiedBoard({
                localX: lx,
                localY: ly,
                boardCols: ctx.boardCols,
                totalWidth: ctx.totalWidth,
                cellW: ctx.cellW,
                cellH: ctx.cellH,
                gap: ctx.gap,
                itemRects: ctx.itemRects,
                dragKind: hitKind,
                dragPayload: this._pending.payload,
                isRtl: ctx.isRtl,
            });
        } catch (_e) {
            return null;
        }
    }

    _makeDropKey(res) {
        if (!res)
            return '';
        return [
            res.action || '',
            res.targetCol ?? '',
            res.targetRow ?? '',
            res.targetGroupId || '',
            res.targetAppId || '',
        ].join(':');
    }

    _updateDropTarget(stageX, stageY) {
        const res = this._computeDropResolution(stageX, stageY);
        const nextKey = this._makeDropKey(res);
        if (nextKey === this._lastDropKey)
            return;

        this._clearDropVisuals(false);
        this._lastDropKey = nextKey;
        if (!res || !this._boardCtx?.boardCanvas)
            return;

        if (res.previewRect) {
            this._boardCtx.boardView?.setDragPreviewExtent?.(res.previewRect, this._boardCtx.cellH, this._boardCtx.gap);
            const pr = new St.Widget({
                style_class: 'sadeem-drop-preview-slot',
                reactive: false,
            });
            pr.set_position(Math.round(res.previewRect.x), Math.round(res.previewRect.y));
            pr.set_size(Math.round(res.previewRect.width), Math.round(res.previewRect.height));
            this._previewActor = pr;
            this._boardCtx.boardCanvas.add_child(pr);
            try {
                this._boardCtx.boardCanvas.set_child_below_sibling(pr, null);
            } catch (_e) {}
        } else if (res.actor && res.highlightClass) {
            this._highlightActor = res.actor;
            this._highlightClass = res.highlightClass;
            try {
                res.actor.add_style_class_name(res.highlightClass);
            } catch (_e) {}
        }
    }

    _clearDropVisuals(endSession = true) {
        if (endSession) {
            this._lastDropKey = '';
            this._boardCtx?.boardView?.endDragSession?.();
        }
        if (this._previewActor) {
            try {
                this._previewActor.destroy();
            } catch (_e) {}
            this._previewActor = null;
        }
        if (this._highlightActor && this._highlightClass) {
            try {
                this._highlightActor.remove_style_class_name(this._highlightClass);
            } catch (_e) {}
        }
        this._highlightActor = null;
        this._highlightClass = '';
    }

    _cleanupDragVisuals() {
        this._clearDropVisuals();
        if (this._ghost) {
            try {
                this._ghost.destroy();
            } catch (_e) {}
            this._ghost = null;
        }
        if (this._fadeActor) {
            try {
                this._fadeActor.opacity = 255;
            } catch (_e) {}
            this._fadeActor = null;
        }
    }

    cancel() {
        this._disconnectCapture();
        this._cleanupDragVisuals();
        if (this._pending?.started)
            this._scheduleResetSuppressClick();
        this._pending = null;
    }

    destroy() {
        this.cancel();
        this._clearSuppressIdle();
        this._suppressNextClick = false;
        this._boardCtx = null;
        this._menuActor = null;
        this._rootStack = null;
        this._overlayLayer = null;
        this._onBeforeStart = null;
        this._onDrop = null;
    }
}
