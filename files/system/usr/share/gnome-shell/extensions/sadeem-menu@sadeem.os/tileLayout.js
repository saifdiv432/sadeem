// Pure GNOME-independent Windows 10 Vertical Columns & Free 2D Tile Board geometry math.
// Kept free of resource:/// imports so GJS unit tests can import directly.

export const TILE_GAP = 6;
export const GROUP_GRID_COLS = 6;
export const GROUP_HORIZ_GAP = 32;
export const GROUP_VERT_GAP = 24;
export const SIDEBAR_WIDTH = 220;
export const SIDEBAR_GAP = 16;
export const ROOT_PADDING_X = 28; // 14px left + 14px right on .sadeem-menu-root
export const BOARD_PADDING_X = 4; // compact padding on .sadeem-menu-board-scroll
export const GROUP_CARD_PAD_X = 24; // 12px left + 12px right padding on group cards
export const GROUP_HEADER_HEIGHT = 28;
export const GROUP_HEADER_MARGIN_BOTTOM = 6;
export const MIN_MENU_WIDTH = 440;
export const MAX_MENU_WIDTH = 1800;
export const MIN_MENU_HEIGHT = 380;
export const MAX_MENU_HEIGHT = 1020;
export const MIN_TILE_COLUMNS = 1;
export const MAX_TILE_COLUMNS = 4;

// Unit pixel presets (0..4); default level 2 -> u=46px, COL_WIDTH=306px
export const UNIT_SIZES = Object.freeze([38, 42, 46, 50, 56]);

// Unified 2D Free Board cell presets (0..4); default level 2 -> 72x82px (compact 2x2 group = 154x174px)
export const CELL_SIZES = Object.freeze([
    Object.freeze({ w: 58, h: 68 }),
    Object.freeze({ w: 64, h: 74 }),
    Object.freeze({ w: 72, h: 82 }),
    Object.freeze({ w: 80, h: 90 }),
    Object.freeze({ w: 90, h: 100 }),
]);
export const CELL_GAP = 10;
export const MIN_BOARD_GRID_COLS = 10;

export const GROUP_CARD_SIZES = Object.freeze({
    '2x2': Object.freeze({ key: '2x2', spanW: 2, spanH: 2, innerCols: 2, innerRows: 2, capacity: 4 }),
    '3x2': Object.freeze({ key: '3x2', spanW: 3, spanH: 2, innerCols: 3, innerRows: 2, capacity: 6 }),
    '3x3': Object.freeze({ key: '3x3', spanW: 3, spanH: 3, innerCols: 3, innerRows: 3, capacity: 9 }),
    '4x3': Object.freeze({ key: '4x3', spanW: 4, spanH: 3, innerCols: 4, innerRows: 3, capacity: 12 }),
});

export const TILE_SPANS = Object.freeze({
    small: Object.freeze({ w: 1, h: 1 }),
    medium: Object.freeze({ w: 2, h: 2 }),
    wide: Object.freeze({ w: 4, h: 2 }),
    large: Object.freeze({ w: 4, h: 4 }),
});

export function clampNumber(value, min, max) {
    const num = Number(value);
    if (!Number.isFinite(num))
        return min;
    return Math.min(max, Math.max(min, num));
}

export function normalizeTileSize(size) {
    if (size === 'small' || size === 'medium' || size === 'wide' || size === 'large')
        return size;
    return 'medium';
}

export function getUnitSizePixels(level = 2) {
    const idx = Math.round(clampNumber(level, 0, UNIT_SIZES.length - 1));
    return UNIT_SIZES[idx];
}

export function getTilePixelDimensions(size, unitPx = 46, gap = TILE_GAP) {
    const norm = normalizeTileSize(size);
    const span = TILE_SPANS[norm];
    const width = span.w * unitPx + Math.max(0, span.w - 1) * gap;
    const height = span.h * unitPx + Math.max(0, span.h - 1) * gap;
    return {
        size: norm,
        spanW: span.w,
        spanH: span.h,
        width,
        height,
    };
}

export function getGroupColumnWidth(unitPx = 46, cols = GROUP_GRID_COLS, gap = TILE_GAP) {
    return cols * unitPx + Math.max(0, cols - 1) * gap;
}

export function getTileIconSize(size, unitPx = 46) {
    const norm = normalizeTileSize(size);
    if (norm === 'small')
        return Math.max(18, Math.round(unitPx * 0.52)); // 24px at u=46
    if (norm === 'wide')
        return Math.max(28, Math.round(unitPx * 0.913)); // 42px at u=46
    if (norm === 'large')
        return Math.max(40, Math.round(unitPx * 1.217)); // 56px at u=46
    return Math.max(26, Math.round(unitPx * 0.826)); // 38px at u=46
}

export function getMenuWidthForColumns(
    cols,
    showAllAppsSidebar = true,
    unitPx = 46,
    horizGap = GROUP_HORIZ_GAP,
    sidebarWidth = SIDEBAR_WIDTH,
    boardPaddingX = BOARD_PADDING_X
) {
    const c = Math.round(clampNumber(cols, MIN_TILE_COLUMNS, MAX_TILE_COLUMNS));
    const colWidth = getGroupColumnWidth(unitPx);
    const boardContentWidth = c * colWidth + Math.max(0, c - 1) * horizGap;
    const boardWidth = boardContentWidth + boardPaddingX;
    const sidebarTotal = showAllAppsSidebar ? (sidebarWidth + SIDEBAR_GAP) : 0;
    const totalWidth = ROOT_PADDING_X + sidebarTotal + boardWidth;
    return {
        cols: c,
        colWidth,
        boardContentWidth,
        boardWidth,
        sidebarTotal,
        rootPaddingX: ROOT_PADDING_X,
        menuWidth: totalWidth,
        totalWidth,
    };
}

