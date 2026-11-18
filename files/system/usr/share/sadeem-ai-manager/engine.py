#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core AI Engine for Sadeem AI Manager:
- Model catalog loading & background refresh
- Official llama.cpp (llama-server) binary auto-installer (CUDA / CPU)
- Hugging Face GGUF & mmproj downloader with live progress, speed, and cancel support
- Local llama-server lifecycle manager (127.0.0.1) with streaming OpenAI-compatible chat
- Local document text extraction (pdftotext + text files) & image base64 encoding
"""

import atexit
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.expanduser("~/.local/share/sadeem-ai")
BIN_DIR = os.path.join(DATA_DIR, "bin")
MODELS_DIR = os.path.join(DATA_DIR, "models")
CONFIG_DIR = os.path.expanduser("~/.config/sadeem-ai-manager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
CACHED_CATALOG_FILE = os.path.join(CONFIG_DIR, "models_catalog_cache.json")
BUNDLED_CATALOG_FILE = os.path.join(APP_DIR, "models_catalog.json")

LLAMA_CPP_RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"
USER_AGENT = "SadeemAIManager/1.0 (+https://github.com/saifdiv432/sadeem)"


def ensure_dirs():
    for d in (DATA_DIR, BIN_DIR, MODELS_DIR, CONFIG_DIR):
        os.makedirs(d, exist_ok=True)


def load_settings():
    ensure_dirs()
    defaults = {
        "onboarding_done": False,
        "last_model_id": "",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception:
            pass
    return defaults


def save_settings(settings):
    ensure_dirs()
    try:
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_FILE)
    except Exception:
        pass


def load_catalog():
    """Load bundled catalog (or newer cached remote catalog if valid)."""
    catalog = {"tiers": [], "models": []}
    for path in (CACHED_CATALOG_FILE, BUNDLED_CATALOG_FILE):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("models"):
                    catalog = data
                    break
            except Exception:
                continue
    return catalog


def refresh_catalog_remote(current_catalog):
    """Optionally refresh models_catalog.json from GitHub raw in background."""
    url = current_catalog.get("remote_catalog_url", "")
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and data.get("models") and data.get("tiers"):
                    ensure_dirs()
                    tmp = CACHED_CATALOG_FILE + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, CACHED_CATALOG_FILE)
                    return data
    except Exception:
        pass
    return None


def get_llama_server_path():
    return os.path.join(BIN_DIR, "llama-server")


def is_llama_server_installed():
    p = get_llama_server_path()
    return os.path.isfile(p) and os.access(p, os.X_OK)


def get_model_gguf_path(model):
    fname = model.get("gguf_filename") or f"{model['id']}.gguf"
    return os.path.join(MODELS_DIR, fname)


def get_model_mmproj_path(model):
    if not model.get("vision") or not model.get("mmproj_filename"):
        return ""
    return os.path.join(MODELS_DIR, f"{model['id']}-{model['mmproj_filename']}")


def is_model_installed(model):
    gguf_p = get_model_gguf_path(model)
    if not (os.path.isfile(gguf_p) and os.path.getsize(gguf_p) > 50 * 1024 * 1024):
        return False
    mm_p = get_model_mmproj_path(model)
    if mm_p:
        if not (os.path.isfile(mm_p) and os.path.getsize(mm_p) > 5 * 1024 * 1024):
            return False
    return True


def delete_model_files(model):
    for p in (
        get_model_gguf_path(model),
        get_model_gguf_path(model) + ".part",
        get_model_mmproj_path(model),
        (get_model_mmproj_path(model) + ".part") if get_model_mmproj_path(model) else "",
    ):
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


def compute_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


class DownloadCancelled(Exception):
    pass


def _stream_download(url, dest_path, label, progress_cb, cancel_event):
    ensure_dirs()
    part_path = dest_path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        total_bytes = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        start_t = time.monotonic()
        last_report_t = 0.0

        with open(part_path, "wb") as out_f:
            while True:
                if cancel_event and cancel_event.is_set():
                    out_f.close()
                    if os.path.exists(part_path):
                        os.remove(part_path)
                    raise DownloadCancelled("Download cancelled by user")

                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)

                now = time.monotonic()
                if progress_cb and (now - last_report_t >= 0.15 or (total_bytes and downloaded >= total_bytes)):
                    elapsed = max(now - start_t, 0.001)
                    speed_mb = (downloaded / (1024 * 1024)) / elapsed
                    frac = (downloaded / total_bytes) if total_bytes > 0 else 0.0
                    progress_cb({
                        "label": label,
                        "fraction": min(1.0, frac),
                        "downloaded_mb": downloaded / (1024 * 1024),
                        "total_mb": total_bytes / (1024 * 1024),
                        "speed_mb": speed_mb,
                    })
                    last_report_t = now

    os.replace(part_path, dest_path)


def _extract_llama_archive(archive_path):
    """Extract llama-server and shared libraries (.so*) flat into BIN_DIR."""
    ensure_dirs()
    extracted_server = False
    tmp_dir = tempfile.mkdtemp(prefix="sadeem-llama-")
    try:
        if archive_path.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(tmp_dir)
        elif archive_path.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(tmp_dir)

        for root, _, files in os.walk(tmp_dir):
            for fname in files:
                src = os.path.join(root, fname)
                if fname == "llama-server":
                    dst = os.path.join(BIN_DIR, "llama-server")
                    shutil.copy2(src, dst)
                    os.chmod(dst, 0o755)
                    extracted_server = True
                elif ".so" in fname:
                    dst = os.path.join(BIN_DIR, fname)
                    if os.path.islink(src):
                        link_target = os.readlink(src)
                        if os.path.lexists(dst):
                            os.remove(dst)
                        os.symlink(os.path.basename(link_target), dst)
                    else:
                        shutil.copy2(src, dst)
                        os.chmod(dst, 0o755)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return extracted_server


def ensure_llama_server(hw, progress_cb=None, cancel_event=None):
    """Download and install official llama.cpp llama-server binary if not already present."""
    if is_llama_server_installed():
        return get_llama_server_path()

    ensure_dirs()
    req = urllib.request.Request(LLAMA_CPP_RELEASES_API, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        releases = json.loads(resp.read().decode("utf-8"))

    use_cuda = bool(hw.get("has_cuda"))
    main_asset = None
    cudart_asset = None

    for rel in releases:
        assets = rel.get("assets", [])
        if not assets:
            continue
        by_name = {a["name"]: a for a in assets}

        if use_cuda:
            # Prefer CUDA 12.x x64 Ubuntu build (most compatible with current NVIDIA drivers)
            cuda_bins = sorted([
                name for name in by_name
                if name.startswith("llama-") and "ubuntu-cuda-" in name and "x64" in name and name.endswith((".tar.gz", ".zip"))
            ])
            cuda12 = [n for n in cuda_bins if "cuda-12" in n]
            chosen = cuda12[0] if cuda12 else (cuda_bins[0] if cuda_bins else None)
            if chosen:
                main_asset = by_name[chosen]
                # Match corresponding cudart runtime archive if published
                cudart_name = "cudart-" + chosen
                if cudart_name in by_name:
                    cudart_asset = by_name[cudart_name]
                break

        # Standard Linux x64 CPU archive
        cpu_bins = [
            name for name in by_name
            if name.startswith("llama-") and "ubuntu-x64" in name and name.endswith((".tar.gz", ".zip"))
        ]
        if cpu_bins:
            main_asset = by_name[cpu_bins[0]]
            break

    if not main_asset:
        raise RuntimeError("Could not find a compatible Linux x64 llama.cpp release asset on GitHub.")

    tmp_archive = os.path.join(DATA_DIR, main_asset["name"])
    try:
        _stream_download(
            main_asset["browser_download_url"],
            tmp_archive,
            f"llama-server ({'CUDA' if use_cuda and 'cuda' in main_asset['name'] else 'Linux x64'})",
            progress_cb,
            cancel_event
        )
        ok = _extract_llama_archive(tmp_archive)
    finally:
        if os.path.exists(tmp_archive):
            os.remove(tmp_archive)

    if cudart_asset:
        tmp_rt = os.path.join(DATA_DIR, cudart_asset["name"])
        try:
            _stream_download(
                cudart_asset["browser_download_url"],
                tmp_rt,
                "CUDA Runtime (cudart)",
                progress_cb,
                cancel_event
            )
            _extract_llama_archive(tmp_rt)
        except DownloadCancelled:
            raise
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_rt):
                os.remove(tmp_rt)

    if not ok or not is_llama_server_installed():
        raise RuntimeError("llama-server binary was not found inside the downloaded archive.")
    return get_llama_server_path()


def _resolve_hf_url(hf_repo, preferred_filename, prefer_mmproj=False):
    """Fallback lookup via Hugging Face public API if a direct URL returns 404."""
    api_url = f"https://huggingface.co/api/models/{hf_repo}/tree/main"
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        items = json.loads(resp.read().decode("utf-8"))
    paths = [i.get("path", "") for i in items if i.get("path", "").endswith(".gguf")]
    if preferred_filename in paths:
        return f"https://huggingface.co/{hf_repo}/resolve/main/{preferred_filename}"
    if prefer_mmproj:
        for kw in ("mmproj-f16", "mmproj-bf16", "mmproj"):
            for p in paths:
                if kw in p.lower():
                    return f"https://huggingface.co/{hf_repo}/resolve/main/{p}"
    else:
        for kw in ("q4_k_m", "q4_k_s", "q4_0"):
            for p in paths:
                if kw in p.lower() and "mmproj" not in p.lower():
                    return f"https://huggingface.co/{hf_repo}/resolve/main/{p}"
    return ""


def download_model_and_engine(model, hw, progress_cb=None, cancel_event=None):
    """Ensure llama-server is present, then download GGUF (and mmproj for Vision models)."""
    ensure_dirs()
    ensure_llama_server(hw, progress_cb=progress_cb, cancel_event=cancel_event)

    # 1. Download main GGUF model
    gguf_dst = get_model_gguf_path(model)
    if not (os.path.isfile(gguf_dst) and os.path.getsize(gguf_dst) > 50 * 1024 * 1024):
        url = model.get("gguf_url", "")
        try:
            _stream_download(url, gguf_dst, model["name"], progress_cb, cancel_event)
        except urllib.error.HTTPError as e:
            if e.code == 404 and model.get("hf_repo"):
                resolved = _resolve_hf_url(model["hf_repo"], model.get("gguf_filename", ""), prefer_mmproj=False)
                if not resolved:
                    raise
                _stream_download(resolved, gguf_dst, model["name"], progress_cb, cancel_event)
            else:
                raise

    # 2. Download Vision mmproj file if supported
    mm_dst = get_model_mmproj_path(model)
    if mm_dst and not (os.path.isfile(mm_dst) and os.path.getsize(mm_dst) > 5 * 1024 * 1024):
        mm_url = model.get("mmproj_url", "")
        try:
            _stream_download(mm_url, mm_dst, f"{model['name']} (Vision)", progress_cb, cancel_event)
        except urllib.error.HTTPError as e:
            if e.code == 404 and model.get("hf_repo"):
                resolved = _resolve_hf_url(model["hf_repo"], model.get("mmproj_filename", ""), prefer_mmproj=True)
                if not resolved:
                    raise
                _stream_download(resolved, mm_dst, f"{model['name']} (Vision)", progress_cb, cancel_event)
            else:
                raise

    return gguf_dst


def extract_document_text(filepath, max_chars=16000):
    """Extract readable text from .pdf (via pdftotext) or text/code files."""
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    if ext == ".pdf":
        res = subprocess.run(
            ["pdftotext", filepath, "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20
        )
        if res.returncode == 0:
            text = res.stdout
        else:
            raise RuntimeError(res.stderr.strip() or "pdftotext failed to read PDF")
    else:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(max_chars + 1024)

    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... تم اقتطاع بقية الملف ليتناسب مع نافذة السياق ...]"
    return text


def encode_image_data_uri(filepath):
    """Encode an image file to a base64 data URI for OpenAI-compatible Vision API."""
    mime, _ = mimetypes.guess_type(filepath)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    with open(filepath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _pick_free_port(preferred=18080):
    for port in (preferred, preferred + 1, preferred + 2, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    return preferred


class LlamaServerManager:
    """Manages local 127.0.0.1 llama-server lifecycle and streaming chat completions."""

    def __init__(self):
        self.proc = None
        self.port = None
        self.active_model_id = None
        atexit.register(self.stop)

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=4)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        self.active_model_id = None
        self.port = None

    def start(self, model, hw):
        if self.is_running() and self.active_model_id == model["id"]:
            return self.port

        self.stop()

        server_bin = get_llama_server_path()
        if not is_llama_server_installed():
            raise RuntimeError("llama-server is not installed yet.")

        gguf_path = get_model_gguf_path(model)
        if not os.path.isfile(gguf_path):
            raise RuntimeError(f"Model file not found: {gguf_path}")

        port = _pick_free_port(18080)
        threads = max(2, min((hw.get("cpu_cores") or 4) - 1, 12))
        # Cap initial context window reasonably on lower-RAM systems to avoid OOM
        ram_total = float(hw.get("ram_total_gb", 8.0))
        max_ctx = 4096 if ram_total < 12.0 else (8192 if ram_total < 24.0 else 16384)
        ctx_size = min(int(model.get("context_window", 8192)), max_ctx)

        cmd = [
            server_bin,
            "--host", "127.0.0.1",
            "--port", str(port),
            "-m", gguf_path,
            "-c", str(ctx_size),
            "-t", str(threads),
        ]

        mm_path = get_model_mmproj_path(model)
        if mm_path and os.path.isfile(mm_path):
            cmd.extend(["--mmproj", mm_path])

        if hw.get("has_cuda"):
            cmd.extend(["-ngl", "99"])

        env = os.environ.copy()
        ld_prev = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{BIN_DIR}:{ld_prev}" if ld_prev else BIN_DIR

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        self.port = port
        self.active_model_id = model["id"]

        # Poll /health until llama-server is ready (up to 60s for large models)
        deadline = time.monotonic() + 60.0
        health_url = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                err_tail = ""
                try:
                    err_tail = (self.proc.stderr.read() or "")[-500:]
                except Exception:
                    pass
                self.stop()
                raise RuntimeError(f"llama-server exited early:\n{err_tail}")
            try:
                with urllib.request.urlopen(health_url, timeout=1.5) as resp:
                    if resp.status == 200:
                        return port
            except Exception:
                pass
            time.sleep(0.4)

        self.stop()
        raise RuntimeError("Timed out waiting for local llama-server to load model.")

    def stream_chat(self, messages, on_token, cancel_event=None):
        """Stream OpenAI-compatible chat completion tokens from local 127.0.0.1 llama-server."""
        if not self.is_running() or not self.port:
            raise RuntimeError("Local AI server is not running.")

        url = f"http://127.0.0.1:{self.port}/v1/chat/completions"
        payload = json.dumps({
            "model": self.active_model_id or "local-model",
            "messages": messages,
            "stream": True,
            "temperature": 0.65,
            "max_tokens": 2048,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST"
        )

        full_text = []
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw_line in resp:
                if cancel_event and cancel_event.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    piece = delta.get("content") or ""
                    if not piece and delta.get("reasoning_content"):
                        piece = delta.get("reasoning_content")
                    if piece:
                        full_text.append(piece)
                        if on_token:
                            on_token(piece)
                except Exception:
                    continue
        return "".join(full_text)
