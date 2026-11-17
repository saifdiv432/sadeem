#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${GITHUB_WORKSPACE:-$(pwd)}"
ISO_INPUT="${1:-}"

if [ -n "$ISO_INPUT" ] && [ -f "$ISO_INPUT" ]; then
  ISO_FILE="$ISO_INPUT"
elif [ -n "$ISO_INPUT" ] && [ -f "$BASE_DIR/$ISO_INPUT" ]; then
  ISO_FILE="$BASE_DIR/$ISO_INPUT"
else
  # Dynamically locate the ISO file
  ISO_FILE=$(find "$BASE_DIR" -maxdepth 3 -type f -name "*.iso" 2>/dev/null | head -n 1 || true)
fi

if [ -z "$ISO_FILE" ] || [ ! -f "$ISO_FILE" ]; then
  echo "Error: ISO file '$ISO_INPUT' not found in workspace."
  exit 1
fi

# Obtain absolute path BEFORE changing directories
ISO_ABS=$(realpath "$ISO_FILE")

echo "=================================================="
echo "Customizing Anaconda WebUI, Cockpit & Plymouth in: $ISO_ABS"
echo "=================================================="

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cd "$WORK_DIR"

TARGET_PATH=""
IMG_NAME=""

# Extract images/install.img or LiveOS/squashfs.img
if xorriso -osirrox on -indev "$ISO_ABS" -extract /images/install.img ./install.img 2>/dev/null && [ -f ./install.img ]; then
  TARGET_PATH="/images/install.img"
  IMG_NAME="install.img"
elif xorriso -osirrox on -indev "$ISO_ABS" -extract /LiveOS/squashfs.img ./squashfs.img 2>/dev/null && [ -f ./squashfs.img ]; then
  TARGET_PATH="/LiveOS/squashfs.img"
  IMG_NAME="squashfs.img"
fi

if [ -n "$TARGET_PATH" ] && [ -f "$IMG_NAME" ]; then
  echo "Found installer image at $TARGET_PATH ($IMG_NAME). Unsquashing..."
  unsquashfs -d squashfs-root "$IMG_NAME"
  chmod -R u+w squashfs-root

  # --------------------------------------------------------------------------
  # 1. Plymouth boot splash configuration
  # --------------------------------------------------------------------------
  echo "--- 1. Configuring Plymouth theme dynamically in installer rootfs ---"
  if [ -d "squashfs-root/usr/share/plymouth/themes/bgrt" ]; then
    PLYMOUTH_THEME="bgrt"
  elif [ -d "squashfs-root/usr/share/plymouth/themes/spinner" ]; then
    PLYMOUTH_THEME="spinner"
  else
    PLYMOUTH_THEME="details"
  fi
  echo "Selected Plymouth theme for installer: $PLYMOUTH_THEME"

  mkdir -p squashfs-root/etc/plymouth squashfs-root/usr/share/plymouth 2>/dev/null || true
  cat << EOF > squashfs-root/etc/plymouth/plymouthd.conf
[Daemon]
Theme=${PLYMOUTH_THEME}
ShowDelay=0
DeviceTimeout=8
EOF

  cat << EOF > squashfs-root/usr/share/plymouth/plymouthd.defaults
