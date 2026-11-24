#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast, robust video editing engine for Sadeem Video Editor using FFmpeg subprocess pipelines.
Features:
- Stream-copy fast path for single kept segment trimming without re-encoding (instant, lossless).
- Multi-segment cutting, concatenation, and per-segment speed alterations (0.5x .. 4.0x) via filter_complex.
- Independent temporal vector markup overlays and native temporal boxblur regions.
- Audio volume adjustment, partial mute ranges, smooth audio fade in/out.
- External audio track insertion with timeline offset, duration trimming, mixing or replacing original audio.
- Export resolution scaling (native, 1080p, 720p) and GIF export with high-quality palette generation.
- Real-time progress monitoring via `-progress pipe:1`, clean cancellation, and atomic file replacement.
"""

import os
import re
import shutil
import subprocess
import tempfile

_FFMPEG_BIN = shutil.which("ffmpeg")
_FFPROBE_BIN = shutil.which("ffprobe")
_DETECTED_ENCODER = None


def _detect_h264_encoder():
    """Detect the best available H.264 video encoder on the host."""
    global _DETECTED_ENCODER
    if _DETECTED_ENCODER is not None:
        return _DETECTED_ENCODER

    if not _FFMPEG_BIN:
        _DETECTED_ENCODER = "libx264"
        return _DETECTED_ENCODER

    try:
        res = subprocess.run(
            [_FFMPEG_BIN, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        encoders = res.stdout
    except Exception:
        encoders = ""

    for enc in ["libx264", "libopenh264", "h264_vaapi", "mpeg4"]:
        if enc in encoders:
            _DETECTED_ENCODER = enc
            return enc

    _DETECTED_ENCODER = "libx264"
    return _DETECTED_ENCODER


def _has_audio_stream(path):
    """Accurately check whether the input video file contains an audio stream."""
    if not _FFPROBE_BIN or not os.path.isfile(path):
        return False
    cmd = [
        _FFPROBE_BIN,
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False)
        return bool(res.stdout.strip())
    except Exception:
        return False


def _get_duration(path):
    """Retrieve video duration in seconds via ffprobe."""
    if not _FFPROBE_BIN or not os.path.isfile(path):
        return 0.0
    cmd = [
        _FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return 0.0


def _build_atempo_filter(speed):
    """Construct chained atempo filters for audio speed adjustment outside [0.5, 2.0]."""
    sp = float(speed)
    filters = []
    while sp > 2.0:
        filters.append("atempo=2.0")
        sp /= 2.0
    while sp < 0.5:
        filters.append("atempo=0.5")
        sp /= 0.5
    if abs(sp - 1.0) > 0.01:
        filters.append(f"atempo={sp:.4f}")
    return ",".join(filters) if filters else None


def export_video(
    input_path,
    output_path,
    trim_start=None,
    trim_end=None,
    kept_segments=None,
    mute_all=False,
    mute_ranges=None,
    original_volume=1.0,
    audio_fade=False,
    external_audio=None,
    external_audio_clips=None,
    crop_box=None,
    overlay_png_path=None,
    overlay_start=None,
    overlay_end=None,
    overlay_items=None,
    blur_items=None,
    export_resolution="native",
    export_format="mp4",
    progress_callback=None,
    cancel_event=None,
):
    """
    Export edited video with optimal speed and quality.

    Arguments:
    - input_path: path to source video file
    - output_path: destination file path
    - trim_start, trim_end: start/end times in seconds (single-segment fallback)
    - kept_segments: list of (start_sec, end_sec) or (start_sec, end_sec, speed)
    - mute_all: bool, drop audio entirely
    - mute_ranges: list of (start_sec, end_sec) for partial audio silencing
    - original_volume: float multiplier (0.0 .. 2.0)
    - audio_fade: bool, apply 0.5s fade in and fade out
    - external_audio: dict {"path", "timeline_start", "duration", "volume", "replace_original"}
    - crop_box: tuple of (x, y, w, h) in pixels
    - overlay_png_path: path to single RGBA PNG image
    - overlay_start, overlay_end: time range in seconds for single overlay
    - overlay_items: list of dicts with {"png_path", "out_ranges": [(s, e), ...]}
    - blur_items: list of dicts with {"out_s", "out_e", "x", "y", "w", "h"}
    - export_resolution: "native", "1080p", or "720p"
    - export_format: "mp4" or "gif"
    - progress_callback: func(fraction: float, time_sec: float)
    - cancel_event: threading.Event to abort processing

    Returns:
    (success: bool, error_msg: str or None)
    """
    if not _FFMPEG_BIN:
        return False, "FFmpeg binary not found in PATH"
    if not os.path.isfile(input_path):
        return False, f"Input video file not found: {input_path}"

    total_in_dur = _get_duration(input_path)

    # 1. Resolve kept segments: (start, end, speed)
    effective_segments = []
    if kept_segments and len(kept_segments) > 0:
        for item in kept_segments:
            if isinstance(item, (list, tuple)):
                s = float(item[0])
                e = float(item[1])
                sp = float(item[2]) if len(item) > 2 else 1.0
            elif isinstance(item, dict):
                s = float(item.get("start", 0.0))
                e = float(item.get("end", 0.0))
                sp = float(item.get("speed", 1.0))
            else:
                continue

            s_f = max(0.0, s)
            e_f = min(total_in_dur, e) if total_in_dur > 0 else e
            if e_f > s_f + 0.01:
                effective_segments.append((s_f, e_f, max(0.05, sp)))

    if not effective_segments:
        eff_start = max(0.0, float(trim_start)) if trim_start is not None else 0.0
        eff_end = float(trim_end) if (trim_end is not None and trim_end > 0) else total_in_dur
        if eff_end <= eff_start:
            eff_end = total_in_dur if total_in_dur > eff_start else eff_start + 1.0
        effective_segments.append((eff_start, eff_end, 1.0))

    target_duration = max(0.1, sum((e - s) / sp for s, e, sp in effective_segments))
    has_audio = _has_audio_stream(input_path)

    # 2. Check conditions
    has_crop = bool(crop_box and len(crop_box) == 4 and crop_box[2] > 0 and crop_box[3] > 0)
    has_blur = bool(blur_items and len(blur_items) > 0)
    has_multi_overlays = bool(overlay_items and len(overlay_items) > 0)
    has_single_overlay = bool(overlay_png_path and os.path.isfile(overlay_png_path))
    has_overlay = has_multi_overlays or has_single_overlay
    has_partial_mute = bool(mute_ranges and len(mute_ranges) > 0 and not mute_all and has_audio)
    
    # Check external audio (either list of clips or single dict)
    active_ext_clips = []
    if external_audio_clips and not mute_all:
        for c in external_audio_clips:
            if c and c.get("path") and os.path.isfile(c.get("path")):
                active_ext_clips.append(c)
    elif external_audio and external_audio.get("path") and os.path.isfile(external_audio.get("path")) and not mute_all:
        active_ext_clips.append(external_audio)

    has_ext_audio = bool(active_ext_clips)
    has_speed_change = any(abs(sp - 1.0) > 0.01 for _s, _e, sp in effective_segments)
    has_volume_change = has_audio and abs(float(original_volume) - 1.0) > 0.01
    is_multi_segment = len(effective_segments) > 1
    is_gif = (export_format or "").lower() == "gif"
    needs_scale = export_resolution in ("1080p", "720p")

    # Temporary output for atomic write
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    ext = ".gif" if is_gif else ".mp4"
    tmp_out = os.path.join(out_dir, f".sadeem_export_{os.getpid()}_{os.path.basename(output_path)}")
    if not tmp_out.endswith(ext):
        tmp_out += ext

    cmd = [_FFMPEG_BIN, "-y", "-hide_banner"]

    # -------------------------------------------------------------------------
    # CASE 1: STREAM COPY FAST PATH
    # Single segment, 1.0x speed, no crop, no blur, no overlays, no audio edits, native res, mp4
    # -------------------------------------------------------------------------
    if (
        not is_multi_segment
        and not has_speed_change
        and not has_crop
        and not has_blur
        and not has_overlay
        and not has_partial_mute
        and not has_ext_audio
        and not audio_fade
        and not has_volume_change
        and not is_gif
        and not needs_scale
    ):
        s0, e0, _sp = effective_segments[0]
        seg_dur = max(0.1, e0 - s0)
        if s0 > 0:
            cmd.extend(["-ss", f"{s0:.3f}"])
        cmd.extend(["-i", input_path])
        cmd.extend(["-t", f"{seg_dur:.3f}"])
        cmd.extend(["-c:v", "copy"])
        if mute_all or not has_audio:
            cmd.append("-an")
        else:
            cmd.extend(["-c:a", "copy"])
        cmd.extend(["-movflags", "+faststart"])

    # -------------------------------------------------------------------------
    # CASE 2: FULL RE-ENCODE PIPELINE
    # -------------------------------------------------------------------------
    else:
        # Input 0: Main Video
        cmd.extend(["-i", input_path])
        input_count = 1

        # Additional Inputs: Single overlay PNG
        single_ov_input_idx = None
        if has_single_overlay and not has_multi_overlays:
            cmd.extend(["-i", overlay_png_path])
            single_ov_input_idx = input_count
            input_count += 1

        # Additional Inputs: Multi overlay PNGs
        multi_ov_indices = []
        if has_multi_overlays:
            for item in overlay_items:
                p = item.get("png_path")
                if p and os.path.isfile(p):
                    cmd.extend(["-i", p])
                    multi_ov_indices.append((input_count, item.get("out_ranges", [])))
                    input_count += 1

        # Additional Input(s): External audio file(s)
        ext_audio_inputs = []
        if has_ext_audio:
            for clip in active_ext_clips:
                cmd.extend(["-i", clip["path"]])
                ext_audio_inputs.append((input_count, clip))
                input_count += 1

        filter_parts = []
        n_segs = len(effective_segments)

        # 1. Video Trimming and Speed Adjustment
        for i, (s, e, sp) in enumerate(effective_segments):
            pts_factor = 1.0 / sp
            filter_parts.append(
                f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=(PTS-STARTPTS)*{pts_factor:.6f}[v{i}]"
            )

        # 2. Audio Processing (Original track)
        replace_orig_audio = any(c.get("replace_original", False) for c in active_ext_clips)
        include_orig_audio = has_audio and not mute_all and not replace_orig_audio and not is_gif

        if include_orig_audio:
            af_filters = []
            if has_partial_mute:
                for ms, me in mute_ranges:
                    af_filters.append(f"volume=enable='between(t,{ms:.3f},{me:.3f})':volume=0")
            if has_volume_change:
                af_filters.append(f"volume={float(original_volume):.3f}")

            if af_filters:
                af_str = ",".join(af_filters)
                filter_parts.append(f"[0:a]{af_str}[a_src]")
                a_in_label = "a_src"
            else:
                a_in_label = "0:a"

            if n_segs > 1:
                splits = "".join(f"[a_in_{i}]" for i in range(n_segs))
                filter_parts.append(f"[{a_in_label}]asplit={n_segs}{splits}")
                for i, (s, e, sp) in enumerate(effective_segments):
                    af_sp = _build_atempo_filter(sp)
                    tempo_str = f",{af_sp}" if af_sp else ""
                    filter_parts.append(
                        f"[a_in_{i}]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS{tempo_str}[a{i}]"
                    )
            else:
                s0, e0, sp0 = effective_segments[0]
                af_sp = _build_atempo_filter(sp0)
                tempo_str = f",{af_sp}" if af_sp else ""
                filter_parts.append(
                    f"[{a_in_label}]atrim=start={s0:.3f}:end={e0:.3f},asetpts=PTS-STARTPTS{tempo_str}[a0]"
                )

        # 3. Concatenate Segments
        if n_segs > 1:
            if include_orig_audio:
                cat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n_segs))
                filter_parts.append(f"{cat_inputs}concat=n={n_segs}:v=1:a=1[vcat][acat_raw]")
            else:
                cat_inputs = "".join(f"[v{i}]" for i in range(n_segs))
                filter_parts.append(f"{cat_inputs}concat=n={n_segs}:v=1:a=0[vcat]")
            cur_v_label = "vcat"
        else:
            cur_v_label = "v0"
            if include_orig_audio:
                filter_parts.append("[a0]anull[acat_raw]")

        # 4. Temporal Blur Regions
        if has_blur:
            for b_idx, b_item in enumerate(blur_items):
                out_s = max(0.0, float(b_item.get("out_s", 0.0)))
                out_e = min(target_duration, float(b_item.get("out_e", target_duration)))
                bx = max(0, int(b_item.get("x", 0) // 2 * 2))
                by = max(0, int(b_item.get("y", 0) // 2 * 2))
                bw = max(2, int(b_item.get("w", 2) // 2 * 2))
                bh = max(2, int(b_item.get("h", 2) // 2 * 2))
                b_style = str(b_item.get("blur_style") or b_item.get("style", "pixelate")).lower()
                strength = max(1, min(100, int(b_item.get("blur_strength") or b_item.get("strength", 50))))
                nxt_v = f"vb_{b_idx}"

                if b_style == "solid":
                    filter_parts.append(
                        f"[{cur_v_label}]drawbox=x={bx}:y={by}:w={bw}:h={bh}:color=black@1.0:t=fill:enable='between(t,{out_s:.3f},{out_e:.3f})'[{nxt_v}]"
                    )
                elif b_style == "frosted":
                    sigma = max(4.0, round(4.0 + (strength / 100.0) * 28.0, 1))
                    filter_parts.append(
                        f"[{cur_v_label}]split[bbase_{b_idx}][bsrc_{b_idx}];"
                        f"[bsrc_{b_idx}]crop={bw}:{bh}:{bx}:{by},gblur=sigma={sigma:.1f}:steps=2,eq=brightness=0.14:saturation=0.75[bblur_{b_idx}];"
                        f"[bbase_{b_idx}][bblur_{b_idx}]overlay={bx}:{by}:enable='between(t,{out_s:.3f},{out_e:.3f})'[{nxt_v}]"
                    )
                else:  # pixelate (default)
                    blk = max(6, int(round(6 + (strength / 100.0) * 38)))
                    filter_parts.append(
                        f"[{cur_v_label}]split[bbase_{b_idx}][bsrc_{b_idx}];"
                        f"[bsrc_{b_idx}]crop={bw}:{bh}:{bx}:{by},scale=max(2\\,iw/{blk}):max(2\\,ih/{blk}):flags=neighbor,scale={bw}:{bh}:flags=neighbor[bblur_{b_idx}];"
                        f"[bbase_{b_idx}][bblur_{b_idx}]overlay={bx}:{by}:enable='between(t,{out_s:.3f},{out_e:.3f})'[{nxt_v}]"
                    )
                cur_v_label = nxt_v

        # 5. Vector Markup Overlays
        if single_ov_input_idx is not None:
            ov_s = max(0.0, float(overlay_start) if overlay_start is not None else 0.0)
            ov_e = max(0.0, float(overlay_end) if overlay_end is not None else target_duration)
            nxt_v = "v_single_ov"
            filter_parts.append(
                f"[{cur_v_label}][{single_ov_input_idx}:v]overlay=0:0:enable='between(t,{ov_s:.3f},{ov_e:.3f})'[{nxt_v}]"
            )
            cur_v_label = nxt_v

        if has_multi_overlays:
            for m_idx, (in_idx, ranges) in enumerate(multi_ov_indices):
                nxt_v = f"v_multi_ov_{m_idx}"
                if ranges:
                    enables = "+".join(f"between(t,{rs:.3f},{re:.3f})" for rs, re in ranges)
                else:
                    enables = f"between(t,0,{target_duration:.3f})"
                filter_parts.append(
                    f"[{cur_v_label}][{in_idx}:v]overlay=0:0:enable='{enables}'[{nxt_v}]"
                )
                cur_v_label = nxt_v

        # 6. Spatial Crop
        if has_crop:
            cx, cy, cw, ch = crop_box
            cw = max(2, int(cw // 2 * 2))
            ch = max(2, int(ch // 2 * 2))
            cx = max(0, int(cx // 2 * 2))
            cy = max(0, int(cy // 2 * 2))
            filter_parts.append(f"[{cur_v_label}]crop={cw}:{ch}:{cx}:{cy}[vcrop]")
            cur_v_label = "vcrop"

        # 7. Resolution Scaling
        if export_resolution == "1080p":
            filter_parts.append(f"[{cur_v_label}]scale=-2:1080:flags=lanczos[vscale]")
            cur_v_label = "vscale"
        elif export_resolution == "720p":
            filter_parts.append(f"[{cur_v_label}]scale=-2:720:flags=lanczos[vscale]")
            cur_v_label = "vscale"

        # 8. Final Audio Track (Fade + External Mix/Replace)
        final_a_label = None
        if not is_gif:
            # Process original audio fade
            cur_a_label = None
            if include_orig_audio:
                if audio_fade:
                    fade_d = min(0.5, target_duration / 4.0)
                    fade_out_st = max(0.0, target_duration - fade_d)
                    filter_parts.append(
                        f"[acat_raw]afade=t=in:ss=0:d={fade_d:.2f},afade=t=out:st={fade_out_st:.2f}:d={fade_d:.2f}[afaded]"
                    )
                    cur_a_label = "afaded"
                else:
                    cur_a_label = "acat_raw"

            # External audio input(s)
            ext_a_labels = []
            if has_ext_audio and ext_audio_inputs:
                for c_i, (in_idx, clip) in enumerate(ext_audio_inputs):
                    ea_trim_s = max(0.0, float(clip.get("source_start", clip.get("trim_start", 0.0))))
                    ea_dur = min(target_duration, float(clip.get("duration", target_duration)))
                    ea_tl_start = max(0.0, float(clip.get("timeline_start", 0.0)))
                    ea_vol = max(0.0, float(clip.get("volume", 1.0)))
                    delay_ms = int(round(ea_tl_start * 1000.0))
                    a_lbl = f"a_ext_{c_i}"
                    filter_parts.append(
                        f"[{in_idx}:a]atrim=start={ea_trim_s:.3f}:duration={ea_dur:.3f},"
                        f"asetpts=PTS-STARTPTS,volume={ea_vol:.3f},adelay={delay_ms}|{delay_ms}[{a_lbl}]"
                    )
                    ext_a_labels.append(a_lbl)

            mix_inputs = []
            if cur_a_label and not replace_orig_audio:
                mix_inputs.append(f"[{cur_a_label}]")
            for a_lbl in ext_a_labels:
                mix_inputs.append(f"[{a_lbl}]")

            if len(mix_inputs) > 1:
                filter_parts.append(
                    f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0:normalize=0[amixed]"
                )
                final_a_label = "amixed"
            elif len(mix_inputs) == 1:
                final_a_label = mix_inputs[0].strip("[]")
            else:
                final_a_label = cur_a_label

        # 9. GIF conversion or Final Mapping
        if is_gif:
            filter_parts.append(
                f"[{cur_v_label}]fps=12,scale=min(720\\,iw):-2:flags=lanczos,split[g0][g1];"
                f"[g0]palettegen=stats_mode=diff[gp];"
                f"[g1][gp]paletteuse=dither=bayer:bayer_scale=5[vgif]"
            )
            cur_v_label = "vgif"

        filter_complex_str = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_complex_str])
        cmd.extend(["-map", f"[{cur_v_label}]"])

        if final_a_label and not is_gif:
            cmd.extend(["-map", f"[{final_a_label}]", "-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.append("-an")

        if is_gif:
            pass  # gif muxer
        else:
            encoder = _detect_h264_encoder()
            if encoder == "libopenh264":
                enc_args = ["-c:v", "libopenh264", "-b:v", "4M", "-pix_fmt", "yuv420p"]
            elif encoder == "h264_vaapi":
                enc_args = ["-c:v", "h264_vaapi", "-b:v", "4M"]
            elif encoder == "mpeg4":
                enc_args = ["-c:v", "mpeg4", "-q:v", "4"]
            else:
                enc_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p"]

            cmd.extend(enc_args)
            cmd.extend(["-movflags", "+faststart"])

    # Progress reporting pipe
    cmd.extend(["-progress", "pipe:1", tmp_out])

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        out_time_re = re.compile(r"out_time_us=(\d+)")

        for line in proc.stdout:
            if cancel_event and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    proc.kill()
                if os.path.isfile(tmp_out):
                    try:
                        os.remove(tmp_out)
                    except OSError:
                        pass
                return False, "Export cancelled by user"

            line = line.strip()
            m = out_time_re.match(line)
            if m and progress_callback:
                us = int(m.group(1))
                time_sec = us / 1_000_000.0
                fraction = min(1.0, max(0.0, time_sec / target_duration))
                progress_callback(fraction, time_sec)

        proc.wait()

        if proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass

        if proc.returncode != 0:
            err = proc.stderr.read() if proc.stderr else "FFmpeg process failed"
            if proc.stderr:
                try:
                    proc.stderr.close()
                except Exception:
                    pass
            if os.path.isfile(tmp_out):
                try:
                    os.remove(tmp_out)
                except OSError:
                    pass
            return False, err.strip()

        if proc.stderr:
            try:
                proc.stderr.close()
            except Exception:
                pass

        if not os.path.isfile(tmp_out) or os.path.getsize(tmp_out) == 0:
            return False, "Generated output file is missing or empty"

        # Atomic replacement
        os.replace(tmp_out, output_path)

        if progress_callback:
            progress_callback(1.0, target_duration)

        return True, None

    except Exception as exc:
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        if os.path.isfile(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
        return False, str(exc)
