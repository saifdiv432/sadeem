#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Media Probe: Audio Devices and Video Hardware Encoder Discovery for Sadeem OS.
Discovers PipeWire / PulseAudio sources (System Audio & Microphones) and selects
the best available hardware or software video encoders (H.264 & H.265 / HEVC).
"""

import json
import os
import shutil
import subprocess
import sys

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

# Initialize GStreamer once
if not Gst.is_initialized():
    Gst.init(None)


def is_gst_element_available(element_name: str) -> bool:
    """Checks whether a GStreamer element factory is available and instantiable."""
    factory = Gst.ElementFactory.find(element_name)
    if not factory:
        return False
    try:
        el = factory.create(None)
        return el is not None
    except Exception:
        return False


# ============================================================================
# VIDEO & AUDIO CODEC PROBE WITH HARDWARE ACCELERATION FALLBACK CHAIN
# ============================================================================

def probe_h264_encoder():
    """
    Finds the best H.264 encoder using fallback priority:
    VA (vah264enc) -> VA-API (vaapih264enc) -> NVENC (nvh264enc) -> x264enc -> openh264enc
    """
    candidates = [
        ("vah264enc", "vah264enc", True),
        ("vaapih264enc", "vaapih264enc", True),
        ("nvh264enc", "nvh264enc preset=low-latency-hq", True),
        ("x264enc", "x264enc speed-preset=veryfast tune=zerolatency", False),
        ("openh264enc", "openh264enc", False),
    ]

    for name, pipeline_str, is_hw in candidates:
        if is_gst_element_available(name):
            return {
                "codec": "h264",
                "name": name,
                "pipeline_str": pipeline_str,
                "parser": "h264parse",
                "is_hardware": is_hw,
            }

    # Ultimate emergency fallback to x264enc
    return {
        "codec": "h264",
        "name": "x264enc",
        "pipeline_str": "x264enc speed-preset=veryfast tune=zerolatency",
        "parser": "h264parse",
        "is_hardware": False,
    }


def probe_h265_encoder():
    """
    Finds the best H.265 / HEVC encoder using fallback priority:
    VA (vah265enc) -> VA-API (vaapih265enc) -> NVENC (nvh265enc) -> x265enc -> fallback to H.264
    """
    candidates = [
        ("vah265enc", "vah265enc", True),
        ("vaapih265enc", "vaapih265enc", True),
        ("nvh265enc", "nvh265enc preset=low-latency-hq", True),
        ("x265enc", "x265enc speed-preset=veryfast tune=zerolatency", False),
    ]

    for name, pipeline_str, is_hw in candidates:
        if is_gst_element_available(name):
            return {
                "codec": "h265",
                "name": name,
                "pipeline_str": pipeline_str,
                "parser": "h265parse",
                "is_hardware": is_hw,
            }

    # If no H.265 encoder is installed/available, fall back cleanly to H.264
    h264_info = probe_h264_encoder()
    h264_info["fallback_from_h265"] = True
    return h264_info


def probe_audio_encoder():
    """
    Finds the best audio encoder: avenc_aac -> fdkaacenc -> opusenc
    """
    candidates = [
        ("avenc_aac", "avenc_aac", "aacparse"),
        ("fdkaacenc", "fdkaacenc", "aacparse"),
        ("opusenc", "opusenc", "opusparse"),
    ]

    for name, pipeline_str, parser in candidates:
        if is_gst_element_available(name):
            return {
                "name": name,
                "pipeline_str": pipeline_str,
                "parser": parser,
            }

    return {
        "name": "avenc_aac",
        "pipeline_str": "avenc_aac",
        "parser": "aacparse",
    }


def get_muxer_element():
    """Returns universal MP4 container muxer with fragment-duration for streaming resilience."""
    return "mp4mux fragment-duration=1000"


# ============================================================================
# PIPEWIRE / PULSEAUDIO AUDIO DEVICES DISCOVERY
# ============================================================================

def get_system_audio_source():
    """Returns the default system output monitor source identifier."""
    # PulseAudio / PipeWire supports @DEFAULT_SINK@.monitor natively
    return {
        "id": "@DEFAULT_SINK@.monitor",
        "name": "System Audio / صوت النظام",
        "is_default": True,
        "is_monitor": True,
    }


def get_connected_microphones():
    """
    Discovers all connected input devices (microphones) via Gst.DeviceMonitor
    with pactl fallback.
    Returns: list of dicts [{"id": str, "name": str, "is_default": bool}]
    """
    mics = []

    # 1. First probe via Gst.DeviceMonitor (native PipeWire GStreamer)
    try:
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Audio/Source", None)
        monitor.start()
        devices = monitor.get_devices()
        for d in devices:
            disp_name = d.get_display_name() or "Microphone"
            node_name = None
            is_default = False
            props = d.get_properties()
            if props:
                if props.has_field("node.name"):
                    node_name = props.get_string("node.name")
                elif props.has_field("device.name"):
                    node_name = props.get_string("device.name")
                if props.has_field("is-default"):
                    is_default = bool(props.get_boolean("is-default")[1])

            # Filter out monitors (which are system output loopbacks, not mics)
            if node_name and node_name.endswith(".monitor"):
                continue
            if disp_name.lower().startswith("monitor of"):
                continue

            mic_id = node_name if node_name else "@DEFAULT_SOURCE@"
            # Avoid duplicate entries
            if not any(m["id"] == mic_id for m in mics):
                mics.append({
                    "id": mic_id,
                    "name": disp_name,
                    "is_default": is_default,
                    "is_monitor": False,
                })
        monitor.stop()
    except Exception as exc:
        pass

    # 2. Fallback or augment via pactl if Gst.DeviceMonitor was empty
    if not mics and shutil.which("pactl"):
        try:
            # Query default source
            def_source = ""
            info_proc = subprocess.run(["pactl", "info"], capture_output=True, text=True, timeout=2)
            for line in info_proc.stdout.splitlines():
                if line.startswith("Default Source:"):
                    def_source = line.split(":", 1)[1].strip()

            proc = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True, timeout=2)
            cur_name = None
            cur_desc = None
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("Name:"):
                    cur_name = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    cur_desc = line.split(":", 1)[1].strip()
                elif line.startswith("Source #") or line == "":
                    if cur_name and not cur_name.endswith(".monitor"):
                        is_def = (cur_name == def_source)
                        disp = cur_desc or cur_name
                        if not any(m["id"] == cur_name for m in mics):
                            mics.append({
                                "id": cur_name,
                                "name": disp,
                                "is_default": is_def,
                                "is_monitor": False,
                            })
                    cur_name = None
                    cur_desc = None

            if cur_name and not cur_name.endswith(".monitor"):
                is_def = (cur_name == def_source)
                disp = cur_desc or cur_name
                if not any(m["id"] == cur_name for m in mics):
                    mics.append({
                        "id": cur_name,
                        "name": disp,
                        "is_default": is_def,
                        "is_monitor": False,
                    })
        except Exception:
            pass

    # 3. Always ensure at least a generic default source entry exists
    if not mics:
        mics.append({
            "id": "@DEFAULT_SOURCE@",
            "name": "Default Microphone / الميكروفون الافتراضي",
            "is_default": True,
            "is_monitor": False,
        })

    # Sort so default device appears first
    mics.sort(key=lambda m: not m["is_default"])
    return mics


def get_audio_probe_summary():
    """Returns combined summary of system sink monitor and input microphones."""
    return {
        "system_audio": get_system_audio_source(),
        "microphones": get_connected_microphones(),
    }


if __name__ == "__main__":
    print("=== Sadeem Capture Media Probe ===")
    h264 = probe_h264_encoder()
    h265 = probe_h265_encoder()
    audio_enc = probe_audio_encoder()
    muxer = get_muxer_element()

    print(f"H.264 Encoder : {h264['name']} (Hardware: {h264['is_hardware']}) -> {h264['pipeline_str']}")
    print(f"H.265 Encoder : {h265['name']} (Hardware: {h265['is_hardware']}) -> {h265['pipeline_str']}")
    print(f"Audio Encoder : {audio_enc['name']} -> {audio_enc['pipeline_str']}")
    print(f"Muxer         : {muxer}")

    print("\n--- Audio Devices ---")
    audio = get_audio_probe_summary()
    print(f"System Audio  : {audio['system_audio']['name']} ({audio['system_audio']['id']})")
    print("Microphones   :")
    for mic in audio["microphones"]:
        def_tag = " [Default]" if mic["is_default"] else ""
        print(f"  * {mic['name']}{def_tag} -> {mic['id']}")
