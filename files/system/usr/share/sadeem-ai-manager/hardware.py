#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hardware Profiler & Model Compatibility Evaluator for Sadeem AI Manager.
Reads RAM (/proc/meminfo), CPU (/proc/cpuinfo), and GPU/VRAM (nvidia-smi & /sys/class/drm).
"""

import glob
import os
import re
import subprocess


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


def get_ram_info():
    total_kb = 0
    avail_kb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        total_kb = int(parts[1])
                elif line.startswith("MemAvailable:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        avail_kb = int(parts[1])
    except Exception:
        pass
    total_gb = round(total_kb / (1024 * 1024), 2) if total_kb else 0.0
    avail_gb = round(avail_kb / (1024 * 1024), 2) if avail_kb else round(total_gb * 0.7, 2)
    return total_gb, avail_gb


def get_cpu_info():
    model = "Unknown CPU"
    cores = os.cpu_count() or 4
    has_avx2 = False
    has_avx512 = False
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("model name") and model == "Unknown CPU":
                    parts = line.split(":", 1)
                    if len(parts) == 2 and parts[1].strip():
                        model = re.sub(r"\s+", " ", parts[1].strip())
                elif line.startswith("flags"):
                    flags = set(line.split(":", 1)[1].strip().split())
                    if "avx2" in flags:
                        has_avx2 = True
                    if any(fl.startswith("avx512") for fl in flags):
                        has_avx512 = True
                    if model != "Unknown CPU":
                        break
    except Exception:
        pass
    return {
        "model": model,
        "cores": cores,
        "has_avx2": has_avx2,
        "has_avx512": has_avx512,
    }


def _lspci_gpu_names():
    names = {}
    try:
        res = subprocess.run(["lspci", "-nn"], capture_output=True, text=True, check=False, timeout=5)
        for line in res.stdout.splitlines():
            if any(k in line for k in ("VGA compatible controller", "3D controller", "Display controller")):
                m = re.match(r"^([0-9a-fA-F:.]+)\s+[^:]+:\s+(.+?)\s+\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", line.strip())
                if m:
                    slot = m.group(1)
                    sys_slot = slot if slot.count(":") >= 2 else f"0000:{slot}"
                    clean_name = re.sub(r"\(rev\s+[0-9a-fA-F]+\)", "", m.group(2)).strip()
                    names[sys_slot.lower()] = (m.group(3).lower(), clean_name)
    except Exception:
        pass
    return names


def get_gpu_info():
    gpus = []
    has_cuda = False
    primary_vendor = "cpu"
    primary_name = "CPU Only (No Dedicated GPU)"
    primary_vram_gb = 0.0

    # 1. Check NVIDIA GPU + VRAM via nvidia-smi
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    gname = parts[0]
                    try:
                        vram_mb = float(parts[1])
                    except ValueError:
                        vram_mb = 0.0
                    vram_gb = round(vram_mb / 1024.0, 2)
                    gpus.append({
                        "vendor": "nvidia",
                        "name": gname,
                        "vram_gb": vram_gb,
                        "cuda": True,
                    })
                    has_cuda = True
                    if vram_gb >= primary_vram_gb:
                        primary_vendor = "nvidia"
                        primary_name = gname
                        primary_vram_gb = vram_gb
    except Exception:
        pass

    # 2. Inspect /sys/class/drm/card*/device for AMD and Intel GPUs
    lspci_map = _lspci_gpu_names()
    seen_slots = set()
    for card_path in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        if "-" in os.path.basename(card_path):
            continue
        dev_dir = os.path.join(card_path, "device")
        if not os.path.isdir(dev_dir):
            continue
        real_slot = os.path.basename(os.path.realpath(dev_dir)).lower()
        if real_slot in seen_slots:
            continue
        seen_slots.add(real_slot)

        vendor_hex = _read_text(os.path.join(dev_dir, "vendor")).replace("0x", "").lower()
        vram_bytes_s = _read_text(os.path.join(dev_dir, "mem_info_vram_total"))
        vram_gb = 0.0
        if vram_bytes_s.isdigit():
            vram_gb = round(int(vram_bytes_s) / (1024 ** 3), 2)

        lspci_entry = lspci_map.get(real_slot)
        gpu_name = lspci_entry[1] if lspci_entry else ""

        if vendor_hex == "1002":
            gname = gpu_name or "AMD Radeon Graphics"
            gpus.append({"vendor": "amd", "name": gname, "vram_gb": vram_gb, "cuda": False})
            if not has_cuda and (primary_vendor == "cpu" or vram_gb > primary_vram_gb):
                primary_vendor = "amd"
                primary_name = gname
                primary_vram_gb = vram_gb
        elif vendor_hex == "8086":
            gname = gpu_name or "Intel Integrated Graphics"
            gpus.append({"vendor": "intel", "name": gname, "vram_gb": vram_gb, "cuda": False})
            if not has_cuda and primary_vendor == "cpu":
                primary_vendor = "intel"
                primary_name = gname
                primary_vram_gb = vram_gb
        elif vendor_hex == "10de" and not has_cuda:
            gname = gpu_name or "NVIDIA GPU (Driver Inactive)"
            gpus.append({"vendor": "nvidia", "name": gname, "vram_gb": vram_gb, "cuda": False})
            if primary_vendor == "cpu":
                primary_vendor = "nvidia"
                primary_name = gname
                primary_vram_gb = vram_gb

    return {
        "vendor": primary_vendor,
        "name": primary_name,
        "vram_gb": primary_vram_gb,
        "has_cuda": has_cuda,
        "all_gpus": gpus,
    }


def profile_hardware():
    ram_total_gb, ram_avail_gb = get_ram_info()
    cpu = get_cpu_info()
    gpu = get_gpu_info()

    # Determine recommended model tier
    if ram_total_gb >= 24.0 or (ram_total_gb >= 16.0 and gpu["vram_gb"] >= 10.0):
        rec_tier = "pro"
        rec_range_ar = "النماذج الكبيرة والاحترافية (12B–14B)"
        rec_range_en = "Large & Pro Models (12B–14B)"
    elif ram_total_gb >= 12.0 or (ram_total_gb >= 8.0 and gpu["vram_gb"] >= 6.0):
        rec_tier = "medium"
        rec_range_ar = "النماذج المتوسطة المتوازنة (4B–9B)"
        rec_range_en = "Balanced Medium Models (4B–9B)"
    else:
        rec_tier = "light"
        rec_range_ar = "النماذج الخفيفة السريعة (1B–4B)"
        rec_range_en = "Fast Lightweight Models (1B–4B)"

    return {
        "ram_total_gb": ram_total_gb,
        "ram_avail_gb": ram_avail_gb,
        "cpu_model": cpu["model"],
        "cpu_cores": cpu["cores"],
        "has_avx2": cpu["has_avx2"],
        "has_avx512": cpu["has_avx512"],
        "gpu_vendor": gpu["vendor"],
        "gpu_name": gpu["name"],
        "vram_gb": gpu["vram_gb"],
        "has_cuda": gpu["has_cuda"],
        "all_gpus": gpu["all_gpus"],
        "recommended_tier": rec_tier,
        "recommended_range_ar": rec_range_ar,
        "recommended_range_en": rec_range_en,
    }


def evaluate_model_compatibility(model, hw):
    """
    Evaluate model fit against available system memory (and discrete GPU VRAM offload).
    - < 65% of usable memory -> 'excellent' (green)
    - 65% to 85%            -> 'acceptable' (amber/yellow)
    - > 85%                 -> 'too_heavy' (red, locked with warning)
    """
    ram_req = float(model.get("ram_required_gb", model.get("size_gb", 2.0) * 1.4))
    ram_total = max(float(hw.get("ram_total_gb", 8.0)), 1.0)
    ram_avail = max(float(hw.get("ram_avail_gb", ram_total * 0.7)), 1.0)

    # Effective budget accounts for reclaimable page cache + discrete GPU VRAM when offloading via CUDA
    usable_mem = max(ram_avail, ram_total * 0.78)
    vram = float(hw.get("vram_gb", 0.0))
    if hw.get("has_cuda") and vram >= 3.5:
        usable_mem = max(usable_mem, ram_avail + vram * 0.80)

    ratio = ram_req / max(usable_mem, 1.0)
    pct = min(999, int(round(ratio * 100)))

    if ratio < 0.65:
        level = "excellent"
        label_ar = "ممتاز لجهازك"
        label_en = "Excellent for your PC"
    elif ratio <= 0.85:
        level = "acceptable"
        label_ar = "يعمل بأداء مقبول"
        label_en = "Acceptable Performance"
    else:
        level = "too_heavy"
        label_ar = "يتطلب ذاكرة أكبر"
        label_en = "Requires More RAM"

    return {
        "level": level,
        "ratio": ratio,
        "percent": pct,
        "ram_required_gb": ram_req,
        "usable_mem_gb": round(usable_mem, 1),
        "label_ar": label_ar,
        "label_en": label_en,
    }
