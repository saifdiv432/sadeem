# Upstream Patches on Third-Party GNOME Shell Extensions

This document tracks custom Sadeem OS patches applied to third-party GNOME Shell extensions under `files/system/usr/share/gnome-shell/extensions/` so they are preserved cleanly when updating upstream extensions or rebasing onto **GNOME 52+**.

---

## 1. `dash-to-panel@jderose9.github.com`

- **Upstream:** <https://github.com/home-sweet-gnome/dash-to-panel> (version `74` in `metadata.json`)
- **Problem Fixed:** In RTL locales (Arabic), hovered taskbar window previews (`PreviewMenu`) were mirrored or pinned to the right monitor edge because `Clutter.BinLayout` + `x_align: START` reverses horizontal alignment in RTL containers.
- **Files Added / Modified:**
  - `files/system/usr/share/gnome-shell/extensions/dash-to-panel@jderose9.github.com/previewPosition.js` *(added)*
    - Pure helper `computePreviewMenuPosition(...)` computing physical LTR `(x, y, width, height)` inside the clipped stage box for both horizontal and vertical panels.
  - `files/system/usr/share/gnome-shell/extensions/dash-to-panel@jderose9.github.com/windowPreview.js` *(modified)*
    - `PreviewMenu._init`: switched layout manager to `Clutter.FixedLayout()` with `text_direction: Clutter.TextDirection.LTR` on `PreviewMenu` and `PreviewMenu.menu`, keeping `this._box.text_direction = Clutter.get_default_text_direction()`.
    - `PreviewMenu._updatePosition`: enforces LTR coordinates on `this` and `this.menu`, computes coordinates via `computePreviewMenuPosition(...)`, and restores RTL text direction on `Preview` cards.

---

## 2. `emoji-copy@felipeftn`

- **Upstream:** <https://github.com/felipeftn/emoji-copy> (version `43` in `metadata.json`)
- **Problem Fixed:** When `window-location` is `'cursor'` (`<Super>period`), the emoji popup could spawn or grow outside screen boundaries near any monitor edge or corner, especially when expanding categories or typing in search.
- **Files Added / Modified:**
  - `files/system/usr/share/gnome-shell/extensions/emoji-copy@felipeftn/popupClamp.js` *(added)*
    - Pure helpers `clampPopupAnchorToWorkArea(...)` and `clampPopupBoxToWorkArea(...)` enforcing monitor `workArea` bounds with a 12 px margin.
  - `files/system/usr/share/gnome-shell/extensions/emoji-copy@felipeftn/extension.js` *(modified)*
    - Tracks `_cursorAnchor` / `dummyCursor` in `Main.uiGroup`.
    - Clamps initial popup anchor coordinates via `clampPopupAnchorToWorkArea` when opening at cursor (`window-location === "cursor"`).
    - Connects `notify::allocation` on the `BoxPointer` (`_allocClampSigId`) to dynamically shift `_cursorAnchor` via `clampPopupBoxToWorkArea` when popup dimensions change.
  - `files/system/usr/share/gnome-shell/extensions/emoji-copy@felipeftn/schemas/gschemas.compiled` *(compiled; also auto-compiled during image build in `recipes/recipe.yml`)*.

---

## 3. `clipboard-indicator@tudmotu.com` (External Hook Only)

- **Upstream:** <https://github.com/Tudmotu/gnome-shell-extension-clipboard-indicator> (version `72` in `metadata.json`)
- **Status:** **No upstream source files modified inside `clipboard-indicator@tudmotu.com/`.**
- **External Integration:** Cursor-anchored popup positioning (`<Super>v`) and work-area clamping are injected externally at runtime by `sadeem-desktop-helper@sadeem.os` (`extension.js` + `popupClamp.js`).

---

## GNOME 52 Upgrade Checklist

When upgrading any third-party extension or rebasing onto GNOME 52:

1. **Snapshot & Replace Carefully:**
   - Before overwriting `dash-to-panel@jderose9.github.com/` or `emoji-copy@felipeftn/`, back up `previewPosition.js`, `popupClamp.js`, and check `git diff` against upstream `windowPreview.js` and `extension.js`.
2. **Update `metadata.json`:**
   - Ensure `"52"` is listed in `shell-version` for all extensions (both third-party and Sadeem-owned).
3. **Re-apply Patches:**
   - **Dash to Panel:** Re-copy `previewPosition.js`, re-apply the `Clutter.FixedLayout` + `computePreviewMenuPosition` changes in `windowPreview.js`, and check whether upstream changed `PreviewMenu` / `this.menu` / `this._updatePosition()`.
   - **Emoji Copy:** Re-copy `popupClamp.js` and re-apply cursor anchor + `notify::allocation` clamping in `extension.js`. Check upstream `Main.panel.addToStatusArea` key and `BoxPointer` allocation signals.
   - **Clipboard Indicator / Helper:** Verify `sadeem-desktop-helper@sadeem.os/extension.js` against GNOME 52 `PopupMenu` / `BoxPointer` (`_userArrowSide`, `setSourceAlignment`, allocation box properties).
4. **Recompile & Validate:**
   - Run `glib-compile-schemas` on modified schema directories (or let `recipes/recipe.yml` compile `/usr/share/gnome-shell/extensions/*/schemas` on build).
   - Run unit tests covering geometry, clamping, and GNOME typelib checks:
     - `python3 -B -m unittest discover -s tests -v`
5. **Interactive Verification (Wayland RTL + LTR):**
   - Hover multiple taskbar icons in Arabic (`RTL`) and verify Dash to Panel window previews center over each icon without sticking to the right edge.
   - Press `Super + .` and `Super + V` near all four screen corners/edges and expand categories/search to confirm popups stay fully inside the monitor work area.
