// Pure work-area bounding helpers for Emoji Copy cursor-anchored popups.

export const SIDE_TOP = 0;
export const SIDE_RIGHT = 1;
export const SIDE_BOTTOM = 2;
export const SIDE_LEFT = 3;

function normalizeSide(arrowSide) {
    if (arrowSide === SIDE_RIGHT || arrowSide === SIDE_BOTTOM || arrowSide === SIDE_LEFT) {
        return arrowSide;
    }
    return SIDE_TOP;
}

/**
 * Computes clamped cursor anchor coordinates within workArea with safety margin.
 */
export function clampPopupAnchorToWorkArea(
    px,
    py,
    menuW,
    menuH,
    workArea,
    arrowSide = SIDE_TOP,
    margin = 12,
    arrowAlignment = 0.5
) {
    const wa = workArea || { x: 0, y: 0, width: 1920, height: 1080 };
    const w = (typeof menuW === 'number' && menuW > 0) ? menuW : 360;
    const h = (typeof menuH === 'number' && menuH > 0) ? menuH : 440;
    const m = (typeof margin === 'number' && margin >= 0) ? margin : 12;
    const align = (typeof arrowAlignment === 'number' && !Number.isNaN(arrowAlignment))
        ? Math.max(0, Math.min(1, arrowAlignment))
        : 0.5;
    const side = normalizeSide(arrowSide);

    const waLeft = wa.x + m;
    const waRight = wa.x + wa.width - m;
    const waTop = wa.y + m;
    const waBottom = wa.y + wa.height - m;

    let ax = Number(px) || 0;
    let ay = Number(py) || 0;

    if (side === SIDE_LEFT || side === SIDE_RIGHT) {
        const minY = waTop + h * align;
        const maxY = waBottom - h * (1 - align);
        ay = minY > maxY ? (wa.y + wa.height * align) : Math.max(minY, Math.min(ay, maxY));

        if (side === SIDE_LEFT) {
            const maxX = waRight - w;
            ax = waLeft > maxX ? waLeft : Math.max(waLeft, Math.min(ax, maxX));
        } else {
            const minX = waLeft + w;
            ax = minX > waRight ? waRight : Math.max(minX, Math.min(ax, waRight));
        }
    } else {
        const minX = waLeft + w * align;
        const maxX = waRight - w * (1 - align);
        ax = minX > maxX ? (wa.x + wa.width * align) : Math.max(minX, Math.min(ax, maxX));

        if (side === SIDE_BOTTOM) {
            const minY = waTop + h;
            const maxY = waBottom;
            ay = minY > maxY ? waBottom : Math.max(minY, Math.min(ay, maxY));
        } else {
            const minY = waTop;
            const maxY = waBottom - h;
            ay = minY > maxY ? waTop : Math.max(minY, Math.min(ay, maxY));
        }
    }

    return {
        x: Math.round(ax),
        y: Math.round(ay),
    };
}

/**
 * Clamps a realized BoxPointer actor rectangle (bx, by, bw, bh) cleanly inside workArea.
 */
export function clampPopupBoxToWorkArea(bx, by, bw, bh, workArea, margin = 12) {
    const wa = workArea || { x: 0, y: 0, width: 1920, height: 1080 };
    const m = (typeof margin === 'number' && margin >= 0) ? margin : 12;
    const minX = wa.x + m;
    const maxX = Math.max(minX, wa.x + wa.width - bw - m);
    const minY = wa.y + m;
    const maxY = Math.max(minY, wa.y + wa.height - bh - m);

    return {
        x: Math.round(Math.max(minX, Math.min(bx, maxX))),
        y: Math.round(Math.max(minY, Math.min(by, maxY))),
    };
}