[Daemon]
Theme=${PLYMOUTH_THEME}
ShowDelay=0
DeviceTimeout=8
UseSimpledrmNoLuks=1
EOF

  for theme_file in squashfs-root/usr/share/plymouth/themes/spinner/spinner.plymouth \
                    squashfs-root/usr/share/plymouth/themes/bgrt/bgrt.plymouth; do
    if [ -f "$theme_file" ]; then
      sed -i 's/BackgroundStartColor=.*/BackgroundStartColor=0x111111/' "$theme_file" || true
      sed -i 's/BackgroundEndColor=.*/BackgroundEndColor=0x111111/' "$theme_file" || true
      sed -i 's/UseProgressBar=true/UseProgressBar=false/' "$theme_file" || true
    fi
  done

  # Neutralize tribar fallback to text mode to prevent horizontal line flash
  if [ -f squashfs-root/usr/share/plymouth/themes/tribar/tribar.plymouth ]; then
    sed -i 's/ModuleName=tribar/ModuleName=text/' squashfs-root/usr/share/plymouth/themes/tribar/tribar.plymouth || true
  fi

  # Copy watermark to installer rootfs if available
  if [ -f "$BASE_DIR/files/system/usr/share/icons/hicolor/scalable/apps/sadeem-logo.svg" ] && command -v rsvg-convert >/dev/null 2>&1; then
    mkdir -p squashfs-root/usr/share/plymouth/themes/spinner 2>/dev/null || true
    rsvg-convert -w 128 -h 128 "$BASE_DIR/files/system/usr/share/icons/hicolor/scalable/apps/sadeem-logo.svg" -o squashfs-root/usr/share/plymouth/themes/spinner/watermark.png 2>/dev/null || true
  fi

  # --------------------------------------------------------------------------
  # 2. Decompress existing Cockpit .css.gz to allow clean modification
  # --------------------------------------------------------------------------
  if [ -d "squashfs-root/usr/share/cockpit" ]; then
    echo "Decompressing existing Cockpit .css.gz archives..."
    while IFS= read -r gz_file; do
      [ -f "$gz_file" ] && gunzip -k -f "$gz_file" 2>/dev/null || true
    done < <(find squashfs-root/usr/share/cockpit -type f -name "*.css.gz" 2>/dev/null || true)
  fi

  # Align anaconda and anaconda-webui directories if needed
  if [ -d "squashfs-root/usr/share/cockpit/anaconda" ] && [ ! -d "squashfs-root/usr/share/cockpit/anaconda-webui" ]; then
    ln -s anaconda squashfs-root/usr/share/cockpit/anaconda-webui || true
  elif [ -d "squashfs-root/usr/share/cockpit/anaconda-webui" ] && [ ! -d "squashfs-root/usr/share/cockpit/anaconda" ]; then
    ln -s anaconda-webui squashfs-root/usr/share/cockpit/anaconda || true
  elif [ ! -d "squashfs-root/usr/share/cockpit/anaconda-webui" ] && [ ! -d "squashfs-root/usr/share/cockpit/anaconda" ]; then
    mkdir -p squashfs-root/usr/share/cockpit/anaconda-webui
  fi

  # Ensure index.css exists in Cockpit Anaconda dirs
  for aw_dir in squashfs-root/usr/share/cockpit/anaconda-webui squashfs-root/usr/share/cockpit/anaconda; do
    if [ -d "$aw_dir" ] && [ ! -f "$aw_dir/index.css" ]; then
      touch "$aw_dir/index.css"
    fi
  done

  # --------------------------------------------------------------------------
  # 3. Anaconda WebUI PatternFly theme (strictly COLOR ONLY, NO layout/height)
  # --------------------------------------------------------------------------
  echo "--- 2. Appending color-only rules to Anaconda WebUI stylesheets ---"
  ANACONDA_COLOR_CSS='
/* Sadeem Burgundy PatternFly Theme */
:root, .pf-v6-theme-dark, .pf-v5-theme-dark, .pf-v6-theme-light, .pf-v5-theme-light {
  --pf-t--global--color--brand--default: #7a1c33 !important;
  --pf-t--global--color--brand--hover: #5c1426 !important;
  --pf-t--global--color--brand--clicked: #4a0f1e !important;
  --pf-v5-global--primary-color--100: #7a1c33 !important;
  --pf-v5-global--primary-color--200: #5c1426 !important;
  --pf-v5-global--link--Color: #7a1c33 !important;
}
.pf-v6-c-button.pf-m-primary, .pf-v5-c-button.pf-m-primary {
  background-color: #7a1c33 !important;
  border-color: #7a1c33 !important;
  color: #ffffff !important;
}
.pf-v6-c-button.pf-m-primary:hover, .pf-v5-c-button.pf-m-primary:hover {
  background-color: #5c1426 !important;
  border-color: #5c1426 !important;
  color: #ffffff !important;
}
.pf-v6-c-button.pf-m-primary:active, .pf-v5-c-button.pf-m-primary:active {
  background-color: #4a0f1e !important;
  border-color: #4a0f1e !important;
  color: #ffffff !important;
}
.pf-v5-c-progress__bar, .pf-v6-c-progress__bar, [class*="progress__bar"] {
  background-color: #7a1c33 !important;
}
.pf-v5-c-spinner, .pf-v6-c-spinner {
  stroke: #7a1c33 !important;
}
.pf-v5-c-nav__link.pf-m-current,
.pf-v6-c-nav__link.pf-m-current,
[class*="nav__link"][class*="current"],
.pf-v5-c-wizard__nav-link.pf-m-current,
.pf-v5-c-wizard__nav-item.pf-m-current > * {
  --pf-v5-c-nav__link--m-current--Color: #7a1c33 !important;
  border-left-color: #7a1c33 !important;
  color: #7a1c33 !important;
}
.pf-v5-c-radio__input:checked, .pf-v6-c-radio__input:checked,
.pf-v5-c-check__input:checked, .pf-v6-c-check__input:checked {
  border-color: #7a1c33 !important;
  background-color: #7a1c33 !important;
}
'

  for c_dir in squashfs-root/usr/share/cockpit/anaconda-webui \
               squashfs-root/usr/share/cockpit/anaconda \
               squashfs-root/usr/share/anaconda; do
    if [ -d "$c_dir" ]; then
      while IFS= read -r css_file; do
        if [ -f "$css_file" ] && ! grep -q "Sadeem Burgundy PatternFly Theme" "$css_file" 2>/dev/null; then
          echo "Patching Anaconda WebUI CSS: $css_file"
          echo "$ANACONDA_COLOR_CSS" >> "$css_file"
        fi
      done < <(find "$c_dir/" -type f -name "*.css" -not -name "userChrome.css" 2>/dev/null || true)
    fi
  done

  # --------------------------------------------------------------------------
  # 4. Cockpit Shell & Branding top bar
  # --------------------------------------------------------------------------
  echo "--- 3. Styling Cockpit Shell & Branding top bar ---"
  COCKPIT_TOPBAR_CSS='
