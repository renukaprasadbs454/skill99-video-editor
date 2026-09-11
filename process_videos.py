#!/usr/bin/env python3
"""
Batch Video Processor
======================
Trims, upscales and adds a logo watermark to every video in INPUT_DIR,
writing the result to OUTPUT_DIR under the exact same filename.

Requires FFmpeg + FFprobe to be installed and available on PATH.
No third-party Python packages are required.

Run with:
    python process_videos.py
or on Windows just double-click run.bat
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

# ============================================================
# CONFIGURATION  (edit these values, nothing else needs to change)
# ============================================================

# --- Folders -------------------------------------------------
INPUT_DIR = "input"
OUTPUT_DIR = "output"
LOGO_PATH = os.path.join("logo", "logo.png")

# --- Output resolution ----------------------------------------
# Change these two values to switch the target resolution
# (e.g. 3840x2160 for 4K). Nothing else in the script needs editing.
OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080

# --- Trim -------------------------------------------------------
# Number of seconds removed from the END of every video.
TRIM_LAST_SECONDS = 10

# --- Logo ---------------------------------------------------------
# Measured from the supplied reference frame (1920x1080 canvas):
# the logo (including its own grey backing plate) is ~277px wide,
# sitting ~11px from the right edge and ~11px from the bottom edge.
LOGO_WIDTH = 280            # logo width in pixels on the OUTPUT canvas
                            # height is auto-calculated to preserve aspect ratio
LOGO_RIGHT_MARGIN = 11      # px from the right edge of the frame
LOGO_BOTTOM_MARGIN = 11     # px from the bottom edge of the frame

# --- Encoding ------------------------------------------------------
VIDEO_CODEC = "libx264"
CRF = 18                    # lower = higher quality/larger file (18 is visually near-lossless)
PRESET = "medium"           # x264 preset: speed vs compression trade-off
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"

# --- Behaviour -------------------------------------------------------
OVERWRITE_EXISTING = False   # False = skip files that already exist in OUTPUT_DIR
SUPPORTED_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm")

# WebM containers cannot hold H.264/AAC. If the *input* (and therefore
# output) file is .webm, these codecs are used instead automatically.
WEBM_VIDEO_CODEC = "libvpx-vp9"
WEBM_AUDIO_CODEC = "libopus"

# ============================================================
# END OF CONFIGURATION
# ============================================================


def check_ffmpeg_installed():
    """Verify ffmpeg and ffprobe are reachable on PATH."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        print("=" * 60)
        print("ERROR: Required tool(s) not found on PATH:", ", ".join(missing))
        print("=" * 60)
        print(
            """
FFmpeg is required for this tool to work.

How to install FFmpeg on Windows:

  Option A - using winget (Windows 10/11, recommended):
    1. Open Command Prompt or PowerShell
    2. Run:  winget install ffmpeg
    3. Close and reopen your terminal / double-click run.bat again

  Option B - manual install:
    1. Go to https://www.gyan.dev/ffmpeg/builds/ (or ffmpeg.org/download.html)
    2. Download the "release full" build (a .zip file)
    3. Extract it, e.g. to  C:\\ffmpeg
    4. Add  C:\\ffmpeg\\bin  to your Windows PATH environment variable:
         - Search "Environment Variables" in the Start Menu
         - Edit the "Path" variable under User or System variables
         - Add a new entry:  C:\\ffmpeg\\bin
    5. Open a NEW Command Prompt window and test with:  ffmpeg -version

  Option C - using Chocolatey (if installed):
    choco install ffmpeg
"""
        )
        sys.exit(1)