export function getMaxFittingColumns(
    workAreaWidth = 1920,
    showAllAppsSidebar = true,
    unitPx = 46,
    horizGap = GROUP_HORIZ_GAP,
    sidebarWidth = SIDEBAR_WIDTH,
    boardPaddingX = BOARD_PADDING_X
) {
    const safeWorkW = Math.max(360, Number(workAreaWidth) || 1920);
    const maxMenuW = safeWorkW - 16;

    let maxCols = MIN_TILE_COLUMNS;
    for (let c = MIN_TILE_COLUMNS; c <= MAX_TILE_COLUMNS; c++) {
        const dims = getMenuWidthForColumns(
            c,
            showAllAppsSidebar,
            unitPx,
            horizGap,
            sidebarWidth,
            boardPaddingX
        );
        if (dims.totalWidth <= maxMenuW)
            maxCols = c;
    }
    return maxCols;
}

export function computeColsFromWidth(
    targetWidth,
    {
        workAreaWidth = 1920,
        showAllAppsSidebar = true,
        unitPx = 46,
        horizGap = GROUP_HORIZ_GAP,
        sidebarWidth = SIDEBAR_WIDTH,
        boardPaddingX = BOARD_PADDING_X,
    } = {}
) {
    const maxCols = getMaxFittingColumns(
        workAreaWidth,
        showAllAppsSidebar,
        unitPx,
        horizGap,
        sidebarWidth,
        boardPaddingX
    );
    const w = Number(targetWidth) || 0;
    let bestCols = MIN_TILE_COLUMNS;
    let bestDist = Infinity;
    for (let c = MIN_TILE_COLUMNS; c <= maxCols; c++) {
        const dims = getMenuWidthForColumns(
            c,
            showAllAppsSidebar,
            unitPx,
            horizGap,
            sidebarWidth,
            boardPaddingX
        );
        const dist = Math.abs(w - dims.totalWidth);
        if (dist < bestDist) {
            bestDist = dist;
            bestCols = c;
        }
    }
    return bestCols;
}

export function computeMenuGeometry({
    workAreaWidth = 1920,
    workAreaHeight = 1040,
    tileColumns = 3,
    showAllAppsSidebar = true,
    desiredWidth = null,
    desiredHeight = 660,
    unitPx = 46,
} = {}) {
    const safeWorkW = Math.max(360, Number(workAreaWidth) || 1920);
    const safeWorkH = Math.max(360, Number(workAreaHeight) || 1040);
    const maxFittingCols = getMaxFittingColumns(safeWorkW, showAllAppsSidebar, unitPx);
    const requestedCols = Math.round(
        clampNumber(tileColumns, MIN_TILE_COLUMNS, MAX_TILE_COLUMNS)
    );
    const effectiveCols = Math.max(MIN_TILE_COLUMNS, Math.min(requestedCols, maxFittingCols));

    const widthDims = getMenuWidthForColumns(
        effectiveCols,
        showAllAppsSidebar,
        unitPx
    );

    const maxAllowedW = Math.max(360, Math.min(MAX_MENU_WIDTH, safeWorkW - 16));
    const minAllowedW = Math.min(MIN_MENU_WIDTH, maxAllowedW);
    const hasExplicitWidth = desiredWidth !== undefined && desiredWidth !== null && Number(desiredWidth) > 0;
    const totalWidth = hasExplicitWidth
        ? Math.round(clampNumber(desiredWidth, minAllowedW, maxAllowedW))
        : Math.min(maxAllowedW, widthDims.totalWidth);

    const sidebarWidth = showAllAppsSidebar ? SIDEBAR_WIDTH : 0;
    const sidebarGap = showAllAppsSidebar ? SIDEBAR_GAP : 0;
    const visibleBoardWidth = Math.max(200, totalWidth - ROOT_PADDING_X - (showAllAppsSidebar ? (SIDEBAR_WIDTH + SIDEBAR_GAP) : 0));

    const maxAllowedH = Math.max(
        MIN_MENU_HEIGHT,
        Math.min(MAX_MENU_HEIGHT, safeWorkH - 20)
    );
    const totalHeight = Math.round(
        clampNumber(desiredHeight || 660, Math.min(MIN_MENU_HEIGHT, maxAllowedH), maxAllowedH)
    );

    return {
        requestedCols,
        maxFittingCols,
        effectiveCols,
        colWidth: widthDims.colWidth,
        groupColWidth: widthDims.colWidth,
        cardWidth: widthDims.colWidth + GROUP_CARD_PAD_X,
        colGap: GROUP_HORIZ_GAP,
        groupGap: GROUP_VERT_GAP,
        boardContentWidth: widthDims.boardContentWidth,
        boardWidth: visibleBoardWidth,
        boardPaddingX: BOARD_PADDING_X,
        rootPaddingX: ROOT_PADDING_X,
        sidebarGap,
        sidebarWidth,
        totalWidth,
        totalMenuWidth: totalWidth,
        menuWidth: totalWidth,
        totalHeight,
        totalMenuHeight: totalHeight,
        menuHeight: totalHeight,
        unitPx,
    };
}

/**
 * Pure mathematical edge hit-tester for resizing.
 * Returns 'corner' | 'top' | 'side' ONLY along outer free edges; returns null anywhere inside.
 */
