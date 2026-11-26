#!/usr/bin/env bash
# ==============================================================================
# Sadeem OS - Automated External Applications Installer
# Fetches and installs the latest releases of bundled third-party applications
# directly from GitHub Releases API during image build, with resilient python3
# API resolution and static fallbacks for rate-limited environments.
# ==============================================================================

set -euo pipefail

TARGET_ROOT="${1:-/}"
TMP_WORK_DIR=$(mktemp -d /tmp/sadeem-ext-apps-XXXXXX)

cleanup() {
    rm -rf "$TMP_WORK_DIR"
}
trap cleanup EXIT

# ------------------------------------------------------------------------------
# Function: resolve_release_asset
# Uses Python 3 to query GitHub API for latest release, falls back to /releases
# if 404, and automatically returns fallback_url on rate limit / network error.
# ------------------------------------------------------------------------------
resolve_release_asset() {
    local repo="$1"
    local pattern="$2"
    local fallback_url="$3"

    python3 - "$repo" "$pattern" "$fallback_url" << 'PYEOF'
import sys
import os
import json
import re
import urllib.request
import urllib.error

repo = sys.argv[1]
pattern = sys.argv[2]
fallback_url = sys.argv[3]

headers = {
    'User-Agent': 'sadeem-builder',
    'Accept': 'application/vnd.github+json',
}
token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
if token:
    headers['Authorization'] = f'Bearer {token}'

endpoints = [
    f"https://api.github.com/repos/{repo}/releases/latest",
    f"https://api.github.com/repos/{repo}/releases"
]

found_url = None
found_tag = None

for url in endpoints:
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace'))
            releases = data if isinstance(data, list) else [data]
            for release in releases:
                if not isinstance(release, dict):
                    continue
                tag = release.get('tag_name', 'unknown')
                for asset in release.get('assets', []):
                    name = asset.get('name', '')
                    if re.search(pattern, name, re.IGNORECASE):
                        download_url = asset.get('browser_download_url')
                        if download_url:
                            found_url = download_url
                            found_tag = tag
                            break
                if found_url:
                    break
        if found_url:
            break
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"WARNING: GitHub API returned HTTP {e.code} for {url}: {e.reason}\n")
    except Exception as e:
        sys.stderr.write(f"WARNING: Failed to query {url}: {e}\n")

if found_url:
    sys.stderr.write(f"==> Resolved {repo} ({found_tag}): {found_url}\n")
    print(found_url)
else:
    sys.stderr.write(f"WARNING: Using fallback URL for {repo}: {fallback_url}\n")
    print(fallback_url)
PYEOF
}

# ------------------------------------------------------------------------------
# Function: download_and_verify_archive
# Downloads archive with curl, checks validity, and retries with fallback if needed.
# ------------------------------------------------------------------------------
download_and_verify_archive() {
    local url="$1"
    local fallback_url="$2"
    local dest_file="$3"

    echo "==> Downloading archive from ${url}..." >&2
    if ! curl -fSL --retry 3 --retry-delay 2 -H "User-Agent: sadeem-builder" -o "$dest_file" "$url" || [[ ! -s "$dest_file" ]]; then
        if [[ "$url" != "$fallback_url" ]]; then
            echo "WARNING: Download failed or empty from ${url}. Retrying with fallback: ${fallback_url}..." >&2
            rm -f "$dest_file"
            if ! curl -fSL --retry 3 --retry-delay 2 -H "User-Agent: sadeem-builder" -o "$dest_file" "$fallback_url" || [[ ! -s "$dest_file" ]]; then
                echo "ERROR: Fallback download also failed from ${fallback_url}" >&2
                return 1
            fi
        else
            echo "ERROR: Failed to download from ${url}" >&2
            return 1
        fi
    fi

    if ! tar -tzf "$dest_file" >/dev/null 2>&1; then
        if [[ "$url" != "$fallback_url" ]]; then
            echo "WARNING: Downloaded archive from ${url} is invalid. Retrying with fallback: ${fallback_url}..." >&2
            rm -f "$dest_file"
            if ! curl -fSL --retry 3 --retry-delay 2 -H "User-Agent: sadeem-builder" -o "$dest_file" "$fallback_url" || [[ ! -s "$dest_file" ]] || ! tar -tzf "$dest_file" >/dev/null 2>&1; then
                echo "ERROR: Fallback archive also invalid from ${fallback_url}" >&2
                return 1
            fi
        else
            echo "ERROR: Archive is invalid or corrupted." >&2
            return 1
        fi
    fi

    return 0
}

# ------------------------------------------------------------------------------
# 1. Install ZapFast (Native WhatsApp Client)
# Repository: crmne/zapfast
# ------------------------------------------------------------------------------
echo "=========================================================="
echo "Installing ZapFast (crmne/zapfast)..."
echo "=========================================================="

ZAPFAST_FALLBACK="https://github.com/crmne/zapfast/releases/download/v0.21.3/zapfast-v0.21.3-x86_64-unknown-linux-gnu.tar.gz"
ZAPFAST_ARCHIVE="${TMP_WORK_DIR}/zapfast.tar.gz"
ZAPFAST_EXTRACT="${TMP_WORK_DIR}/zapfast_extracted"
mkdir -p "$ZAPFAST_EXTRACT"

ZAPFAST_URL=$(resolve_release_asset "crmne/zapfast" "x86_64.*linux.*\.tar\.gz$" "$ZAPFAST_FALLBACK")
download_and_verify_archive "$ZAPFAST_URL" "$ZAPFAST_FALLBACK" "$ZAPFAST_ARCHIVE"

