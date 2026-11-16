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
echo "Customizing Anaconda WebUI & Branding in: $ISO_ABS"
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

  CSS_FILE="$BASE_DIR/files/system/usr/share/sadeem/anaconda-burgundy.css"
  if [ -f "$CSS_FILE" ]; then
    echo "Applying Sadeem burgundy CSS theme to installer WebUI..."
    mkdir -p squashfs-root/usr/share/sadeem
    cp -f "$CSS_FILE" squashfs-root/usr/share/sadeem/anaconda-burgundy.css

    find squashfs-root/usr/share/cockpit squashfs-root/usr/share/anaconda -type f -name "*.css" 2>/dev/null | while read -r f; do
      echo "Patching stylesheet: $f"
      echo -e "\n/* Sadeem Burgundy Theme */\n" >> "$f"
      cat "$CSS_FILE" >> "$f"
    done

    find squashfs-root/usr/share/cockpit squashfs-root/usr/share/anaconda -type f -name "*.html" 2>/dev/null | while read -r h; do
      if ! grep -q "anaconda-burgundy.css" "$h"; then
        sed -i 's|</head>|<link rel="stylesheet" href="/usr/share/sadeem/anaconda-burgundy.css">\n</head>|' "$h" || true
      fi
    done
  fi

  # Update product configuration
  echo "Updating product configuration to Sadeem 45..."
  mkdir -p squashfs-root/etc/anaconda/product.d
  for conf in squashfs-root/etc/anaconda/product.d/*.conf squashfs-root/etc/anaconda/product.conf squashfs-root/usr/share/anaconda/product.d/*.conf; do
    if [ -f "$conf" ]; then
      sed -i 's|product_name = .*|product_name = Sadeem 45|g' "$conf"
    fi
  done
  echo -e "[Product]\nproduct_name = Sadeem 45" > squashfs-root/etc/anaconda/product.d/sadeem.conf

  # Update os-release inside installer rootfs
  for osrel in squashfs-root/usr/lib/os-release squashfs-root/etc/os-release; do
    if [ -f "$osrel" ]; then
      sed -i 's|^NAME=.*|NAME="Sadeem"|' "$osrel"
      sed -i 's|^PRETTY_NAME=.*|PRETTY_NAME="Sadeem 45"|' "$osrel"
    fi
  done

  # Rebuild squashfs image
  rm -f "$IMG_NAME"
  echo "Re-compressing $IMG_NAME with xz..."
  mksquashfs squashfs-root "$IMG_NAME" -comp xz -noappend

  # Immediately delete uncompressed rootfs to conserve disk space
  rm -rf squashfs-root

  # Inject back into ISO using xorriso preserving bootloader & partition configuration
  echo "Injecting updated $TARGET_PATH back into $ISO_ABS..."
  xorriso -indev "$ISO_ABS" \
          -outdev "${ISO_ABS}.tmp" \
          -boot_image any keep \
          -update "$IMG_NAME" "$TARGET_PATH"

  # Immediately remove compressed image from temp directory
  rm -f "$IMG_NAME"

  mv -f "${ISO_ABS}.tmp" "$ISO_ABS"
  echo "ISO installer branding customization completed successfully!"
else
  echo "Notice: No installer squashfs image found in $ISO_FILE; leaving ISO as-is."
fi

# Explicitly cleanup WORK_DIR before exiting
cd "$BASE_DIR"
rm -rf "$WORK_DIR"
trap - EXIT