export function detectResizeEdge(stageX, stageY, panelRect, isRtl = false, edgePx = 12, outerPx = 6) {
    if (!panelRect || panelRect.width <= 0 || panelRect.height <= 0)
        return null;
    const { x, y, width, height } = panelRect;
    if (
        stageX < (x - outerPx)
        || stageX > (x + width + outerPx)
        || stageY < (y - outerPx)
        || stageY > (y + height + outerPx)
    ) {
        return null;
    }

    const onTop = stageY >= (y - outerPx)
        && stageY <= (y + edgePx)
        && stageX >= (x - outerPx)
        && stageX <= (x + width + outerPx);
    const onOuterSide = isRtl
        ? (stageX >= (x - outerPx) && stageX <= (x + edgePx) && stageY >= (y - outerPx) && stageY <= (y + height + outerPx))
        : (stageX >= (x + width - edgePx) && stageX <= (x + width + outerPx) && stageY >= (y - outerPx) && stageY <= (y + height + outerPx));

    if (onTop && onOuterSide)
        return 'corner';
    if (onTop)
        return 'top';
    if (onOuterSide)
        return 'side';
    return null;
}

/**
 * Computes explicit Clutter.FixedLayout pixel coordinates { x, y, width, height }
 * honoring explicit saved 2D coordinates (col, row) when present, and filling
 * gaps cleanly without forcing positioned tiles back to (0, 0).
 */
export function computeTileRects(
    tiles,
    unitSize = 46,
    gutter = TILE_GAP,
    gridCols = GROUP_GRID_COLS,
    isRtl = false
) {
    const list = Array.isArray(tiles) ? tiles : [];
    const safeCols = Math.max(4, Math.round(Number(gridCols) || GROUP_GRID_COLS));
    const colWidth = getGroupColumnWidth(unitSize, safeCols, gutter);
    const grid = [];
    const placements = new Array(list.length);

    const ensureRows = rowCount => {
        while (grid.length < rowCount)
            grid.push(new Array(safeCols).fill(false));
    };

    const canPlace = (col, row, spanW, spanH) => {
        if (col < 0 || row < 0 || col + spanW > safeCols)
            return false;
        ensureRows(row + spanH);
        for (let r = row; r < row + spanH; r++) {
            for (let c = col; c < col + spanW; c++) {
                if (grid[r][c])
                    return false;
            }
        }
        return true;
    };

    const markPlace = (col, row, spanW, spanH) => {
        ensureRows(row + spanH);
        for (let r = row; r < row + spanH; r++) {
            for (let c = col; c < col + spanW; c++)
                grid[r][c] = true;
        }
    };

    const hasExplicitCoords = item => (
        item && Number.isInteger(item.col) && item.col >= 0
        && Number.isInteger(item.row) && item.row >= 0
    );

    let maxRowUsed = 0;

    const commitPlacement = (idx, item, placedCol, placedRow, dims, spanW, spanH) => {
        markPlace(placedCol, placedRow, spanW, spanH);
        maxRowUsed = Math.max(maxRowUsed, placedRow + spanH);

        const width = spanW * unitSize + Math.max(0, spanW - 1) * gutter;
        const height = spanH * unitSize + Math.max(0, spanH - 1) * gutter;
        const rawX = placedCol * (unitSize + gutter);
        const x = isRtl ? (colWidth - (rawX + width)) : rawX;
        const y = placedRow * (unitSize + gutter);

        placements[idx] = {
            item,
            index: idx,
            col: placedCol,
            row: placedRow,
            colSpan: spanW,
            rowSpan: spanH,
            spanW,
            spanH,
            rawX,
            x,
            y,
            width,
            height,
        };
    };

    // Pass 1: Place explicitly positioned items at their saved (col, row), pushing down on conflict
    for (let i = 0; i < list.length; i++) {
        const item = list[i];
        if (!hasExplicitCoords(item))
            continue;

        const dims = getTilePixelDimensions(item?.size, unitSize, gutter);
        const spanW = Math.min(dims.spanW, safeCols);
        const spanH = dims.spanH;
        const prefCol = Math.min(safeCols - spanW, Math.max(0, item.col));
        const prefRow = Math.max(0, item.row);

        let placedCol = prefCol;
        let placedRow = prefRow;
        let found = false;

        for (let r = prefRow; r < prefRow + 200; r++) {
            if (canPlace(prefCol, r, spanW, spanH)) {
                placedRow = r;
                found = true;
                break;
            }
        }
        if (!found) {
            for (let r = prefRow; !found && r < 500; r++) {
                for (let c = 0; c <= safeCols - spanW; c++) {
                    if (canPlace(c, r, spanW, spanH)) {
                        placedCol = c;
                        placedRow = r;
                        found = true;
                        break;
                    }
                }
            }
        }

        commitPlacement(i, item, placedCol, placedRow, dims, spanW, spanH);
    }

    // Pass 2: Pack unpositioned items into first available slots without moving anchored items
    for (let i = 0; i < list.length; i++) {
        if (placements[i])
            continue;
        const item = list[i];
        const dims = getTilePixelDimensions(item?.size, unitSize, gutter);
        const spanW = Math.min(dims.spanW, safeCols);
        const spanH = dims.spanH;

        let placedCol = 0;
        let placedRow = 0;
        let found = false;

        for (let row = 0; !found; row++) {
            ensureRows(row + spanH);
            for (let col = 0; col <= safeCols - spanW; col++) {
                if (canPlace(col, row, spanW, spanH)) {
                    placedCol = col;
                    placedRow = row;
                    found = true;
                    break;
                }
            }
            if (row > 500) {
                placedRow = grid.length;
                placedCol = 0;
                break;
            }
        }

        commitPlacement(i, item, placedCol, placedRow, dims, spanW, spanH);
    }

    const rects = placements.filter(Boolean);
    const totalRows = maxRowUsed;
    const totalHeight = totalRows > 0
        ? totalRows * unitSize + Math.max(0, totalRows - 1) * gutter
        : 0;

    return {
        rects,
        placements: rects,
        totalCols: safeCols,
        totalRows,
        colWidth,
        totalWidth: colWidth,
        pixelWidth: colWidth,
        totalHeight,
        pixelHeight: totalHeight,
    };
}

export function packTiles(items, maxCols = GROUP_GRID_COLS, unitPx = 46, gap = TILE_GAP, isRtl = false) {
    return computeTileRects(items, unitPx, gap, maxCols, isRtl);
}

