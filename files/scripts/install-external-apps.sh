#!/usr/bin/env bash
# ==============================================================================
# Sadeem OS - Automated External Applications Installer
# Fetches and installs the latest releases of bundled third-party applications
# directly from GitHub Releases API during image build.
# ==============================================================================

set -euo pipefail

TARGET_ROOT="${1:-/}"
TMP_WORK_DIR=$(mktemp -d /tmp/sadeem-ext-apps-XXXXXX)

cleanup() {
    rm -rf "$TMP_WORK_DIR"
}
trap cleanup EXIT

# Configure curl authentication header if GitHub token is present in the environment
CURL_AUTH_ARGS=()
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    CURL_AUTH_ARGS=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
elif [[ -n "${GH_TOKEN:-}" ]]; then
    CURL_AUTH_ARGS=(-H "Authorization: Bearer ${GH_TOKEN}")
fi

USER_AGENT="Sadeem-OS-Build/1.0 (https://github.com/saifdiv432/sadeem)"

# Function: fetch_latest_github_release
# Arguments:
#   $1: GitHub repo (owner/repo)
#   $2: Asset regex pattern (e.g. "x86_64.*linux.*\.tar\.gz$")
#   $3: Output archive path
# Outputs:
#   Echoes detected tag name
fetch_latest_github_release() {
    local repo="$1"
    local pattern="$2"
    local output_file="$3"

    echo "==> Querying latest release for ${repo} via GitHub API..." >&2
    local api_url="https://api.github.com/repos/${repo}/releases/latest"

    local release_json
    if ! release_json=$(curl -fsSL -H "User-Agent: ${USER_AGENT}" "${CURL_AUTH_ARGS[@]}" "${api_url}" 2>/dev/null); then
        echo "ERROR: Failed to connect or fetch release metadata from ${api_url}" >&2
        exit 1
    fi

    if [[ -z "$release_json" ]] || [[ "$release_json" == "null" ]]; then
        echo "ERROR: Empty release metadata received for ${repo} from ${api_url}" >&2
        exit 1
    fi

    local tag_name
    tag_name=$(echo "$release_json" | jq -r '.tag_name // empty')
    if [[ -z "$tag_name" ]]; then
        echo "ERROR: Could not parse tag_name for ${repo}." >&2
        exit 1
    fi

    local download_url
    download_url=$(echo "$release_json" | jq -r --arg pat "$pattern" '[.assets[] | select(.name | test($pat))] | first | .browser_download_url // empty')
    if [[ -z "$download_url" ]]; then
        echo "ERROR: Could not find asset matching '${pattern}' in release ${tag_name} for ${repo}." >&2
        exit 1
    fi

    echo "==> Downloading ${repo} (${tag_name}) from ${download_url}..." >&2
    if ! curl -fsSL -H "User-Agent: ${USER_AGENT}" "${CURL_AUTH_ARGS[@]}" -o "$output_file" "$download_url"; then
        echo "ERROR: Failed to download asset from ${download_url}" >&2
        exit 1
    fi

    if [[ ! -s "$output_file" ]]; then
        echo "ERROR: Downloaded file for ${repo} is missing or empty." >&2
        exit 1
    fi

    echo "$tag_name"
}

# ------------------------------------------------------------------------------
# 1. Install ZapFast (Native WhatsApp Client)
# Repository: crmne/zapfast
# ------------------------------------------------------------------------------
echo "=========================================================="
echo "Installing ZapFast (crmne/zapfast)..."
echo "=========================================================="

ZAPFAST_ARCHIVE="${TMP_WORK_DIR}/zapfast.tar.gz"
ZAPFAST_EXTRACT="${TMP_WORK_DIR}/zapfast_extracted"
mkdir -p "$ZAPFAST_EXTRACT"

ZAPFAST_TAG=$(fetch_latest_github_release "crmne/zapfast" "x86_64.*linux.*\\.tar\\.gz$" "$ZAPFAST_ARCHIVE")
echo "==> Extracting ZapFast (${ZAPFAST_TAG})..."
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
cat << 'EOF' > "${TARGET_ROOT}/usr/bin/zapfast"
#!/usr/bin/bash
exec /usr/share/zapfast/zapfast "$@"
EOF
chmod 755 "${TARGET_ROOT}/usr/bin/zapfast"

# Copy omarchy themes if present
find "$ZAPFAST_EXTRACT" -path "*/contrib/omarchy/*" -type f -exec cp -f {} "${TARGET_ROOT}/usr/share/zapfast/omarchy/" \; 2>/dev/null || true

# Copy scalable icon if present
ZAPFAST_SVG=$(find "$ZAPFAST_EXTRACT" -name "zapfast.svg" | head -n 1)
if [[ -n "$ZAPFAST_SVG" ]] && [[ -f "$ZAPFAST_SVG" ]]; then
    cp -f "$ZAPFAST_SVG" "${TARGET_ROOT}/usr/share/icons/hicolor/scalable/apps/zapfast.svg"
fi

echo "==> ZapFast (${ZAPFAST_TAG}) installed successfully."

# ------------------------------------------------------------------------------
# 2. Install Mister Download Manager (MDM)
# Repository: anefzaoui/misterdownloadmanager
# ------------------------------------------------------------------------------
echo "=========================================================="
echo "Installing Mister Download Manager (anefzaoui/misterdownloadmanager)..."
echo "=========================================================="

MDM_ARCHIVE="${TMP_WORK_DIR}/mdm.tar.gz"
MDM_EXTRACT="${TMP_WORK_DIR}/mdm_extracted"
mkdir -p "$MDM_EXTRACT"

MDM_TAG=$(fetch_latest_github_release "anefzaoui/misterdownloadmanager" ".*linux.*x86_64.*\\.tar\\.gz$" "$MDM_ARCHIVE")
echo "==> Extracting Mister Download Manager (${MDM_TAG})..."
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

# Install Firefox Extension XPI
MDM_XPI=$(find "$MDM_EXTRACT" -type f -name "mdm-firefox.xpi" | head -n 1)
if [[ -n "$MDM_XPI" ]] && [[ -f "$MDM_XPI" ]]; then
    cp -f "$MDM_XPI" "${TARGET_ROOT}/usr/share/misterdownloadmanager/mdm-firefox.xpi"
    cp -f "$MDM_XPI" "${TARGET_ROOT}/usr/lib64/firefox/browser/extensions/integration@misterdownloadmanager.com.xpi"
fi

# Install Chromium extension files
MDM_EXT_DIR=$(find "$MDM_EXTRACT" -type d -name "extension-chromium" | head -n 1)
if [[ -n "$MDM_EXT_DIR" ]] && [[ -d "$MDM_EXT_DIR" ]]; then
    rm -rf "${TARGET_ROOT}/usr/share/misterdownloadmanager/extension-chromium"
    cp -rf "$MDM_EXT_DIR" "${TARGET_ROOT}/usr/share/misterdownloadmanager/"
fi

echo "==> Mister Download Manager (${MDM_TAG}) installed successfully."

echo "=========================================================="
echo "All external applications fetched and installed successfully!"
echo "=========================================================="
