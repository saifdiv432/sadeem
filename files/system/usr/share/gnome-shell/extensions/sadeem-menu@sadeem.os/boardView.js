// boardView.js - Scrollable Unified 2D Board, Compact Foldable Groups, and Search Results
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import { bindTooltip } from './bottomStrip.js';
import * as I18n from './i18n.js';
import * as TileLayout from './tileLayout.js';

function getAppGicon(appRecord) {
    try {
        const icon = appRecord?.appInfo?.get_icon?.();
        if (icon)
            return icon;
    } catch (_e) {}
    return Gio.Icon.new_for_string('application-x-executable');
}

export class BoardView extends St.BoxLayout {
    static {
        GObject.registerClass(this);
    }

    constructor() {
        super({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-menu-board-area',
            style: 'min-width: 0px; min-height: 0px;',
            x_expand: true,
            y_expand: true,
            reactive: true,
        });
        this.clip_to_allocation = true;
        this._boardScroll = null;
        this._searchScroll = null;
        this._searchResults = [];
        this._searchButtons = [];
        this._selectedSearchIndex = -1;
        this._callbacks = {};

        this.connect('button-press-event', (_a, ev) => {
            if (ev.get_button() === Clutter.BUTTON_SECONDARY && this._callbacks.onBackgroundContext) {
                const [sx, sy] = ev.get_coords();
                this._callbacks.onBackgroundContext(sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
    }

    renderHome(boardItems, opts) {
        this._callbacks = opts;
        this._searchResults = [];
        this._searchButtons = [];
        this._selectedSearchIndex = -1;
        this._searchScroll = null;
        this.destroy_all_children();

        const level = Number.isInteger(opts.iconSizeLevel) ? opts.iconSizeLevel : 2;
        const cell = TileLayout.getCellDimensions(level);
        const availW = Math.max(200, (opts.boardWidth || 876) - 6);
        const visibleCols = Math.max(
            TileLayout.MIN_BOARD_GRID_COLS,
            Math.floor((availW + TileLayout.CELL_GAP) / (cell.w + TileLayout.CELL_GAP))
        );

        const packed = TileLayout.computeUnifiedBoardRects(
            boardItems,
            cell.w,
            cell.h,
            TileLayout.CELL_GAP,
            visibleCols,
            Boolean(opts.isRtl)
        );

        const boardCanvas = new St.Widget({
            layout_manager: new Clutter.FixedLayout(),
            style: `width: ${packed.totalWidth}px; height: ${packed.totalHeight}px;`,
            x_expand: false,
            y_expand: false,
            reactive: true,
        });
        boardCanvas.set_size(packed.totalWidth, packed.totalHeight);
        boardCanvas.connect('button-press-event', (_a, ev) => {
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                const [sx, sy] = ev.get_coords();
                opts.onBackgroundContext?.(sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        for (const r of packed.rects) {
            const actor = r.item.type === 'group'
                ? this._createGroupCard(r.item, r, opts)
                : this._createLooseAppTile(r.item, cell.w, cell.h, opts);
            r.actor = actor;
            boardCanvas.add_child(actor);
            actor.set_position(r.x, r.y);
            actor.set_size(r.width, r.height);
        }

        opts.dragManager?.setBoardContext({
            boardView: this,
            boardCanvas,
            boardCols: packed.totalCols,
            totalWidth: packed.totalWidth,
            cellW: cell.w,
            cellH: cell.h,
            gap: TileLayout.CELL_GAP,
            itemRects: packed.rects,
            isRtl: Boolean(opts.isRtl),
        });

        const viewport = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-menu-board-viewport',
            x_expand: false,
            y_expand: false,
        });
        viewport.add_child(boardCanvas);

        const boardScroll = new St.ScrollView({
            style_class: 'sadeem-menu-board-scroll',
            style: 'min-width: 0px; min-height: 0px;',
            overlay_scrollbars: false,
            hscrollbar_policy: St.PolicyType.AUTOMATIC,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            enable_mouse_scrolling: true,
            x_expand: true,
            y_expand: true,
            child: viewport,
        });
        boardScroll.clip_to_allocation = true;
        boardScroll.connect('scroll-event', (_sv, ev) => {
            opts.onHideTooltip?.();
            return this._handleShiftHorizScroll(boardScroll, ev);
        });
        this._boardScroll = boardScroll;
        this.add_child(boardScroll);
    }

    _handleShiftHorizScroll(scrollView, ev) {
        if (!(ev.get_state?.() & Clutter.ModifierType.SHIFT_MASK))
            return Clutter.EVENT_PROPAGATE;
        const dir = ev.get_scroll_direction?.();
        let delta = 0;
        if (dir === Clutter.ScrollDirection.UP || dir === Clutter.ScrollDirection.LEFT)
            delta = -48;
        else if (dir === Clutter.ScrollDirection.DOWN || dir === Clutter.ScrollDirection.RIGHT)
            delta = 48;
        else if (dir === Clutter.ScrollDirection.SMOOTH) {
            const [sdx, sdy] = ev.get_scroll_delta?.() || [0, 0];
            delta = (Math.abs(sdy) >= Math.abs(sdx) ? sdy : sdx) * 48;
        }
        const hAdj = scrollView.hadjustment;
        if (delta !== 0 && hAdj && hAdj.upper > hAdj.page_size) {
            const maxV = Math.max(hAdj.lower, hAdj.upper - hAdj.page_size);
            hAdj.value = TileLayout.clampNumber(hAdj.value + delta, hAdj.lower, maxV);
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _createLooseAppTile(item, cellW, cellH, opts) {
        const rec = item.record;
        const iconSize = TileLayout.getLooseAppIconSize(cellW);

        const vbox = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-tile-inner-col',
            x_expand: true,
            y_expand: true,
            y_align: Clutter.ActorAlign.FILL,
            reactive: false,
        });
        const icon = new St.Icon({
            gicon: getAppGicon(rec),
            icon_size: iconSize,
            x_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        const lbl = new St.Label({
            text: rec.name,
            style_class: 'sadeem-tile-label',
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        lbl.clutter_text.single_line_mode = false;
        lbl.clutter_text.line_wrap = true;
        lbl.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        lbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        lbl.clutter_text.line_alignment = Pango.Alignment.CENTER;

        vbox.add_child(new St.Widget({ y_expand: true, reactive: false }));
        vbox.add_child(icon);
        vbox.add_child(new St.Widget({ y_expand: true, reactive: false }));
        vbox.add_child(lbl);

        const btn = new St.Button({
            style_class: 'sadeem-tile-btn',
            button_mask: St.ButtonMask.PRIMARY,
            style: `width: ${cellW}px; height: ${cellH}px;`,
            can_focus: true,
            reactive: true,
            track_hover: true,
            x_expand: false,
            y_expand: false,
            child: vbox,
        });
        btn.set_size(cellW, cellH);
        btn.accessible_name = rec.name;
        btn.connect('clicked', () => {
            if (opts.dragManager?.consumeSuppressedClick()) return;
            opts.onHideTooltip?.(btn);
            opts.onLaunchApp?.(rec, false);
        });
        btn.connect('button-press-event', (_b, ev) => {
            opts.onHideTooltip?.(btn);
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                const [sx, sy] = ev.get_coords();
                opts.onLooseAppContext?.(rec, sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        opts.dragManager?.attachDraggable(btn, 'board-app', {
            itemType: 'app',
            itemId: rec.id,
            name: rec.name,
            gicon: getAppGicon(rec),
            sourceGroupId: null,
        });
        if ((rec.name || '').length > 18)
            bindTooltip(btn, rec.name, opts.onShowTooltip, opts.onHideTooltip);
        return btn;
    }

    _createGroupCard(group, rect, opts) {
        const cardW = rect.width;
        const cardH = rect.height;
        const slots = TileLayout.computeCompactGroupSlots(group.apps, group.cardSize);
        const displayTitle = (group.name || '').trim() || I18n.t('folder_default_name');

        const card = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-group-card',
            style: `width: ${cardW}px; height: ${cardH}px;`,
            x_expand: false,
            y_expand: false,
            reactive: true,
            track_hover: true,
        });
        card.clip_to_allocation = true;
        card.set_size(cardW, cardH);

        const innerW = Math.max(80, cardW - 14);
        const innerH = Math.max(60, cardH - 14 - 22 - 2);
        const slotGap = 4;
        const slotW = Math.max(24, Math.floor((innerW - (slots.innerCols - 1) * slotGap) / slots.innerCols));
        const slotH = Math.max(24, Math.floor((innerH - (slots.innerRows - 1) * slotGap) / slots.innerRows));
        const iconPx = TileLayout.getCompactGroupIconSize(slotW, slotH);

        const groupDragPayload = {
            itemType: 'group',
            itemId: group.id,
            groupId: group.id,
            name: displayTitle,
            cardSize: group.cardSize,
            fadeActor: card,
            visualActor: card,
        };

        const gridBox = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-group-card-grid',
            x_expand: true,
            y_expand: true,
            reactive: false,
        });

        if (group.apps.length === 0) {
            const emptyLbl = new St.Label({
                text: I18n.t('hint_empty_group'),
                style_class: 'sadeem-empty-group-dropzone',
                x_expand: true,
                y_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
                reactive: false,
            });
            emptyLbl.clutter_text.line_wrap = true;
            emptyLbl.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
            const emptyCardBtn = new St.Button({
                style_class: 'sadeem-group-empty-slot-btn',
                button_mask: St.ButtonMask.PRIMARY,
                can_focus: false,
                reactive: true,
                track_hover: false,
                x_expand: true,
                y_expand: true,
                child: emptyLbl,
            });
            emptyCardBtn.connect('clicked', () => {
                if (opts.dragManager?.consumeSuppressedClick()) return;
                opts.onOpenGroupModal?.(group);
            });
            emptyCardBtn.connect('button-press-event', (_b, ev) => {
                opts.onHideTooltip?.();
                if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                    const [sx, sy] = ev.get_coords();
                    opts.onGroupCardContext?.(group, sx, sy);
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            });
            opts.dragManager?.attachDraggable(emptyCardBtn, 'board-group', groupDragPayload, card);
            gridBox.add_child(emptyCardBtn);
        } else {
            let slotIdx = 0;
            for (let r = 0; r < slots.innerRows; r++) {
                const rowBox = new St.BoxLayout({
                    orientation: Clutter.Orientation.HORIZONTAL,
                    style_class: 'sadeem-group-card-row',
                    x_expand: true,
                    y_expand: false,
                    reactive: false,
                });
                for (let c = 0; c < slots.innerCols; c++) {
                    if (slotIdx < slots.directApps.length) {
                        rowBox.add_child(this._createGroupSlotButton(group, slots.directApps[slotIdx].record, slotW, slotH, iconPx, opts, groupDragPayload, card));
                    } else if (slots.hasOverflowCluster && slotIdx === (slots.capacity - 1)) {
                        rowBox.add_child(this._createOverflowSlotButton(group, slots, slotW, slotH, opts, groupDragPayload, card));
                    } else {
                        const emptySlotBtn = new St.Button({
                            style_class: 'sadeem-group-empty-slot-btn',
                            button_mask: St.ButtonMask.PRIMARY,
                            style: `width: ${slotW}px; height: ${slotH}px;`,
                            can_focus: false,
                            reactive: true,
                            track_hover: false,
                            x_expand: false,
                            y_expand: false,
                        });
                        emptySlotBtn.set_size(slotW, slotH);
                        emptySlotBtn.connect('clicked', () => {
                            if (opts.dragManager?.consumeSuppressedClick()) return;
                            opts.onOpenGroupModal?.(group);
                        });
                        emptySlotBtn.connect('button-press-event', (_b, ev) => {
                            opts.onHideTooltip?.();
                            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                                const [sx, sy] = ev.get_coords();
                                opts.onGroupCardContext?.(group, sx, sy);
                                return Clutter.EVENT_STOP;
                            }
                            return Clutter.EVENT_PROPAGATE;
                        });
                        opts.dragManager?.attachDraggable(emptySlotBtn, 'board-group', groupDragPayload, card);
                        rowBox.add_child(emptySlotBtn);
                    }
                    slotIdx++;
                }
                gridBox.add_child(rowBox);
            }
        }

        const footer = new St.BoxLayout({
            orientation: Clutter.Orientation.HORIZONTAL,
            style_class: 'sadeem-group-card-footer',
            x_expand: true,
            y_expand: false,
            reactive: false,
        });

        const titleLbl = new St.Label({
            text: displayTitle,
            style_class: 'sadeem-group-card-title',
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        titleLbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        titleLbl.clutter_text.single_line_mode = true;

        const titleBtn = new St.Button({
            style_class: 'sadeem-group-title-btn',
            button_mask: St.ButtonMask.PRIMARY,
            can_focus: true,
            reactive: true,
            x_expand: true,
            child: titleLbl,
        });
        titleBtn.connect('clicked', () => {
            if (opts.dragManager?.consumeSuppressedClick()) return;
            opts.onOpenGroupModal?.(group);
        });
        titleBtn.connect('button-press-event', (_b, ev) => {
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                const [sx, sy] = ev.get_coords();
                opts.onGroupCardContext?.(group, sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        opts.dragManager?.attachDraggable(titleBtn, 'board-group', groupDragPayload, card);

        const moreIcon = new St.Icon({ icon_name: 'view-more-symbolic', icon_size: 13, reactive: false });
        const moreBtn = new St.Button({
            style_class: 'sadeem-group-action-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: moreIcon,
        });
        moreBtn.connect('clicked', () => {
            opts.onHideTooltip?.();
            let sx = 0;
            let sy = 0;
            try {
                const [bx, by] = moreBtn.get_transformed_position();
                const [bw, bh] = moreBtn.get_transformed_size();
                sx = Math.round(bx + bw / 2);
                sy = Math.round(by + bh / 2);
            } catch (_e) {}
            opts.onGroupCardContext?.(group, sx, sy);
        });
        moreBtn.connect('button-press-event', (_b, ev) => {
            opts.onHideTooltip?.();
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                const [sx, sy] = ev.get_coords();
                opts.onGroupCardContext?.(group, sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        footer.add_child(titleBtn);
        footer.add_child(moreBtn);
        card.add_child(gridBox);
        card.add_child(footer);

        card.connect('button-press-event', (_c, ev) => {
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                opts.onHideTooltip?.();
                const [sx, sy] = ev.get_coords();
                opts.onGroupCardContext?.(group, sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        return card;
    }

    _createGroupSlotButton(group, rec, slotW, slotH, iconPx, opts, groupDragPayload, card) {
        const icon = new St.Icon({
            gicon: getAppGicon(rec),
            icon_size: iconPx,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        const slotBtn = new St.Button({
            style_class: 'sadeem-group-slot-app',
            button_mask: St.ButtonMask.PRIMARY,
            style: `width: ${slotW}px; height: ${slotH}px;`,
            can_focus: true,
            reactive: true,
            track_hover: true,
            x_expand: false,
            y_expand: false,
            child: icon,
        });
        slotBtn.set_size(slotW, slotH);
        slotBtn.accessible_name = rec.name;
        slotBtn.connect('clicked', () => {
            if (opts.dragManager?.consumeSuppressedClick()) return;
            opts.onHideTooltip?.(slotBtn);
            opts.onLaunchApp?.(rec, false);
        });
        slotBtn.connect('button-press-event', (_b, ev) => {
            opts.onHideTooltip?.(slotBtn);
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                const [sx, sy] = ev.get_coords();
                opts.onGroupAppContext?.(group, rec, sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        if (groupDragPayload)
            opts.dragManager?.attachDraggable(slotBtn, 'board-group', groupDragPayload, card || null);
        bindTooltip(slotBtn, rec.name, opts.onShowTooltip, opts.onHideTooltip);
        return slotBtn;
    }

    _createOverflowSlotButton(group, slots, slotW, slotH, opts, groupDragPayload, card) {
        const miniPx = Math.max(11, Math.floor(Math.min(slotW, slotH) * 0.24));
        const mosaic = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'sadeem-group-overflow-mosaic',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            reactive: false,
        });
        for (let i = 0; i < slots.clusterApps.length; i += 2) {
            const mRow = new St.BoxLayout({
                orientation: Clutter.Orientation.HORIZONTAL,
                style_class: 'sadeem-group-overflow-mosaic-row',
                x_align: Clutter.ActorAlign.CENTER,
                reactive: false,
            });
            for (const entry of slots.clusterApps.slice(i, i + 2))
                mRow.add_child(new St.Icon({ gicon: getAppGicon(entry.record), icon_size: miniPx, reactive: false }));
            mosaic.add_child(mRow);
        }

        const inner = new St.Widget({ layout_manager: new Clutter.BinLayout(), x_expand: true, y_expand: true, reactive: false });
        inner.add_child(mosaic);
        inner.add_child(new St.Label({
            text: `+${slots.overflowCount}`,
            style_class: 'sadeem-group-overflow-badge',
            x_align: Clutter.ActorAlign.END,
            y_align: Clutter.ActorAlign.END,
            reactive: false,
        }));

        const btn = new St.Button({
            style_class: 'sadeem-group-overflow-slot',
            button_mask: St.ButtonMask.PRIMARY,
            style: `width: ${slotW}px; height: ${slotH}px;`,
            can_focus: true,
            reactive: true,
            track_hover: true,
            x_expand: false,
            y_expand: false,
            child: inner,
        });
        btn.set_size(slotW, slotH);
        btn.accessible_name = I18n.t('ctx_open_group');
        btn.connect('clicked', () => {
            if (opts.dragManager?.consumeSuppressedClick()) return;
            opts.onHideTooltip?.(btn);
            opts.onOpenGroupModal?.(group);
        });
        btn.connect('button-press-event', (_b, ev) => {
            opts.onHideTooltip?.(btn);
            if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                const [sx, sy] = ev.get_coords();
                opts.onGroupCardContext?.(group, sx, sy);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        if (groupDragPayload)
            opts.dragManager?.attachDraggable(btn, 'board-group', groupDragPayload, card || null);
        bindTooltip(btn, I18n.t('ctx_open_group'), opts.onShowTooltip, opts.onHideTooltip);
        return btn;
    }

    renderSearch(appResults, fileResults, filesPending, opts) {
        opts.dragManager?.clearBoardContext();
        this._callbacks = opts;
        this._boardScroll = null;
        this._searchScroll = null;
        this._searchResults = [];
        this._searchButtons = [];
        this._selectedSearchIndex = -1;
        this.destroy_all_children();

        const content = new St.BoxLayout({ orientation: Clutter.Orientation.VERTICAL, style_class: 'sadeem-menu-search-results', x_expand: true });

        if (appResults.length > 0) {
            content.add_child(new St.Label({ text: I18n.t('section_apps'), style_class: 'sadeem-menu-search-section-label', reactive: false }));
            for (const rec of appResults) {
                const btn = this._createSearchRow(getAppGicon(rec), rec.name, rec.description, () => opts.onLaunchApp?.(rec, false), (sx, sy) => opts.onAppContext?.(rec, sx, sy));
                this._searchResults.push({ type: 'app', record: rec });
                this._searchButtons.push(btn);
                content.add_child(btn);
            }
        }

        if (fileResults.length > 0 || filesPending) {
            content.add_child(new St.Label({ text: I18n.t('section_files'), style_class: 'sadeem-menu-search-section-label', reactive: false }));
            if (filesPending && fileResults.length === 0)
                content.add_child(new St.Label({ text: I18n.t('searching'), style_class: 'sadeem-menu-search-desc', style: 'padding: 6px 10px;', reactive: false }));
            for (const fileRes of fileResults) {
                const btn = this._createSearchRow(fileRes.gicon, fileRes.name, fileRes.description, () => opts.onActivateFile?.(fileRes), null);
                this._searchResults.push({ type: 'file', fileResult: fileRes });
                this._searchButtons.push(btn);
                content.add_child(btn);
            }
        }

        if (appResults.length === 0 && fileResults.length === 0 && !filesPending)
            content.add_child(new St.Label({ text: I18n.t('no_results'), style_class: 'sadeem-menu-empty-status', x_expand: true, x_align: Clutter.ActorAlign.CENTER, reactive: false }));

        this._searchScroll = new St.ScrollView({
            style_class: 'sadeem-menu-search-scroll',
            overlay_scrollbars: true,
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            enable_mouse_scrolling: true,
            x_expand: true,
            y_expand: true,
            child: content,
        });
        this._searchScroll.clip_to_allocation = true;
        this.add_child(this._searchScroll);

        if (this._searchButtons.length > 0)
            this.setSearchIndex(0);
    }

    _createSearchRow(gicon, title, subtitle, onActivate, onRightClick) {
        const rowBox = new St.BoxLayout({ orientation: Clutter.Orientation.HORIZONTAL, x_expand: true, style: 'spacing: 10px;', reactive: false });
        rowBox.add_child(new St.Icon({ gicon, icon_size: 32, y_align: Clutter.ActorAlign.CENTER, reactive: false }));
        const textCol = new St.BoxLayout({ orientation: Clutter.Orientation.VERTICAL, x_expand: true, y_align: Clutter.ActorAlign.CENTER, reactive: false });
        const titleLbl = new St.Label({ text: title, style_class: 'sadeem-menu-sidebar-label', reactive: false });
        titleLbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        textCol.add_child(titleLbl);
        if (subtitle) {
            const subLbl = new St.Label({ text: subtitle, style_class: 'sadeem-menu-search-desc', reactive: false });
            subLbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            textCol.add_child(subLbl);
        }
        rowBox.add_child(textCol);

        const btn = new St.Button({ style_class: 'sadeem-menu-search-row-item', button_mask: St.ButtonMask.PRIMARY, can_focus: true, reactive: true, x_expand: true, child: rowBox });
        btn.connect('clicked', () => onActivate?.());
        if (onRightClick) {
            btn.connect('button-press-event', (_b, ev) => {
                if (ev.get_button() === Clutter.BUTTON_SECONDARY) {
                    const [sx, sy] = ev.get_coords();
                    onRightClick(sx, sy);
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            });
        }
        return btn;
    }

    setSearchIndex(idx) {
        if (this._selectedSearchIndex >= 0 && this._searchButtons[this._selectedSearchIndex])
            this._searchButtons[this._selectedSearchIndex].remove_style_class_name('sadeem-menu-result-selected');
        this._selectedSearchIndex = idx;
        const activeBtn = idx >= 0 ? this._searchButtons[idx] : null;
        if (activeBtn) {
            activeBtn.add_style_class_name('sadeem-menu-result-selected');
            try {
                const adj = this._searchScroll?.vadjustment;
                const box = activeBtn.get_allocation_box?.();
                if (adj && box) {
                    if (box.y1 < adj.value)
                        adj.value = box.y1;
                    else if (box.y2 > adj.value + adj.page_size)
                        adj.value = Math.max(0, box.y2 - adj.page_size);
                }
            } catch (_e) {}
        }
    }

    moveSearchSelection(delta) {
        if (this._searchButtons.length === 0)
            return false;
        const len = this._searchButtons.length;
        const next = this._selectedSearchIndex < 0 ? 0 : (this._selectedSearchIndex + delta + len) % len;
        this.setSearchIndex(next);
        return true;
    }

    getSelectedSearchItem() {
        const idx = this._selectedSearchIndex >= 0 ? this._selectedSearchIndex : 0;
        return this._searchResults[idx] || null;
    }
}