/**
 * Moves or inserts `movingItemId` at (targetCol, targetRow) in a 6-column group,
 * pushing colliding tiles smoothly downward without collapsing other tiles back to (0, 0).
 */
export function placeTileAt(items, movingItemId, targetCol, targetRow, gridCols = GROUP_GRID_COLS) {
    const safeCols = Math.max(4, Math.round(Number(gridCols) || GROUP_GRID_COLS));
    const packedBefore = computeTileRects(items, 40, TILE_GAP, safeCols, false).rects;

    const movingRect = packedBefore.find(r => r.item?.id === movingItemId);
    if (!movingRect)
        return packedBefore.map(r => ({ ...r.item, col: r.col, row: r.row }));

    const spanW = movingRect.spanW;
    const spanH = movingRect.spanH;
    const placedCol = Math.min(safeCols - spanW, Math.max(0, Math.round(Number(targetCol) || 0)));
    const placedRow = Math.max(0, Math.round(Number(targetRow) || 0));

    const overlaps = (aCol, aRow, aW, aH, bCol, bRow, bW, bH) => {
        return aCol < (bCol + bW)
            && (aCol + aW) > bCol
            && aRow < (bRow + bH)
            && (aRow + aH) > bRow;
    };

    const fixedEntry = {
        ...movingRect.item,
        col: placedCol,
        row: placedRow,
        _spanW: spanW,
        _spanH: spanH,
    };

    // Prepare other tiles sorted by current (row, col), keeping their existing coordinates
    const others = packedBefore
        .filter(r => r.item?.id !== movingItemId)
        .sort((a, b) => (a.row - b.row) || (a.col - b.col))
        .map(r => ({
            ...r.item,
            col: r.col,
            row: r.row,
            _spanW: r.spanW,
            _spanH: r.spanH,
        }));

    // Push any tile overlapping the placed tile or pushed predecessors downward cleanly
    const placedList = [fixedEntry];
    for (const o of others) {
        let curRow = o.row;
        let settled = false;
        while (!settled && curRow < 500) {
            let blocker = null;
            for (const p of placedList) {
                if (overlaps(o.col, curRow, o._spanW, o._spanH, p.col, p.row, p._spanW, p._spanH)) {
                    blocker = p;
                    break;
                }
            }
            if (!blocker) {
                settled = true;
            } else {
                curRow = blocker.row + blocker._spanH;
            }
        }
        o.row = curRow;
        placedList.push(o);
    }

    placedList.sort((a, b) => (a.row - b.row) || (a.col - b.col));
    return placedList.map(entry => {
        const clean = { ...entry };
        delete clean._spanW;
        delete clean._spanH;
        return clean;
    });
}

export function distributeGroupsToColumns(groups, colCount, unitSize = 46, gap = TILE_GAP) {
    const safeCols = Math.max(MIN_TILE_COLUMNS, Math.min(8, Math.round(Number(colCount) || 1)));
    const list = Array.isArray(groups) ? groups : [];
    const columns = Array.from({ length: safeCols }, () => []);
    const heights = new Array(safeCols).fill(0);

    const estimateGroupHeight = grp => {
        const items = Array.isArray(grp?.items) ? grp.items : [];
        const packed = computeTileRects(items, unitSize, gap, GROUP_GRID_COLS, false);
        const tilesH = items.length > 0 ? packed.totalHeight : 64;
        return GROUP_HEADER_HEIGHT + GROUP_HEADER_MARGIN_BOTTOM + tilesH + GROUP_VERT_GAP;
    };

    const pickShortestColumn = () => {
        let best = 0;
        let minH = heights[0];
        for (let c = 1; c < safeCols; c++) {
            if (heights[c] < minH) {
                minH = heights[c];
                best = c;
            }
        }
        return best;
    };

    for (const grp of list) {
        let targetCol;
        if (Number.isInteger(grp?.column) && grp.column >= 0 && grp.column < safeCols)
            targetCol = grp.column;
        else
            targetCol = pickShortestColumn();

        columns[targetCol].push(grp);
        heights[targetCol] += estimateGroupHeight(grp);
    }

    return {
        colCount: safeCols,
        columns,
        heights,
    };
}

/**
 * Computes exact drop resolution including 2D (targetCol, targetRow) and previewSlotRect.
 */
