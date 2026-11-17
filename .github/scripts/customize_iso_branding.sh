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

  CSS_ANACONDA="$BASE_DIR/files/system/usr/share/sadeem/anaconda-burgundy.css"
  CSS_COCKPIT="$BASE_DIR/files/system/usr/share/sadeem/cockpit-branding.css"

  if [ -f "$CSS_ANACONDA" ]; then
    echo "Applying Sadeem burgundy CSS theme..."
    mkdir -p squashfs-root/usr/share/sadeem 2>/dev/null || true
    cp -f "$CSS_ANACONDA" squashfs-root/usr/share/sadeem/anaconda-burgundy.css || true
    [ -f "$CSS_COCKPIT" ] && cp -f "$CSS_COCKPIT" squashfs-root/usr/share/sadeem/cockpit-branding.css || true

    # 1. Target Cockpit Shell branding stylesheets (top navigation bar: #topnav, .cockpit-header, .pf-v5-c-page__header)
    for f in squashfs-root/usr/share/cockpit/branding/fedora/branding.css \
             squashfs-root/usr/share/cockpit/branding/*/*.css \
             squashfs-root/usr/share/cockpit/shell/shell.css \
             squashfs-root/usr/share/cockpit/shell/*.css; do
      if [ -f "$f" ]; then
        echo "Patching Cockpit shell stylesheet: $f"
        echo -e "\n/* Sadeem Burgundy Cockpit Top Bar */\n" >> "$f" || true
        if [ -f "$CSS_COCKPIT" ]; then
          cat "$CSS_COCKPIT" >> "$f" || true
        else
          cat << 'EOF' >> "$f"
#topnav, .cockpit-header, .pf-v5-c-page__header {
  background-color: #7a1c33 !important;
  background: #7a1c33 !important;
  color: #ffffff !important;
  border-bottom: none !important;
  margin: 0 !important;
  height: auto !important;
}
#topnav *, .cockpit-header *, .pf-v5-c-page__header * {
  color: #ffffff !important;
}
EOF
        fi
      fi
    done

    # 2. Target Anaconda WebUI stylesheets (PatternFly variables, buttons, progress bar - without overlapping header)
    ANACONDA_DIRS=()
    [ -d squashfs-root/usr/share/cockpit/anaconda ] && ANACONDA_DIRS+=(squashfs-root/usr/share/cockpit/anaconda)
    [ -d squashfs-root/usr/share/anaconda ] && ANACONDA_DIRS+=(squashfs-root/usr/share/anaconda)

    if [ ${#ANACONDA_DIRS[@]} -gt 0 ]; then
      find "${ANACONDA_DIRS[@]}" -type f -name "*.css" 2>/dev/null | while read -r f; do
        if [ -f "$f" ]; then
          echo "Patching Anaconda WebUI stylesheet: $f"
          echo -e "\n/* Sadeem Burgundy Theme */\n" >> "$f" || true
          cat "$CSS_ANACONDA" >> "$f" || true
        fi
      done || true

      find "${ANACONDA_DIRS[@]}" -type f -name "*.html" 2>/dev/null | while read -r h; do
        if [ -f "$h" ]; then
          if ! grep -q "anaconda-burgundy.css" "$h" 2>/dev/null; then
            sed -i 's|</head>|<link rel="stylesheet" href="/usr/share/sadeem/anaconda-burgundy.css">\n</head>|' "$h" || true
          fi
        fi
      done || true
    fi
  fi

  # Configure Plymouth theme safely via config files without running dracut or plymouth-set-default-theme inside rootfs
  echo "Configuring Plymouth theme in installer rootfs..."
  mkdir -p squashfs-root/etc/plymouth squashfs-root/usr/share/plymouth/themes/spinner 2>/dev/null || true
  cat << 'EOF' > squashfs-root/etc/plymouth/plymouthd.conf
[Daemon]
Theme=spinner
ShowDelay=0
DeviceTimeout=8
EOF
  cat << 'EOF' > squashfs-root/usr/share/plymouth/plymouthd.defaults
[Daemon]
Theme=spinner
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

  # Neutralize tribar fallback in installer rootfs to eliminate horizontal bar
  if [ -f squashfs-root/usr/share/plymouth/themes/tribar/tribar.plymouth ]; then
    sed -i 's/ModuleName=tribar/ModuleName=text/' squashfs-root/usr/share/plymouth/themes/tribar/tribar.plymouth || true
  fi

  # Copy watermark to installer rootfs if available
  if [ -f "$BASE_DIR/files/system/usr/share/icons/hicolor/scalable/apps/sadeem-logo.svg" ] && command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 128 -h 128 "$BASE_DIR/files/system/usr/share/icons/hicolor/scalable/apps/sadeem-logo.svg" -o squashfs-root/usr/share/plymouth/themes/spinner/watermark.png 2>/dev/null || true
  fi

  # Update product configuration
  echo "Updating product configuration to Sadeem 45..."
  mkdir -p squashfs-root/etc/anaconda/product.d 2>/dev/null || true
  for conf in squashfs-root/etc/anaconda/product.d/*.conf squashfs-root/etc/anaconda/product.conf squashfs-root/usr/share/anaconda/product.d/*.conf; do
    if [ -f "$conf" ]; then
      sed -i 's|product_name = .*|product_name = Sadeem 45|g' "$conf" || true
    fi
  done
  echo -e "[Product]\nproduct_name = Sadeem 45" > squashfs-root/etc/anaconda/product.d/sadeem.conf || true

  # Update os-release inside installer rootfs
  for osrel in squashfs-root/usr/lib/os-release squashfs-root/etc/os-release; do
    if [ -f "$osrel" ]; then
      sed -i 's|^NAME=.*|NAME="Sadeem"|' "$osrel" || true
      sed -i 's|^PRETTY_NAME=.*|PRETTY_NAME="Sadeem 45"|' "$osrel" || true
    fi
  done

  # Rebuild squashfs image
  rm -f "$IMG_NAME"
  echo "Re-compressing $IMG_NAME with xz..."
  mksquashfs squashfs-root "$IMG_NAME" -comp xz -noappend

  # Immediately delete uncompressed rootfs to conserve disk space
  rm -rf squashfs-root

  # Check if EFI/BOOT/grub.cfg exists in ISO and ensure quiet and disable plymouth flicker during boot
  GRUB_UPDATED=false
  if xorriso -osirrox on -indev "$ISO_ABS" -extract /EFI/BOOT/grub.cfg ./grub.cfg 2>/dev/null && [ -f ./grub.cfg ]; then
    echo "Found EFI/BOOT/grub.cfg in ISO, configuring boot options..."
    if ! grep -q "plymouth.enable=0" ./grub.cfg 2>/dev/null; then
      sed -i 's|inst.stage2=[^ ]*|& rd.plymouth=0 plymouth.enable=0|g' ./grub.cfg || true
      GRUB_UPDATED=true
    fi
  fi

  # Check if isolinux/isolinux.cfg exists in ISO
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
