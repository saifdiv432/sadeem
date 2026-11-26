// Pure coordinate positioning helper for Dash to Panel PreviewMenu (LTR & RTL safe).

export const SIDE_TOP = 0;
export const SIDE_RIGHT = 1;
export const SIDE_BOTTOM = 2;
export const SIDE_LEFT = 3;

/**
 * Computes physical LTR (x, y) position of PreviewMenu.menu within PreviewMenu's clipped
 * stage box so hovered previews always center over their taskbar icon in both RTL and LTR.
 */
export function computePreviewMenuPosition({
    sourceX1,
    sourceY1,
    sourceContentWidth,
    sourceContentHeight,
    appIconMargin = 0,
    previewsWidth,
    previewsHeight,
    monitorX = 0,
    monitorY = 0,
    monitorWidth = 1920,
    monitorHeight = 1080,
    clipWidth = 0,
    clipHeight = 0,
    vertical = false,
    position = SIDE_BOTTOM,
}) {
    const pw = Math.min(previewsWidth, monitorWidth);
    const ph = Math.min(previewsHeight, monitorHeight);
    let x = 0;
    let y = 0;

    if (vertical) {
        y = sourceY1 + appIconMargin - monitorY + (sourceContentHeight - ph) * 0.5;
        y = Math.max(0, Math.min(y, monitorHeight - ph));
        x = position === SIDE_RIGHT ? Math.max(0, (clipWidth || pw) - pw) : 0;
    } else {
        x = sourceX1 + appIconMargin - monitorX + (sourceContentWidth - pw) * 0.5;
        x = Math.max(0, Math.min(x, monitorWidth - pw));
        y = position === SIDE_BOTTOM ? Math.max(0, (clipHeight || ph) - ph) : 0;
    }

    return {
        x: Math.round(x),
        y: Math.round(y),
        width: pw,
        height: ph,
    };
}