export function hitTestTileGrid({
    stageX,
    stageY,
    columnDescriptors = [],
    dragKind = 'tile',
    dragPayload = {},
    isRtl = false,
    unitPx = 46,
    gap = TILE_GAP,
}) {
    const insideRect = (rect, x, y) => {
        return rect
            && rect.width > 0
            && rect.height > 0
            && x >= rect.x
            && x <= (rect.x + rect.width)
            && y >= rect.y
            && y <= (rect.y + rect.height);
    };

    if (dragKind === 'group-header') {
        for (const colDesc of columnDescriptors) {
            for (const grpDesc of (colDesc.groups || [])) {
                if (insideRect(grpDesc.headerRect, stageX, stageY) || insideRect(grpDesc.cardRect, stageX, stageY)) {
                    return {
                        action: 'reorder-group',
                        groupId: grpDesc.groupId,
                        targetColumn: colDesc.colIndex,
                        actor: grpDesc.headerActor || grpDesc.cardActor || null,
                        highlightClass: 'sadeem-group-drop-active',
                    };
                }
            }
            if (insideRect(colDesc.columnRect, stageX, stageY)) {
                return {
                    action: 'move-group-to-column',
                    targetColumn: colDesc.colIndex,
                    actor: colDesc.dropFooterActor || colDesc.columnActor || null,
                    highlightClass: 'sadeem-new-group-dropzone-active',
                };
            }
        }
        return null;
    }

    const isSourceFolder = dragPayload?.itemType === 'folder';
    const draggedDims = getTilePixelDimensions(dragPayload?.size || 'medium', unitPx, gap);
    const draggedSpanW = draggedDims.spanW;
    const draggedSpanH = draggedDims.spanH;

    const computeCanvasPreview = (canvasRect, x, y) => {
        if (!canvasRect)
            return null;
        const colWidth = getGroupColumnWidth(unitPx, GROUP_GRID_COLS, gap);
        const relX = clampNumber(x - canvasRect.x, 0, colWidth);
        const logicalX = isRtl ? (colWidth - relX) : relX;
        const relY = Math.max(0, y - canvasRect.y);

        const rawCol = Math.floor(logicalX / (unitPx + gap));
        const targetCol = Math.min(GROUP_GRID_COLS - draggedSpanW, Math.max(0, rawCol));
        const targetRow = Math.max(0, Math.floor(relY / (unitPx + gap)));

        const slotRawX = targetCol * (unitPx + gap);
        const slotLocalX = isRtl ? (colWidth - (slotRawX + draggedDims.width)) : slotRawX;
        const slotLocalY = targetRow * (unitPx + gap);

        return {
            targetCol,
            targetRow,
            previewRect: {
                x: canvasRect.x + slotLocalX,
                y: canvasRect.y + slotLocalY,
                width: draggedDims.width,
                height: draggedDims.height,
            },
        };
    };

    for (const colDesc of columnDescriptors) {
        // 1. Open inline folder drawer
        if (!isSourceFolder && colDesc.openDrawer && insideRect(colDesc.openDrawer.rect, stageX, stageY)) {
            return {
                action: 'add-to-folder',
                targetGroupId: colDesc.openDrawer.groupId,
                folderId: colDesc.openDrawer.folderId,
                targetColumn: colDesc.colIndex,
                actor: colDesc.openDrawer.actor || null,
                highlightClass: 'sadeem-group-drop-active',
            };
        }

        // 2. Groups inside this vertical column
        for (const grpDesc of (colDesc.groups || [])) {
            for (const tileDesc of (grpDesc.tiles || [])) {
                const tr = tileDesc.rect;
                if (!insideRect(tr, stageX, stageY))
                    continue;

                const rx = (stageX - tr.x) / tr.width;
                const ry = (stageY - tr.y) / tr.height;
                const isSameItem = !dragPayload?.folderId
                    && dragPayload?.sourceGroupId === grpDesc.groupId
                    && dragPayload?.itemId === tileDesc.itemId
                    && dragPayload?.itemType === tileDesc.itemType;

                if (!isSourceFolder && !isSameItem) {
                    if (tileDesc.itemType === 'folder') {
                        if (rx >= 0.16 && rx <= 0.84 && ry >= 0.16 && ry <= 0.84) {
                            return {
                                action: 'add-to-folder',
                                targetGroupId: grpDesc.groupId,
                                folderId: tileDesc.itemId,
                                targetColumn: colDesc.colIndex,
                                actor: tileDesc.actor || null,
                                highlightClass: 'sadeem-tile-drop-folder',
                            };
                        }
                    } else if (rx >= 0.24 && rx <= 0.76 && ry >= 0.24 && ry <= 0.76) {
                        return {
                            action: 'create-folder',
                            targetGroupId: grpDesc.groupId,
                            targetAppId: tileDesc.itemId,
                            targetColumn: colDesc.colIndex,
                            actor: tileDesc.actor || null,
                            highlightClass: 'sadeem-tile-drop-folder',
                        };
                    }
                }

                const snap = computeCanvasPreview(grpDesc.canvasRect, stageX, stageY);
                const isAfter = isRtl ? (rx < 0.5) : (rx >= 0.5);
                return {
                    action: 'reorder-tile',
                    targetGroupId: grpDesc.groupId,
                    insertIndex: isAfter ? tileDesc.index + 1 : tileDesc.index,
                    targetColumn: colDesc.colIndex,
                    targetCol: snap ? snap.targetCol : tileDesc.col,
                    targetRow: snap ? snap.targetRow : tileDesc.row,
                    previewRect: snap ? snap.previewRect : tr,
                    actor: tileDesc.actor || null,
                    highlightClass: 'sadeem-tile-drop-target',
                };
            }

            if (insideRect(grpDesc.cardRect, stageX, stageY)) {
                const snap = computeCanvasPreview(grpDesc.canvasRect, stageX, stageY);
                return {
                    action: 'move-to-group',
                    targetGroupId: grpDesc.groupId,
                    targetColumn: colDesc.colIndex,
                    targetCol: snap ? snap.targetCol : 0,
                    targetRow: snap ? snap.targetRow : 0,
                    previewRect: snap ? snap.previewRect : null,
                    actor: grpDesc.cardActor || grpDesc.canvasActor || null,
                    highlightClass: 'sadeem-group-drop-active',
                };
            }
        }

        // 3. Explicit new-group zone or empty space below column
        if (insideRect(colDesc.dropFooterRect, stageX, stageY) || insideRect(colDesc.columnRect, stageX, stageY)) {
            return {
                action: 'new-group',
                targetColumn: colDesc.colIndex,
                actor: colDesc.dropFooterActor || null,
                highlightClass: 'sadeem-new-group-dropzone-active',
            };
        }
    }

    return null;
}