def run_command(cmd):
    """Run a subprocess command, returning (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except FileNotFoundError as e:
        return False, "", str(e)


def probe_video(path):
    """Return a dict with duration, width, height, fps, has_audio for a video file."""
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        path,
    ]
    ok, out, err = run_command(cmd)
    if not ok:
        raise RuntimeError(f"ffprobe failed: {err.strip()}")

    data = json.loads(out)
    duration = float(data.get("format", {}).get("duration", 0.0))

    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    if video_stream is None:
        raise RuntimeError("No video stream found in file")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))

    # duration can sometimes only be present on the video stream, not format
    if duration <= 0:
        duration = float(video_stream.get("duration", 0.0))

    fps_raw = video_stream.get("r_frame_rate", "0/1")
    try:
        num, den = fps_raw.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    except ValueError:
        fps = 0.0

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": audio_stream is not None,
        "video_codec": video_stream.get("codec_name", "?"),
        "audio_codec": audio_stream.get("codec_name", "?") if audio_stream else None,
    }


def build_ffmpeg_command(input_path, logo_path, output_path, target_duration, has_audio, video_codec, audio_codec):
    """Construct the ffmpeg command for one file."""

    # Scale to fit the target resolution while preserving aspect ratio,
    # then pad with black bars if the source isn't exactly 16:9 (or whatever
    # ratio OUTPUT_WIDTH/OUTPUT_HEIGHT represents). If the source aspect
    # ratio already matches, the pad amount is 0 and this has no visible effect.
    video_filter = (
        f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:"
        f"force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1[base]"
    )
    logo_filter = f"[1:v]scale={LOGO_WIDTH}:-1:flags=lanczos[logo]"
    overlay_filter = (
        f"[base][logo]overlay="
        f"W-w-{LOGO_RIGHT_MARGIN}:H-h-{LOGO_BOTTOM_MARGIN}[vout]"
    )
    filter_complex = ";".join([video_filter, logo_filter, overlay_filter])

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-i", logo_path,
        "-t", f"{target_duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[vout]",
    ]

    if has_audio:
        cmd += ["-map", "0:a?", "-c:a", audio_codec, "-b:a", AUDIO_BITRATE]
    else:
        cmd += ["-an"]

    cmd += [
        "-c:v", video_codec,
    ]

    # CRF-based encoders (x264/x265) use -crf + -preset.
    # libvpx-vp9 uses a slightly different quality flag set.
    if video_codec == "libvpx-vp9":
        cmd += ["-crf", str(CRF), "-b:v", "0", "-deadline", "good", "-cpu-used", "2"]
    else:
        cmd += ["-crf", str(CRF), "-preset", PRESET]

    cmd += ["-movflags", "+faststart"] if output_path.lower().endswith((".mp4", ".mov")) else []
    cmd += [output_path]
    return cmd


def format_seconds(s):
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{int(h)}h {int(m)}m {sec:.1f}s"
    if m:
        return f"{int(m)}m {sec:.1f}s"
    return f"{sec:.1f}s"


def process_one(filename, index, total):
    input_path = os.path.join(INPUT_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, filename)

    print(f"\n[{index}/{total}] Processing {filename}")

    if os.path.exists(output_path) and not OVERWRITE_EXISTING:
        print(f"  Status: SKIPPED (output already exists, OVERWRITE_EXISTING=False)")
        return "skipped"

    ext = os.path.splitext(filename)[1].lower()
    video_codec = WEBM_VIDEO_CODEC if ext == ".webm" else VIDEO_CODEC
    audio_codec = WEBM_AUDIO_CODEC if ext == ".webm" else AUDIO_CODEC

    try:
        info = probe_video(input_path)
    except Exception as e:
        print(f"  Status: FAILED (could not read video info: {e})")
        return "failed"

    original_duration = info["duration"]
    target_duration = original_duration - TRIM_LAST_SECONDS

    if original_duration <= 0:
        print(f"  Status: FAILED (could not determine video duration)")
        return "failed"

    if target_duration <= 0:
        print(
            f"  Status: FAILED (video is {original_duration:.2f}s, which is <= "
            f"TRIM_LAST_SECONDS={TRIM_LAST_SECONDS}s — nothing would be left)"
        )
        return "failed"

    # Write to a temp file in OUTPUT_DIR first, then atomically rename,
    # so a crash mid-encode never leaves a broken/partial file at the
    # final output path.
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, dir=OUTPUT_DIR)
    os.close(tmp_fd)
    os.remove(tmp_path)  # ffmpeg needs to create the file itself

    cmd = build_ffmpeg_command(
        input_path, LOGO_PATH, tmp_path, target_duration, info["has_audio"],
        video_codec, audio_codec,
    )

    ok, _, err = run_command(cmd)

    if not ok:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print("  Status: FAILED (ffmpeg error)")
        print("  --- ffmpeg output (last 30 lines) ---")
        for line in err.strip().splitlines()[-30:]:
            print("  " + line)
        return "failed"

    os.replace(tmp_path, output_path)

    print(f"  Input:               {input_path}")
    print(f"  Output:              {output_path}")
    print(f"  Original duration:   {format_seconds(original_duration)}")
    print(f"  Final duration:      {format_seconds(target_duration)}")
    print(f"  Original resolution: {info['width']}x{info['height']}")
    print(f"  Output resolution:   {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}")
    print(f"  Logo position:       bottom-right (margin {LOGO_RIGHT_MARGIN}px right, {LOGO_BOTTOM_MARGIN}px bottom)")
    print(f"  Status:              SUCCESS")
    return "success"


def main():
    check_ffmpeg_installed()

    if not os.path.isfile(LOGO_PATH):
        print(f"ERROR: Logo file not found at '{LOGO_PATH}'. Place your logo there and try again.")
        sys.exit(1)

    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = sorted(
        f for f in os.listdir(INPUT_DIR)
        if os.path.isfile(os.path.join(INPUT_DIR, f))
        and os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        print(f"No supported video files found in '{INPUT_DIR}'.")
        print(f"Supported extensions: {', '.join(SUPPORTED_EXTENSIONS)}")
        return

    print(f"Found {len(files)} video(s) in '{INPUT_DIR}'.")

    start_time = time.time()
    results = {"success": [], "failed": [], "skipped": []}

    for i, filename in enumerate(files, start=1):
        status = process_one(filename, i, len(files))
        results[status].append(filename)

    elapsed = time.time() - start_time

    print("\n" + "=" * 40)
    print("PROCESSING COMPLETE")
    print("=" * 40)
    print(f"\nTotal videos: {len(files)}")
    print(f"Successful:   {len(results['success'])}")
    print(f"Skipped:      {len(results['skipped'])}")
    print(f"Failed:       {len(results['failed'])}")
    print(f"Time taken:   {format_seconds(elapsed)}")
    print(f"\nOutput directory:\n{os.path.abspath(OUTPUT_DIR)}")

    if results["failed"]:
        print("\nFailed files:")
        for f in results["failed"]:
            print(f"- {f}")


if __name__ == "__main__":
    main()