/* Sadeem Burgundy Cockpit Top Bar */
#topnav {
  background-color: #7a1c33 !important;
  color: #ffffff !important;
}
#topnav * {
  color: #ffffff !important;
}
'
  for dir in squashfs-root/usr/share/cockpit/branding \
             squashfs-root/usr/share/cockpit/shell; do
    if [ -d "$dir" ]; then
      while IFS= read -r css_file; do
        if [ -f "$css_file" ]; then
          echo "Patching Cockpit shell CSS: $css_file"
          sed -i -E 's/#(0066cc|0088ce|06c|1e5692|294172|3c6eb4|0055aa|51a2da)/#7a1c33/gI' "$css_file" || true
          if ! grep -q "#topnav" "$css_file" 2>/dev/null; then
            echo "$COCKPIT_TOPBAR_CSS" >> "$css_file"
          fi
        fi
      done < <(find "$dir" -type f -name "*.css" 2>/dev/null || true)
    fi
  done

  # Recompress all modified Cockpit .css files to .css.gz
  echo "Rebuilding Cockpit .css.gz archives with gzip -kf..."
  if [ -d "squashfs-root/usr/share/cockpit" ]; then
    while IFS= read -r css_file; do
      if [ -f "$css_file" ]; then
        gzip -kf "$css_file" 2>/dev/null || true
      fi
    done < <(find squashfs-root/usr/share/cockpit -type f -name "*.css" 2>/dev/null || true)
  fi

  # --------------------------------------------------------------------------
  # 5. Firefox Kiosk userChrome.css and user.js
  # --------------------------------------------------------------------------
  echo "--- 4. Styling Firefox Kiosk theme for Anaconda WebUI ---"

  materialize_if_symlink() {
    local f="$1"
    local parent_dir
    parent_dir=$(dirname "$f")
    if [ -L "$parent_dir" ] && [ ! -d "$parent_dir" ]; then
      local ptarget
      ptarget=$(readlink "$parent_dir" || true)
      rm -f "$parent_dir"
      mkdir -p "$parent_dir"
      if [[ "$ptarget" == /* ]] && [ -d "squashfs-root${ptarget}" ]; then
        cp -a "squashfs-root${ptarget}/." "$parent_dir/" 2>/dev/null || true
      fi
    else
      mkdir -p "$parent_dir" 2>/dev/null || true
    fi

    if [ -L "$f" ]; then
      local target
      target=$(readlink "$f" || true)
      local resolved=""
      if [[ "$target" == /* ]]; then
        resolved="squashfs-root${target}"
      elif [ -n "$target" ]; then
        resolved="${parent_dir}/${target}"
      fi
      echo "Materializing symlink $f -> $target (resolved: $resolved)"
      local tmp_copy=""
      if [ -n "$resolved" ] && [ -f "$resolved" ]; then
        tmp_copy=$(mktemp)
        cp -L "$resolved" "$tmp_copy" 2>/dev/null || cp "$resolved" "$tmp_copy" 2>/dev/null || true
      fi
      rm -f "$f"
      if [ -n "$tmp_copy" ] && [ -f "$tmp_copy" ]; then
        mv -f "$tmp_copy" "$f"
      else
        touch "$f"
      fi
    elif [ ! -f "$f" ]; then
      touch "$f"
    fi
    chmod 0644 "$f" 2>/dev/null || true
  }

  FIREFOX_TOPBAR_CSS='
/* Sadeem Firefox Top Bar */
:root, #navigator-toolbox, #titlebar, #TabsToolbar, #nav-bar, .titlebar-color, toolbar {
  background-color: #7a1c33 !important;
  background-image: none !important;
  color: #ffffff !important;
}
'

  # Explicitly materialize and patch live and default userChrome.css
  UC_TARGETS=(
    "squashfs-root/usr/share/anaconda/firefox-theme/live/chrome/userChrome.css"
    "squashfs-root/usr/share/anaconda/firefox-theme/default/chrome/userChrome.css"
  )
  while IFS= read -r extra_uc; do
    if [ -n "$extra_uc" ]; then
      UC_TARGETS+=("$extra_uc")
    fi
  done < <(find squashfs-root/usr/share/anaconda \( -type f -o -type l \) -name "userChrome.css" 2>/dev/null || true)

  for uc_file in "${UC_TARGETS[@]}"; do
    materialize_if_symlink "$uc_file"
    if [ -f "$uc_file" ]; then
      echo "Patching Firefox userChrome.css: $uc_file"
      sed -i -E 's/#(294172|3c6eb4|0066cc|0055aa|51a2da|0088ce|06c)/#7a1c33/gI' "$uc_file" || true
      sed -i -E 's/rgb\(\s*(41\s*,\s*65\s*,\s*114|60\s*,\s*110\s*,\s*180|0\s*,\s*102\s*,\s*204)\s*\)/#7a1c33/gI' "$uc_file" || true
      if ! grep -q "Sadeem Firefox Top Bar" "$uc_file" 2>/dev/null; then
        echo "$FIREFOX_TOPBAR_CSS" >> "$uc_file"
      fi
    fi
  done

  # Enable userChrome.css in Firefox preferences
  echo "Enabling toolkit.legacyUserProfileCustomizations.stylesheets..."
  while IFS= read -r pref_file; do
    materialize_if_symlink "$pref_file"
    if [ -f "$pref_file" ]; then
      if grep -q "toolkit.legacyUserProfileCustomizations.stylesheets" "$pref_file"; then
        sed -i 's/user_pref("toolkit.legacyUserProfileCustomizations.stylesheets",.*/user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);/' "$pref_file" || true
      else
        echo 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' >> "$pref_file"
      fi
    fi
  done < <(find squashfs-root/usr/share/anaconda squashfs-root/etc \( -type f -o -type l \) \( -name "user.js" -o -name "prefs.js" \) 2>/dev/null || true)

  for pdir in squashfs-root/usr/share/anaconda/firefox-theme/live squashfs-root/usr/share/anaconda/firefox-theme/default; do
    if [ -d "$pdir" ]; then
      materialize_if_symlink "$pdir/user.js"
      if ! grep -q "toolkit.legacyUserProfileCustomizations.stylesheets" "$pdir/user.js"; then
        echo 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' >> "$pdir/user.js"
      fi
    fi
  done

  for fdir in squashfs-root/usr/lib64/firefox/defaults/pref squashfs-root/usr/lib/firefox/defaults/pref squashfs-root/etc/firefox/pref; do
    if [ -d "$fdir" ]; then
      echo 'pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' >> "$fdir/all-sadeem.js" || true
    fi
  done

  # --------------------------------------------------------------------------
  # 6. Update product configuration & os-release
  # --------------------------------------------------------------------------
  echo "--- 5. Updating product configuration to Sadeem 45 ---"
  mkdir -p squashfs-root/etc/anaconda/product.d 2>/dev/null || true
  for conf in squashfs-root/etc/anaconda/product.d/*.conf squashfs-root/etc/anaconda/product.conf squashfs-root/usr/share/anaconda/product.d/*.conf; do
    if [ -f "$conf" ]; then
      sed -i 's|product_name = .*|product_name = Sadeem 45|g' "$conf" || true
    fi
  done
  echo -e "[Product]\nproduct_name = Sadeem 45" > squashfs-root/etc/anaconda/product.d/sadeem.conf || true

  for osrel in squashfs-root/usr/lib/os-release squashfs-root/etc/os-release; do
    if [ -f "$osrel" ]; then
      sed -i 's|^NAME=.*|NAME="Sadeem"|' "$osrel" || true
      sed -i 's|^PRETTY_NAME=.*|PRETTY_NAME="Sadeem 45"|' "$osrel" || true
    fi
  done

  # --------------------------------------------------------------------------
  # 7. Mandatory Automated CI Verification Gate
  # --------------------------------------------------------------------------
  echo "=================================================="
  echo "Running CI Automated Verification Gate before mksquashfs"
  echo "=================================================="

  GATE_FAILED=0

  # Check 1: #7a1c33 inside zcat squashfs-root/usr/share/cockpit/anaconda-webui/index.css.gz (or any index.css.gz in cockpit/anaconda*)
  INDEX_GZ=""
  if [ -f "squashfs-root/usr/share/cockpit/anaconda-webui/index.css.gz" ]; then
    INDEX_GZ="squashfs-root/usr/share/cockpit/anaconda-webui/index.css.gz"
  else
    INDEX_GZ=$(find squashfs-root/usr/share/cockpit -type f -name "index.css.gz" 2>/dev/null | grep "anaconda" | head -n 1 || true)
    if [ -z "$INDEX_GZ" ]; then
      INDEX_GZ=$(find squashfs-root/usr/share/cockpit -type f -name "index.css.gz" 2>/dev/null | head -n 1 || true)
    fi
  fi

  if [ -n "$INDEX_GZ" ] && [ -f "$INDEX_GZ" ]; then
    if gzip -dc "$INDEX_GZ" | grep -q "#7a1c33"; then
      echo "[PASS] Gate Check 1: #7a1c33 found in $INDEX_GZ"
    else
      echo "[FAIL] Gate Check 1: #7a1c33 NOT found in $INDEX_GZ"
      GATE_FAILED=1
    fi
  else
    echo "[FAIL] Gate Check 1: index.css.gz not found in Cockpit Anaconda"
    GATE_FAILED=1
  fi

  # Check 2: #7a1c33 inside squashfs-root/usr/share/anaconda/firefox-theme/live/chrome/userChrome.css
  FIREFOX_UC="squashfs-root/usr/share/anaconda/firefox-theme/live/chrome/userChrome.css"
  if [ -f "$FIREFOX_UC" ] && grep -q "#7a1c33" "$FIREFOX_UC"; then
    echo "[PASS] Gate Check 2: #7a1c33 found in $FIREFOX_UC"
  else
    echo "[FAIL] Gate Check 2: #7a1c33 NOT found in $FIREFOX_UC"
    GATE_FAILED=1
  fi

  # Check 3: Theme= in squashfs-root/etc/plymouth/plymouthd.conf matches (bgrt|spinner|details)
  PLYMOUTH_CFG="squashfs-root/etc/plymouth/plymouthd.conf"
  if [ -f "$PLYMOUTH_CFG" ] && grep -qE '^Theme=(bgrt|spinner|details)$' "$PLYMOUTH_CFG"; then
    MATCHED_THEME=$(grep -E '^Theme=' "$PLYMOUTH_CFG")
    echo "[PASS] Gate Check 3: Plymouth theme valid ($MATCHED_THEME in $PLYMOUTH_CFG)"
  else
    echo "[FAIL] Gate Check 3: Plymouth theme in $PLYMOUTH_CFG missing or invalid"
    [ -f "$PLYMOUTH_CFG" ] && cat "$PLYMOUTH_CFG"
    GATE_FAILED=1
  fi

  # Check 4: Newly added CSS modifications contain no 'height:' or 'position: fixed'
  FORBIDDEN_CSS=0
  while IFS= read -r css; do
    if [ -f "$css" ] && grep -q "#7a1c33" "$css" 2>/dev/null; then
      SADEEM_CHUNK=$(awk '/\/\* Sadeem/{flag=1} flag' "$css" 2>/dev/null || true)
      if echo "$SADEEM_CHUNK" | grep -Ei "(height\s*:|position\s*:\s*fixed)" >/dev/null; then
        echo "[FAIL] Gate Check 4: Forbidden CSS property found in $css:"
        echo "$SADEEM_CHUNK" | grep -Ei "(height\s*:|position\s*:\s*fixed)"
        FORBIDDEN_CSS=1
        GATE_FAILED=1
      fi
    fi
  done < <(find squashfs-root/usr/share/cockpit squashfs-root/usr/share/anaconda -type f -name "*.css" 2>/dev/null || true)

  if [ "$FORBIDDEN_CSS" -eq 0 ]; then
    echo "[PASS] Gate Check 4: No 'height:' or 'position: fixed' found in newly added CSS rules"
  fi

  if [ "$GATE_FAILED" -ne 0 ]; then
    echo "=================================================="
    echo "ERROR: Automated verification gate failed! Aborting build."
    echo "=================================================="
    exit 1
  fi

  echo "=================================================="
  echo "All 4 CI verification gate checks passed successfully!"
  echo "=================================================="

  # --------------------------------------------------------------------------
  # 8. Re-compress squashfs and inject back into ISO
  # --------------------------------------------------------------------------
  rm -f "$IMG_NAME"
  echo "Re-compressing $IMG_NAME with xz..."
  mksquashfs squashfs-root "$IMG_NAME" -comp xz -noappend

  # Immediately delete uncompressed rootfs to conserve disk space
  rm -rf squashfs-root

  # Configure boot options in EFI/BOOT/grub.cfg if present
  GRUB_UPDATED=false
  if xorriso -osirrox on -indev "$ISO_ABS" -extract /EFI/BOOT/grub.cfg ./grub.cfg 2>/dev/null && [ -f ./grub.cfg ]; then
    echo "Found EFI/BOOT/grub.cfg in ISO, configuring boot options..."
    if ! grep -q "plymouth.enable=0" ./grub.cfg 2>/dev/null; then
      sed -i 's|inst.stage2=[^ ]*|& rd.plymouth=0 plymouth.enable=0|g' ./grub.cfg || true
      GRUB_UPDATED=true
    fi
  fi

  # Configure boot options in isolinux/isolinux.cfg if present
  ISOLINUX_UPDATED=false
  if xorriso -osirrox on -indev "$ISO_ABS" -extract /isolinux/isolinux.cfg ./isolinux.cfg 2>/dev/null && [ -f ./isolinux.cfg ]; then
    echo "Found isolinux/isolinux.cfg in ISO, configuring boot options..."
    if ! grep -q "plymouth.enable=0" ./isolinux.cfg 2>/dev/null; then
      sed -i 's|inst.stage2=[^ ]*|& rd.plymouth=0 plymouth.enable=0|g' ./isolinux.cfg || true
      ISOLINUX_UPDATED=true
    fi
  fi

  # Inject back into ISO using xorriso preserving bootloader & partition configuration
  echo "Injecting updated $TARGET_PATH back into $ISO_ABS..."
  UPDATE_ARGS=("-update" "$IMG_NAME" "$TARGET_PATH")
  if [ "$GRUB_UPDATED" = "true" ] && [ -f "./grub.cfg" ]; then
    UPDATE_ARGS+=("-update" "./grub.cfg" "/EFI/BOOT/grub.cfg")
  fi
  if [ "$ISOLINUX_UPDATED" = "true" ] && [ -f "./isolinux.cfg" ]; then
    UPDATE_ARGS+=("-update" "./isolinux.cfg" "/isolinux/isolinux.cfg")
  fi

  xorriso -indev "$ISO_ABS" \
          -outdev "${ISO_ABS}.tmp" \
          -boot_image any keep \
          "${UPDATE_ARGS[@]}"

  # Immediately remove temporary files
  rm -f "$IMG_NAME" ./grub.cfg ./isolinux.cfg 2>/dev/null || true

  mv -f "${ISO_ABS}.tmp" "$ISO_ABS"
  echo "ISO installer branding customization completed successfully!"
else
  echo "Notice: No installer squashfs image found in $ISO_FILE; leaving ISO as-is."
fi

# Explicitly cleanup WORK_DIR before exiting
cd "$BASE_DIR"
rm -rf "$WORK_DIR"
trap - EXIT