export function computeSurfacePosition({
    workArea = { x: 0, y: 0, width: 1920, height: 1040 },
    anchorRect = null,
    totalWidth = 1158,
    totalHeight = 680,
    isRtl = false,
    margin = 8,
} = {}) {
    const waX = Number(workArea?.x) || 0;
    const waY = Number(workArea?.y) || 0;
    const waW = Math.max(360, Number(workArea?.width) || 1920);
    const waH = Math.max(360, Number(workArea?.height) || 1040);

    const w = Math.min(totalWidth, Math.max(100, waW - 2 * margin));
    const h = Math.min(totalHeight, Math.max(100, waH - 2 * margin));

    const hasAnchor = anchorRect
        && Number.isFinite(anchorRect.x)
        && Number.isFinite(anchorRect.y);
    const isBottom = hasAnchor ? (anchorRect.y > (waY + waH / 2)) : true;

    const minX = waX + margin;
    const maxX = Math.max(minX, waX + waW - w - margin);
    const minY = waY + margin;
    const maxY = Math.max(minY, waY + waH - h - margin);

    let rawX;
    if (hasAnchor) {
        const aw = Number(anchorRect.width) || 36;
        rawX = isRtl ? (anchorRect.x + aw - w) : anchorRect.x;
    } else {
        rawX = isRtl ? (waX + waW - w - margin) : (waX + margin);
    }

    const rawY = isBottom ? (waY + waH - h - margin) : (waY + margin);

    return {
        x: Math.round(clampNumber(rawX, minX, maxX)),
        y: Math.round(clampNumber(rawY, minY, maxY)),
        width: w,
        height: h,
        isBottom,
    };
}

export function clampContextMenuPosition({
    stageX = 0,
    stageY = 0,
    menuWidth = 220,
    menuHeight = 240,
    workArea = { x: 0, y: 0, width: 1920, height: 1040 },
    isRtl = false,
    margin = 8,
} = {}) {
    const waX = Number(workArea?.x) || 0;
    const waY = Number(workArea?.y) || 0;
    const waW = Math.max(320, Number(workArea?.width) || 1920);
    const waH = Math.max(240, Number(workArea?.height) || 1040);

    const minX = waX + margin;
    const maxX = Math.max(minX, waX + waW - menuWidth - margin);
    const minY = waY + margin;
    const maxY = Math.max(minY, waY + waH - menuHeight - margin);

    let rawX = isRtl ? (stageX - menuWidth - 2) : (stageX + 2);
    if (isRtl && rawX < minX)
        rawX = stageX + 2;
    else if (!isRtl && (rawX + menuWidth) > (waX + waW - margin))
        rawX = stageX - menuWidth - 2;

    let rawY = stageY + 2;
    if ((rawY + menuHeight) > (waY + waH - margin))
        rawY = stageY - menuHeight - 2;

    return {
        x: Math.round(clampNumber(rawX, minX, maxX)),
        y: Math.round(clampNumber(rawY, minY, maxY)),
    };
}

// ---------------- Unified 2D Free Board & Compact Foldable Group Geometry ----------------

export function getCellDimensions(level = 2) {
    const idx = Math.round(clampNumber(level, 0, CELL_SIZES.length - 1));
    return CELL_SIZES[idx];
}

export function normalizeGroupCardSize(cardSize) {
    if (cardSize && Object.prototype.hasOwnProperty.call(GROUP_CARD_SIZES, cardSize))
        return cardSize;
    return '2x2';
}

export function getLooseAppIconSize(cellW = 72) {
    return Math.max(36, Math.round(cellW * 0.639)); // 46px at default cellW=72
}

export function getCompactGroupIconSize(slotW = 67, slotH = 63) {
    return Math.min(32, Math.max(24, Math.round(Math.min(slotW, slotH) * 0.50))); // 30..32px compact icons
}

export function getBoardItemDimensions(
    itemType = 'app',
    cardSize = '2x2',
    cellW = 72,
    cellH = 82,
    gap = CELL_GAP
) {
    if (itemType === 'group') {
        const spec = GROUP_CARD_SIZES[normalizeGroupCardSize(cardSize)];
        return {
            itemType: 'group',
            cardSize: spec.key,
            spanW: spec.spanW,
            spanH: spec.spanH,
            width: spec.spanW * cellW + Math.max(0, spec.spanW - 1) * gap,
            height: spec.spanH * cellH + Math.max(0, spec.spanH - 1) * gap,
        };
    }
    return {
        itemType: 'app',
        cardSize: '1x1',
        spanW: 1,
        spanH: 1,
        width: cellW,
        height: cellH,
    };
}

export function getBoardItemKey(item) {
    if (!item || !item.id)
        return '';
    return `${item.type === 'group' ? 'group' : 'app'}:${item.id}`;
}

export function computeCompactGroupSlots(apps, cardSize = '2x2') {
    const spec = GROUP_CARD_SIZES[normalizeGroupCardSize(cardSize)];
    const list = Array.isArray(apps) ? apps : [];
    const hasOverflowCluster = list.length > spec.capacity;
    const directApps = hasOverflowCluster ? list.slice(0, spec.capacity - 1) : list.slice();
    const overflowApps = hasOverflowCluster ? list.slice(spec.capacity - 1) : [];
    return {
        cardSize: spec.key,
        innerCols: spec.innerCols,
        innerRows: spec.innerRows,
        spanW: spec.spanW,
        spanH: spec.spanH,
        capacity: spec.capacity,
        totalCount: list.length,
        directApps,
        overflowApps,
        clusterApps: overflowApps.slice(0, 4),
        overflowCount: overflowApps.length,
        hasOverflowCluster,
    };
}