echo "==> Extracting ZapFast..."
tar -xzf "$ZAPFAST_ARCHIVE" -C "$ZAPFAST_EXTRACT"

ZAPFAST_BIN=$(find "$ZAPFAST_EXTRACT" -type f -name "zapfast" | head -n 1)
if [[ -z "$ZAPFAST_BIN" ]] || [[ ! -f "$ZAPFAST_BIN" ]]; then
    echo "ERROR: zapfast binary not found in extracted archive." >&2
    exit 1
fi

mkdir -p "${TARGET_ROOT}/usr/share/zapfast/omarchy"
mkdir -p "${TARGET_ROOT}/usr/bin"
mkdir -p "${TARGET_ROOT}/usr/share/applications"
mkdir -p "${TARGET_ROOT}/usr/share/icons/hicolor/scalable/apps"

install -m 755 "$ZAPFAST_BIN" "${TARGET_ROOT}/usr/share/zapfast/zapfast"

# Ensure /usr/bin/zapfast runner exists
cat << 'RUNNER' > "${TARGET_ROOT}/usr/bin/zapfast"
#!/usr/bin/bash
exec /usr/share/zapfast/zapfast "$@"
RUNNER
chmod 755 "${TARGET_ROOT}/usr/bin/zapfast"

# Copy omarchy themes if present
find "$ZAPFAST_EXTRACT" -path "*/contrib/omarchy/*" -type f -exec cp -f {} "${TARGET_ROOT}/usr/share/zapfast/omarchy/" \; 2>/dev/null || true

# Copy scalable icon if present
ZAPFAST_SVG=$(find "$ZAPFAST_EXTRACT" -name "zapfast.svg" | head -n 1)
if [[ -n "$ZAPFAST_SVG" ]] && [[ -f "$ZAPFAST_SVG" ]]; then
    cp -f "$ZAPFAST_SVG" "${TARGET_ROOT}/usr/share/icons/hicolor/scalable/apps/zapfast.svg"
fi

echo "==> ZapFast installed successfully."

# ------------------------------------------------------------------------------
# 2. Install Mister Download Manager (MDM)
# Repository: anefzaoui/misterdownloadmanager
# ------------------------------------------------------------------------------
echo "=========================================================="
echo "Installing Mister Download Manager (anefzaoui/misterdownloadmanager)..."
echo "=========================================================="

MDM_FALLBACK="https://github.com/anefzaoui/misterdownloadmanager/releases/download/v0.5.2/MisterDownloadManager-0.5.2-linux-x86_64.tar.gz"
MDM_ARCHIVE="${TMP_WORK_DIR}/mdm.tar.gz"
MDM_EXTRACT="${TMP_WORK_DIR}/mdm_extracted"
mkdir -p "$MDM_EXTRACT"

MDM_URL=$(resolve_release_asset "anefzaoui/misterdownloadmanager" ".*linux.*x86_64.*\.tar\.gz$" "$MDM_FALLBACK")
download_and_verify_archive "$MDM_URL" "$MDM_FALLBACK" "$MDM_ARCHIVE"

echo "==> Extracting Mister Download Manager..."
tar -xzf "$MDM_ARCHIVE" -C "$MDM_EXTRACT"

mkdir -p "${TARGET_ROOT}/usr/bin"
mkdir -p "${TARGET_ROOT}/usr/share/misterdownloadmanager"
mkdir -p "${TARGET_ROOT}/usr/lib64/firefox/browser/extensions"

for b in misterdownloadmanager misterdownloadmanager-cli misterdownloadmanager-mcp misterdownloadmanager-nmhost; do
    BIN_PATH=$(find "$MDM_EXTRACT" -type f -name "$b" | head -n 1)
    if [[ -z "$BIN_PATH" ]] || [[ ! -f "$BIN_PATH" ]]; then
        echo "ERROR: Binary '$b' not found in MDM extracted archive." >&2
        exit 1
    fi
    install -m 755 "$BIN_PATH" "${TARGET_ROOT}/usr/bin/$b"
done

# Install Firefox Extension XPI (system + Flatpak Firefox skel)
MDM_XPI=$(find "$MDM_EXTRACT" -type f -name "mdm-firefox.xpi" | head -n 1)
if [[ -n "$MDM_XPI" ]] && [[ -f "$MDM_XPI" ]]; then
    SKEL_FF_EXT_DIR="${TARGET_ROOT}/etc/skel/.var/app/org.mozilla.firefox/.mozilla/extensions/{ec8030f7-c20a-464f-9b0e-13a3a9e97384}"
    mkdir -p "$SKEL_FF_EXT_DIR"
    cp -f "$MDM_XPI" "${TARGET_ROOT}/usr/share/misterdownloadmanager/mdm-firefox.xpi"
    cp -f "$MDM_XPI" "${TARGET_ROOT}/usr/lib64/firefox/browser/extensions/integration@misterdownloadmanager.com.xpi"
    cp -f "$MDM_XPI" "${SKEL_FF_EXT_DIR}/integration@misterdownloadmanager.com.xpi"
fi

# Install Chromium extension files
MDM_EXT_DIR=$(find "$MDM_EXTRACT" -type d -name "extension-chromium" | head -n 1)
if [[ -n "$MDM_EXT_DIR" ]] && [[ -d "$MDM_EXT_DIR" ]]; then
    rm -rf "${TARGET_ROOT}/usr/share/misterdownloadmanager/extension-chromium"
    cp -rf "$MDM_EXT_DIR" "${TARGET_ROOT}/usr/share/misterdownloadmanager/"
fi

echo "==> Mister Download Manager installed successfully."

echo "=========================================================="
echo "All external applications fetched and installed successfully!"
echo "=========================================================="
