#!/usr/bin/env python3
"""Sync bundled ZapFast and Mister Download Manager metadata and companion assets."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

INSTALL_SCRIPT = "files/scripts/install-external-apps.sh"

APPS = {
    "zapfast": {
        "repo": "crmne/zapfast",
        "asset_regex": r"x86_64.*linux.*\.tar\.gz$",
        "var_name": "ZAPFAST_FALLBACK",
    },
    "misterdm": {
        "repo": "anefzaoui/misterdownloadmanager",
        "asset_regex": r".*linux.*x86_64.*\.tar\.gz$",
        "var_name": "MDM_FALLBACK",
    },
}


def github_get_json(url: str) -> dict | list:
    headers = {
        "User-Agent": "sadeem-app-sync",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def resolve_latest_release(repo: str, asset_regex: str) -> tuple[str, str]:
    """Return (tag_name, browser_download_url) for the latest matching asset."""
    for endpoint in (
        f"https://api.github.com/repos/{repo}/releases/latest",
        f"https://api.github.com/repos/{repo}/releases",
    ):
        data = github_get_json(endpoint)
        releases = data if isinstance(data, list) else [data]
        for rel in releases:
            if not isinstance(rel, dict) or rel.get("draft") or rel.get("prerelease"):
                continue
            tag = rel.get("tag_name", "")
            for asset in rel.get("assets", []):
                name = asset.get("name", "")
                dl_url = asset.get("browser_download_url", "")
                if dl_url and re.search(asset_regex, name, re.IGNORECASE):
                    return tag, dl_url
    raise RuntimeError(f"No matching release asset found for {repo}")


def read_current_fallback(script_text: str, var_name: str) -> str:
    m = re.search(rf'^{re.escape(var_name)}="([^"]+)"', script_text, re.MULTILINE)
    if not m:
        raise RuntimeError(f"Could not locate {var_name} in {INSTALL_SCRIPT}")
    return m.group(1)


def download_and_extract_tar_gz(url: str, extract_dir: str) -> None:
    archive_path = os.path.join(extract_dir, "archive.tar.gz")
    subprocess.run(
        [
            "curl", "-fSL", "--retry", "3", "--retry-delay", "2",
            "-H", "User-Agent: sadeem-app-sync",
            "-o", archive_path, url,
        ],
        check=True,
    )
    if not os.path.isfile(archive_path) or os.path.getsize(archive_path) == 0:
        raise RuntimeError(f"Downloaded archive is empty: {url}")
    with tarfile.open(archive_path, "r:gz") as tf:
        tf.extractall(extract_dir, filter="data")


def sync_zapfast_assets(repo_root: str, extract_dir: str) -> None:
    found_bin = False
    for root, _dirs, files in os.walk(extract_dir):
        if "zapfast" in files and os.path.getsize(os.path.join(root, "zapfast")) > 0:
            found_bin = True
        if "zapfast.svg" in files:
            src_svg = os.path.join(root, "zapfast.svg")
            dst_svg = os.path.join(repo_root, "files/system/usr/share/icons/hicolor/scalable/apps/zapfast.svg")
            os.makedirs(os.path.dirname(dst_svg), exist_ok=True)
            shutil.copy2(src_svg, dst_svg)
        norm_root = root.replace("\\", "/")
        if norm_root.endswith("/contrib/omarchy") or "/contrib/omarchy/" in norm_root:
            dst_om = os.path.join(repo_root, "files/system/usr/share/zapfast/omarchy")
            os.makedirs(dst_om, exist_ok=True)
            for fn in files:
                shutil.copy2(os.path.join(root, fn), os.path.join(dst_om, fn))
    if not found_bin:
        raise RuntimeError("Validated ZapFast archive missing zapfast binary")


def sync_misterdm_assets(repo_root: str, extract_dir: str) -> None:
    required = {
        "misterdownloadmanager",
        "misterdownloadmanager-cli",
        "misterdownloadmanager-mcp",
        "misterdownloadmanager-nmhost",
    }
    found_bins = set()
    xpi_path = None
    chromium_dir = None

    for root, dirs, files in os.walk(extract_dir):
        for fn in files:
            fpath = os.path.join(root, fn)
            if fn in required and os.path.getsize(fpath) > 0:
                found_bins.add(fn)
            if fn == "mdm-firefox.xpi" and os.path.getsize(fpath) > 0:
                xpi_path = fpath
        if "extension-chromium" in dirs and chromium_dir is None:
            chromium_dir = os.path.join(root, "extension-chromium")

    missing = required - found_bins
    if missing:
        raise RuntimeError(f"Validated MDM archive missing binaries: {sorted(missing)}")

    if xpi_path:
        for rel in (
            "files/system/usr/share/misterdownloadmanager/mdm-firefox.xpi",
            "files/system/usr/lib64/firefox/browser/extensions/integration@misterdownloadmanager.com.xpi",
            "files/system/etc/skel/.var/app/org.mozilla.firefox/.mozilla/extensions/{ec8030f7-c20a-464f-9b0e-13a3a9e97384}/integration@misterdownloadmanager.com.xpi",
        ):
            dst = os.path.join(repo_root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(xpi_path, dst)

    if chromium_dir and os.path.isdir(chromium_dir):
        dst_chr = os.path.join(repo_root, "files/system/usr/share/misterdownloadmanager/extension-chromium")
        shutil.rmtree(dst_chr, ignore_errors=True)
        shutil.copytree(chromium_dir, dst_chr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync ZapFast and MisterDM releases.")
    parser.add_argument("--check", action="store_true", help="Only report status without modifying files.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    script_path = os.path.join(repo_root, INSTALL_SCRIPT)
    with open(script_path, "r", encoding="utf-8") as fp:
        script_text = fp.read()

    updates = []
    for app_key, cfg in APPS.items():
        current_url = read_current_fallback(script_text, cfg["var_name"])
        latest_tag, latest_url = resolve_latest_release(cfg["repo"], cfg["asset_regex"])
        if latest_url == current_url:
            print(f"{app_key}: up to date ({latest_tag})")
            continue

        print(f"{app_key}: update available -> {latest_tag} ({latest_url})")
        if args.check:
            updates.append(f"{app_key}:{latest_tag}")
            continue

        with tempfile.TemporaryDirectory(prefix=f"sync_{app_key}_") as tmpdir:
            download_and_extract_tar_gz(latest_url, tmpdir)
            if app_key == "zapfast":
                sync_zapfast_assets(repo_root, tmpdir)
            else:
                sync_misterdm_assets(repo_root, tmpdir)

        script_text = re.sub(
            rf'^({re.escape(cfg["var_name"])}=")[^"]+(")',
            rf"\g<1>{latest_url}\g<2>",
            script_text,
            flags=re.MULTILINE,
        )
        updates.append(f"{app_key} {latest_tag}")

    if not args.check and updates:
        with open(script_path, "w", encoding="utf-8") as fp:
            fp.write(script_text)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fp:
            fp.write(f"updated={'true' if updates else 'false'}\n")
            fp.write(f"summary={', '.join(updates) if updates else 'none'}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