export function computeUnifiedBoardRects(
    items,
    cellW = 72,
    cellH = 82,
    gap = CELL_GAP,
    minCols = MIN_BOARD_GRID_COLS,
    isRtl = false
) {
    const list = Array.isArray(items) ? items : [];
    let safeCols = Math.max(4, Math.round(Number(minCols) || MIN_BOARD_GRID_COLS));

    const itemDims = list.map(it =>
        getBoardItemDimensions(it?.type === 'group' ? 'group' : 'app', it?.cardSize, cellW, cellH, gap)
    );

    const hasExplicitCoords = it => (
        it && Number.isInteger(it.col) && it.col >= 0
        && Number.isInteger(it.row) && it.row >= 0
    );

    for (let i = 0; i < list.length; i++) {
        const it = list[i];
        if (hasExplicitCoords(it))
            safeCols = Math.max(safeCols, it.col + itemDims[i].spanW);
    }

    const totalWidth = safeCols * cellW + Math.max(0, safeCols - 1) * gap;
    const grid = [];
    const placements = new Array(list.length);

    const ensureRows = rowCount => {
        while (grid.length < rowCount)
            grid.push(new Array(safeCols).fill(false));
    };

    const canPlace = (col, row, spanW, spanH) => {
        if (col < 0 || row < 0 || col + spanW > safeCols)
            return false;
        ensureRows(row + spanH);
        for (let r = row; r < row + spanH; r++) {
            for (let c = col; c < col + spanW; c++) {
                if (grid[r][c])
                    return false;
            }
        }
        return true;
    };

    const markPlace = (col, row, spanW, spanH) => {
        ensureRows(row + spanH);
        for (let r = row; r < row + spanH; r++) {
            for (let c = col; c < col + spanW; c++)
                grid[r][c] = true;
        }
    };

    let maxRowUsed = 0;

    const commitPlacement = (idx, item, dims, placedCol, placedRow) => {
        markPlace(placedCol, placedRow, dims.spanW, dims.spanH);
        maxRowUsed = Math.max(maxRowUsed, placedRow + dims.spanH);

        const rawX = placedCol * (cellW + gap);
        const x = isRtl ? (totalWidth - (rawX + dims.width)) : rawX;
        const y = placedRow * (cellH + gap);

        placements[idx] = {
            item,
            key: getBoardItemKey(item),
            index: idx,
            col: placedCol,
            row: placedRow,
            spanW: dims.spanW,
            spanH: dims.spanH,
            colSpan: dims.spanW,
            rowSpan: dims.spanH,
            rawX,
            x,
            y,
            width: dims.width,
            height: dims.height,
        };
    };

    // Pass 1: Honor saved explicit (col, row) coordinates
    for (let i = 0; i < list.length; i++) {
        const item = list[i];
        if (!hasExplicitCoords(item))
            continue;
        const dims = itemDims[i];
        const prefCol = Math.min(safeCols - dims.spanW, Math.max(0, item.col));
        const prefRow = Math.max(0, item.row);

        let placedCol = prefCol;
        let placedRow = prefRow;
        let found = false;

        for (let r = prefRow; r < prefRow + 200; r++) {
            if (canPlace(prefCol, r, dims.spanW, dims.spanH)) {
                placedRow = r;
                found = true;
                break;
            }
        }
        if (!found) {
            for (let r = prefRow; !found && r < 500; r++) {
                for (let c = 0; c <= safeCols - dims.spanW; c++) {
                    if (canPlace(c, r, dims.spanW, dims.spanH)) {
                        placedCol = c;
                        placedRow = r;
                        found = true;
                        break;
                    }
                }
            }
        }
        commitPlacement(i, item, dims, placedCol, placedRow);
    }

    // Pass 2: Pack unpositioned items cleanly into first open slots
    for (let i = 0; i < list.length; i++) {
        if (placements[i])
            continue;
        const item = list[i];
        const dims = itemDims[i];
        let placedCol = 0;
        let placedRow = 0;
        let found = false;

        for (let row = 0; !found; row++) {
            ensureRows(row + dims.spanH);
            for (let col = 0; col <= safeCols - dims.spanW; col++) {
                if (canPlace(col, row, dims.spanW, dims.spanH)) {
                    placedCol = col;
                    placedRow = row;
                    found = true;
                    break;
                }
            }
            if (row > 500) {
                placedRow = grid.length;
                placedCol = 0;
                break;
            }
        }
        commitPlacement(i, item, dims, placedCol, placedRow);
    }

    const rects = placements.filter(Boolean);
    const totalRows = Math.max(1, maxRowUsed);
    const totalHeight = totalRows * cellH + Math.max(0, totalRows - 1) * gap;

    return {
        rects,
        totalCols: safeCols,
        totalRows,
        cellW,
        cellH,
        gap,
        totalWidth,
        totalHeight,
    };
}

export function placeBoardItemAt(
    items,
    movingKey,
    targetCol,
    targetRow,
    minCols = MIN_BOARD_GRID_COLS
) {
    const packedBefore = computeUnifiedBoardRects(items, 78, 84, CELL_GAP, minCols, false).rects;
    const movingRect = packedBefore.find(r => r.key === movingKey || r.item?.id === movingKey);
    if (!movingRect)
        return packedBefore.map(r => ({ ...r.item, col: r.col, row: r.row }));

    const spanW = movingRect.spanW;
    const spanH = movingRect.spanH;
    const placedCol = Math.min(32, Math.max(0, Math.round(Number(targetCol) || 0)));
    const placedRow = Math.max(0, Math.round(Number(targetRow) || 0));

    const overlaps = (aCol, aRow, aW, aH, bCol, bRow, bW, bH) => (
        aCol < (bCol + bW)
        && (aCol + aW) > bCol
        && aRow < (bRow + bH)
        && (aRow + aH) > bRow
    );

    const fixedEntry = {
        ...movingRect.item,
        col: placedCol,
        row: placedRow,
        _spanW: spanW,
        _spanH: spanH,
    };

    const others = packedBefore
        .filter(r => r.key !== movingRect.key)
        .sort((a, b) => (a.row - b.row) || (a.col - b.col))
        .map(r => ({
            ...r.item,
            col: r.col,
            row: r.row,
            _spanW: r.spanW,
            _spanH: r.spanH,
        }));

    const placedList = [fixedEntry];
    for (const o of others) {
        let curRow = o.row;
        let settled = false;
        while (!settled && curRow < 500) {
            let blocker = null;
            for (const p of placedList) {
                if (overlaps(o.col, curRow, o._spanW, o._spanH, p.col, p.row, p._spanW, p._spanH)) {
                    blocker = p;
                    break;
                }
            }
            if (!blocker)
                settled = true;
            else
                curRow = blocker.row + blocker._spanH;
        }
        o.row = curRow;
        placedList.push(o);
    }

    placedList.sort((a, b) => (a.row - b.row) || (a.col - b.col));
    return placedList.map(entry => {
        const clean = { ...entry };
        delete clean._spanW;
        delete clean._spanH;
        return clean;
    });
}

export function hitTestUnifiedBoard({
    localX,
    localY,
    boardCols = MIN_BOARD_GRID_COLS,
    totalWidth,
    cellW = 78,
    cellH = 84,
    gap = CELL_GAP,
    itemRects = [],
    dragKind = 'board-app',
    dragPayload = {},
    isRtl = false,
}) {
    if (!Number.isFinite(localX) || !Number.isFinite(localY))
        return null;

    const canvasW = Number.isFinite(totalWidth) && totalWidth > 0
        ? totalWidth
        : (boardCols * cellW + Math.max(0, boardCols - 1) * gap);

    const insideRect = (rect, x, y) => (
        rect
        && rect.width > 0
        && rect.height > 0
        && x >= rect.x
        && x <= (rect.x + rect.width)
        && y >= rect.y
        && y <= (rect.y + rect.height)
    );

    const isGroupDrag = dragKind === 'board-group';

    if (!isGroupDrag) {
        for (const desc of itemRects) {
            if (!insideRect(desc, localX, localY))
                continue;

            const isSelfLoose = desc.item?.type !== 'group'
                && dragKind === 'board-app'
                && !dragPayload?.sourceGroupId
                && desc.item?.id === dragPayload?.itemId;
            if (isSelfLoose)
                continue;

            if (desc.item?.type === 'group') {
                if (dragPayload?.sourceGroupId === desc.item.id)
                    continue;
                return {
                    action: 'add-to-group',
                    targetGroupId: desc.item.id,
                    actor: desc.actor || null,
                    highlightClass: 'sadeem-group-drop-active',
                    previewRect: null,
                };
            }

            const rx = (localX - desc.x) / desc.width;
            const ry = (localY - desc.y) / desc.height;
            if (rx >= 0.18 && rx <= 0.82 && ry >= 0.18 && ry <= 0.82) {
                return {
                    action: 'merge-apps-into-group',
                    targetAppId: desc.item.id,
                    targetCol: desc.col,
                    targetRow: desc.row,
                    actor: desc.actor || null,
                    highlightClass: 'sadeem-tile-drop-folder',
                    previewRect: null,
                };
            }
        }
    }

    const draggedDims = getBoardItemDimensions(
        isGroupDrag ? 'group' : 'app',
        dragPayload?.cardSize || '2x2',
        cellW,
        cellH,
        gap
    );

    const logicalX = isRtl ? (canvasW - localX) : localX;
    const offsetHalfCell = isGroupDrag ? (cellW * 0.45) : 0;
    const rawCol = Math.max(0, Math.floor(Math.max(0, logicalX - offsetHalfCell) / (cellW + gap)));
    const targetCol = Math.min(24, rawCol);
    const targetRow = Math.max(0, Math.floor(Math.max(0, localY) / (cellH + gap)));

    const previewRawX = targetCol * (cellW + gap);
    const previewX = isRtl ? (canvasW - (previewRawX + draggedDims.width)) : previewRawX;
    const previewY = targetRow * (cellH + gap);

    return {
        action: 'place-board-item',
        itemType: isGroupDrag ? 'group' : 'app',
        itemId: isGroupDrag ? dragPayload?.groupId : dragPayload?.itemId,
        sourceGroupId: dragPayload?.sourceGroupId || null,
        targetCol,
        targetRow,
        actor: null,
        highlightClass: '',
        previewRect: {
            x: previewX,
            y: previewY,
            width: draggedDims.width,
            height: draggedDims.height,
        },
    };
}

export function computeRtlAnchoredScrollValue(upper, pageSize, rightOffset = 0, lower = 0) {
    const safeLower = Number.isFinite(Number(lower)) ? Number(lower) : 0;
    const safeUpper = Number.isFinite(Number(upper)) ? Number(upper) : safeLower;
    const safePage = Number.isFinite(Number(pageSize)) ? Math.max(0, Number(pageSize)) : 0;
    const safeRightOffset = Number.isFinite(Number(rightOffset)) ? Math.max(0, Number(rightOffset)) : 0;
    const maxV = Math.max(safeLower, safeUpper - safePage);
    return clampNumber(maxV - safeRightOffset, safeLower, maxV);
}

export function computeBoardRestHeight(packedHeight, scrollPageSize, viewportPadY = 14) {
    const baseH = Math.max(0, Math.round(Number(packedHeight) || 0));
    const pageH = Math.max(0, Math.floor(Number(scrollPageSize) || 0));
    const padY = Math.max(0, Math.round(Number(viewportPadY) || 0));
    const availH = Math.max(0, pageH - padY);
    return Math.max(baseH, availH);
}

export function computeDragExpandedBoardHeight(restHeight, previewRect, cellH = 82, gap = CELL_GAP) {
    const baseH = Math.max(0, Math.round(Number(restHeight) || 0));
    if (!previewRect || !Number.isFinite(previewRect.y) || !Number.isFinite(previewRect.height))
        return baseH;
    const neededBottom = Math.ceil(previewRect.y + previewRect.height + Math.max(0, Number(gap) || 0));
    if (neededBottom <= baseH)
        return baseH;
    const safetyRow = Math.max(24, Math.round(Number(cellH) || 82));
    return Math.max(baseH, neededBottom + safetyRow);
}
