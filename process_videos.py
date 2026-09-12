#!/usr/bin/env python3

"""
Batch Video Processor
=====================

Features:
- Processes all videos inside input/
- Removes the last 10 seconds
- Upscales/pads to 1920x1080
- Adds logo watermark at bottom-right
- Keeps the exact same filename
- Saves processed videos inside output/
- Processes multiple videos in parallel
- Uses 5 workers by default
- Saves a checkpoint after every successful video
- Automatically resumes after interruption
- Skips already completed videos
- Supports MP4, MOV, MKV, AVI and WebM
- Requires FFmpeg and FFprobe
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_DIR = "input"
OUTPUT_DIR = "output"
LOGO_PATH = os.path.join("logo", "logo.png")


# ============================================================
# PARALLEL PROCESSING
# ============================================================

# Number of videos processed at the same time.
#
# Example:
# 100 videos + 5 workers
#
# Worker 1 -> 20 videos
# Worker 2 -> 20 videos
# Worker 3 -> 20 videos
# Worker 4 -> 20 videos
# Worker 5 -> 20 videos

WORKERS = 5


# ============================================================
# CHECKPOINT
# ============================================================

CHECKPOINT_FILE = os.path.join(
    OUTPUT_DIR,
    ".processing_checkpoint.json"
)


# ============================================================
# OUTPUT VIDEO
# ============================================================

OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080


# ============================================================
# TRIM
# ============================================================

# Remove this many seconds from the END of every video.

TRIM_LAST_SECONDS = 10


# ============================================================
# LOGO
# ============================================================

LOGO_WIDTH = 280
LOGO_RIGHT_MARGIN = 11
LOGO_BOTTOM_MARGIN = 11


# ============================================================
# ENCODING
# ============================================================

VIDEO_CODEC = "libx264"
CRF = 18
PRESET = "medium"

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"


# ============================================================
# BEHAVIOUR
# ============================================================

# False:
# If output already exists, skip it.
#
# True:
# Reprocess existing output.

OVERWRITE_EXISTING = False


SUPPORTED_EXTENSIONS = (
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
)


# ============================================================
# WEBM CODECS
# ============================================================

# WebM cannot normally use H.264/AAC.

WEBM_VIDEO_CODEC = "libvpx-vp9"
WEBM_AUDIO_CODEC = "libopus"


# ============================================================
# THREAD LOCKS
# ============================================================

checkpoint_lock = threading.Lock()
print_lock = threading.Lock()


# ============================================================
# SAFE PRINT
# ============================================================

def safe_print(*args, **kwargs):
    """Thread-safe console printing."""

    with print_lock:
        print(*args, **kwargs)


# ============================================================
# CHECK FFMPEG
# ============================================================

def check_ffmpeg_installed():
    """Check whether FFmpeg and FFprobe are available."""

    missing = []

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            missing.append(tool)

    if not missing:
        return

    print("=" * 60)
    print("ERROR: Required tool(s) not found on PATH:")
    print(", ".join(missing))
    print("=" * 60)

    print(
        """
FFmpeg is required for this program.

Windows installation:

Option A - Winget:

    winget install ffmpeg

Then close and reopen PowerShell.

Test with:

    ffmpeg -version

and:

    ffprobe -version
"""
    )

    sys.exit(1)


# ============================================================
# RUN COMMAND
# ============================================================

def run_command(cmd):
    """
    Run a command and return:

    success, stdout, stderr
    """

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        return (
            result.returncode == 0,
            result.stdout,
            result.stderr,
        )

    except FileNotFoundError as e:
        return False, "", str(e)


# ============================================================
# LOAD CHECKPOINT
# ============================================================

def load_checkpoint():
    """
    Load successfully completed videos.

    If checkpoint doesn't exist or is damaged,
    return an empty set.
    """

    if not os.path.isfile(CHECKPOINT_FILE):
        return set()

    try:
        with open(
            CHECKPOINT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        completed = data.get("completed", [])

        if not isinstance(completed, list):
            return set()

        return set(completed)

    except Exception as e:

        safe_print(
            f"WARNING: Could not read checkpoint: {e}"
        )

        return set()


# ============================================================
# SAVE CHECKPOINT
# ============================================================

def save_checkpoint(completed):
    """
    Save checkpoint safely.

    Writes a temporary file first and then replaces
    the real checkpoint.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    temp_checkpoint = CHECKPOINT_FILE + ".tmp"

    data = {
        "completed": sorted(completed)
    }

    with open(
        temp_checkpoint,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=4
        )

        f.flush()
        os.fsync(f.fileno())

    os.replace(
        temp_checkpoint,
        CHECKPOINT_FILE
    )


# ============================================================
# MARK VIDEO COMPLETE
# ============================================================

def mark_completed(filename):
    """
    Immediately save one completed video.
    """

    with checkpoint_lock:

        completed = load_checkpoint()

        completed.add(filename)

        save_checkpoint(completed)


# ============================================================
# PROBE VIDEO
# ============================================================

def probe_video(path):
    """
    Get video information using FFprobe.
    """

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]

    ok, out, err = run_command(cmd)

    if not ok:
        raise RuntimeError(
            f"ffprobe failed: {err.strip()}"
        )

    data = json.loads(out)

    duration = float(
        data.get("format", {}).get(
            "duration",
            0.0
        )
    )

    video_stream = next(
        (
            stream
            for stream in data.get("streams", [])
            if stream.get("codec_type") == "video"
        ),
        None,
    )

    audio_stream = next(
        (
            stream
            for stream in data.get("streams", [])
            if stream.get("codec_type") == "audio"
        ),
        None,
    )

    if video_stream is None:
        raise RuntimeError(
            "No video stream found."
        )

    width = int(
        video_stream.get("width", 0)
    )

    height = int(
        video_stream.get("height", 0)
    )

    if duration <= 0:
        duration = float(
            video_stream.get(
                "duration",
                0.0
            )
        )

    fps_raw = video_stream.get(
        "r_frame_rate",
        "0/1"
    )

    try:

        num, den = fps_raw.split("/")

        den = float(den)

        fps = (
            float(num) / den
            if den != 0
            else 0.0
        )

    except (ValueError, ZeroDivisionError):

        fps = 0.0

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": audio_stream is not None,
        "video_codec": video_stream.get(
            "codec_name",
            "?"
        ),
        "audio_codec": (
            audio_stream.get(
                "codec_name",
                "?"
            )
            if audio_stream
            else None
        ),
    }


# ============================================================
# BUILD FFMPEG COMMAND
# ============================================================

def build_ffmpeg_command(
    input_path,
    logo_path,
    output_path,
    target_duration,
    has_audio,
    video_codec,
    audio_codec,
):
    """
    Build FFmpeg command.

    Video:
        Scale to fit 1920x1080
        Preserve aspect ratio
        Pad with black
        Add logo
    """

    video_filter = (
        "[0:v]"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:"
        "force_original_aspect_ratio=decrease:"
        "flags=lanczos,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:"
        "(ow-iw)/2:(oh-ih)/2:"
        "color=black,"
        "setsar=1"
        "[base]"
    )

    logo_filter = (
        "[1:v]"
        f"scale={LOGO_WIDTH}:-1:"
        "flags=lanczos"
        "[logo]"
    )

    overlay_filter = (
        "[base][logo]"
        "overlay="
        f"W-w-{LOGO_RIGHT_MARGIN}:"
        f"H-h-{LOGO_BOTTOM_MARGIN}"
        "[vout]"
    )

    filter_complex = ";".join(
        [
            video_filter,
            logo_filter,
            overlay_filter,
        ]
    )

    cmd = [
        "ffmpeg",
        "-y",

        # Input video
        "-i",
        input_path,

        # Logo
        "-loop",
        "1",
        "-i",
        logo_path,

        # Duration
        "-t",
        f"{target_duration:.3f}",

        # Filters
        "-filter_complex",
        filter_complex,

        # Video output
        "-map",
        "[vout]",
    ]

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    if has_audio:

        cmd += [
            "-map",
            "0:a?",
            "-c:a",
            audio_codec,
            "-b:a",
            AUDIO_BITRATE,
        ]

    else:

        cmd += [
            "-an"
        ]

    # --------------------------------------------------------
    # VIDEO CODEC
    # --------------------------------------------------------

    cmd += [
        "-c:v",
        video_codec,
    ]

    # --------------------------------------------------------
    # ENCODING SETTINGS
    # --------------------------------------------------------

    if video_codec == "libvpx-vp9":

        cmd += [
            "-crf",
            str(CRF),
            "-b:v",
            "0",
            "-deadline",
            "good",
            "-cpu-used",
            "2",
        ]

    else:

        cmd += [
            "-crf",
            str(CRF),
            "-preset",
            PRESET,
        ]

    # --------------------------------------------------------
    # MP4/MOV FAST START
    # --------------------------------------------------------

    if output_path.lower().endswith(
        (".mp4", ".mov")
    ):

        cmd += [
            "-movflags",
            "+faststart",
        ]

    cmd += [
        output_path
    ]

    return cmd


# ============================================================
# FORMAT TIME
# ============================================================

def format_seconds(seconds):
    """Convert seconds into readable format."""

    minutes, seconds = divmod(seconds, 60)

    hours, minutes = divmod(minutes, 60)

    if hours:

        return (
            f"{int(hours)}h "
            f"{int(minutes)}m "
            f"{seconds:.1f}s"
        )

    if minutes:

        return (
            f"{int(minutes)}m "
            f"{seconds:.1f}s"
        )

    return f"{seconds:.1f}s"


# ============================================================
# PROCESS ONE VIDEO
# ============================================================

def process_one(
    filename,
    worker_id,
    index,
    total,
):
    """
    Process exactly one video.

    A worker processes only one video at a time.
    """

    input_path = os.path.join(
        INPUT_DIR,
        filename
    )

    output_path = os.path.join(
        OUTPUT_DIR,
        filename
    )

    safe_print(
        f"\n[Worker {worker_id}] "
        f"[{index}/{total}] "
        f"Processing: {filename}"
    )

    # --------------------------------------------------------
    # CHECKPOINT
    # --------------------------------------------------------

    completed = load_checkpoint()

    if filename in completed:

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"CHECKPOINT COMPLETE, SKIPPED"
        )

        return "skipped"

    # --------------------------------------------------------
    # EXISTING OUTPUT
    # --------------------------------------------------------

    if (
        os.path.isfile(output_path)
        and not OVERWRITE_EXISTING
    ):

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"OUTPUT ALREADY EXISTS, SKIPPED"
        )

        mark_completed(filename)

        return "skipped"

    # --------------------------------------------------------
    # CHECK INPUT
    # --------------------------------------------------------

    if not os.path.isfile(input_path):

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"FAILED: input file not found"
        )

        return "failed"

    # --------------------------------------------------------
    # PROBE VIDEO
    # --------------------------------------------------------

    try:

        info = probe_video(input_path)

    except Exception as e:

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"FAILED: could not read video information"
        )

        safe_print(
            f"  Error: {e}"
        )

        return "failed"

    original_duration = info["duration"]

    # --------------------------------------------------------
    # CALCULATE FINAL DURATION
    # --------------------------------------------------------

    target_duration = (
        original_duration - TRIM_LAST_SECONDS
    )

    # --------------------------------------------------------
    # VALIDATE DURATION
    # --------------------------------------------------------

    if original_duration <= 0:

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"FAILED: invalid duration"
        )

        return "failed"

    if target_duration <= 0:

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"FAILED: video is shorter than "
            f"{TRIM_LAST_SECONDS} seconds"
        )

        return "failed"

    # --------------------------------------------------------
    # SELECT CODECS
    # --------------------------------------------------------

    extension = os.path.splitext(
        filename
    )[1].lower()

    if extension == ".webm":

        video_codec = WEBM_VIDEO_CODEC
        audio_codec = WEBM_AUDIO_CODEC

    else:

        video_codec = VIDEO_CODEC
        audio_codec = AUDIO_CODEC

    # --------------------------------------------------------
    # CREATE OUTPUT DIRECTORY
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # TEMPORARY OUTPUT
    # --------------------------------------------------------

    temp_fd, temp_path = tempfile.mkstemp(
        suffix=extension,
        dir=OUTPUT_DIR
    )

    os.close(temp_fd)

    # FFmpeg must create the file itself.
    os.remove(temp_path)

    # --------------------------------------------------------
    # BUILD COMMAND
    # --------------------------------------------------------

    cmd = build_ffmpeg_command(
        input_path=input_path,
        logo_path=LOGO_PATH,
        output_path=temp_path,
        target_duration=target_duration,
        has_audio=info["has_audio"],
        video_codec=video_codec,
        audio_codec=audio_codec,
    )

    # --------------------------------------------------------
    # RUN FFMPEG
    # --------------------------------------------------------

    start_time = time.time()

    safe_print(
        f"[Worker {worker_id}] "
        f"{filename} -> FFmpeg started"
    )

    ok, _, err = run_command(cmd)

    elapsed = time.time() - start_time

    # --------------------------------------------------------
    # HANDLE FAILURE
    # --------------------------------------------------------

    if not ok:

        if os.path.exists(temp_path):

            try:
                os.remove(temp_path)
            except OSError:
                pass

        safe_print(
            f"\n[Worker {worker_id}] "
            f"{filename} -> FAILED"
        )

        safe_print(
            "  --- FFmpeg output "
            "(last 30 lines) ---"
        )

        error_lines = (
            err.strip().splitlines()
        )

        for line in error_lines[-30:]:

            safe_print(
                "  " + line
            )

        # IMPORTANT:
        # Do NOT mark as completed.

        return "failed"

    # --------------------------------------------------------
    # VERIFY TEMP OUTPUT
    # --------------------------------------------------------

    if not os.path.isfile(temp_path):

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"FAILED: FFmpeg produced no output"
        )

        return "failed"

    # --------------------------------------------------------
    # ATOMICALLY MOVE OUTPUT
    # --------------------------------------------------------

    try:

        os.replace(
            temp_path,
            output_path
        )

    except Exception as e:

        if os.path.exists(temp_path):

            try:
                os.remove(temp_path)
            except OSError:
                pass

        safe_print(
            f"[Worker {worker_id}] "
            f"{filename} -> "
            f"FAILED: could not save output"
        )

        safe_print(
            f"  Error: {e}"
        )

        return "failed"

    # --------------------------------------------------------
    # CHECKPOINT
    # --------------------------------------------------------

    # Output is completely finished.
    #
    # Now mark the video as completed.

    mark_completed(filename)

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    safe_print(
        f"\n[Worker {worker_id}] "
        f"{filename} -> SUCCESS"
    )

    safe_print(
        f"  Input:               {input_path}"
    )

    safe_print(
        f"  Output:              {output_path}"
    )

    safe_print(
        f"  Original duration:   "
        f"{format_seconds(original_duration)}"
    )

    safe_print(
        f"  Final duration:      "
        f"{format_seconds(target_duration)}"
    )

    safe_print(
        f"  Original resolution: "
        f"{info['width']}x{info['height']}"
    )

    safe_print(
        f"  Output resolution:   "
        f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}"
    )

    safe_print(
        f"  Logo position:       "
        f"bottom-right "
        f"(right {LOGO_RIGHT_MARGIN}px, "
        f"bottom {LOGO_BOTTOM_MARGIN}px)"
    )

    safe_print(
        f"  Processing time:     "
        f"{format_seconds(elapsed)}"
    )

    safe_print(
        "  Status:              SUCCESS"
    )

    return "success"


# ============================================================
# SPLIT VIDEOS INTO WORKER BATCHES
# ============================================================

def split_into_worker_batches(files, workers):
    """
    Split files between workers.

    Each video is assigned to exactly one worker.

    Example:

    103 videos + 5 workers

    Worker 1 -> 21
    Worker 2 -> 21
    Worker 3 -> 21
    Worker 4 -> 20
    Worker 5 -> 20
    """

    total = len(files)

    if total == 0:
        return []

    actual_workers = min(
        workers,
        total
    )

    batches = []

    base_size = total // actual_workers
    remainder = total % actual_workers

    start = 0

    for worker_index in range(
        actual_workers
    ):

        batch_size = (
            base_size
            + (
                1
                if worker_index < remainder
                else 0
            )
        )

        end = start + batch_size

        batches.append(
            files[start:end]
        )

        start = end

    return batches


# ============================================================
# WORKER
# ============================================================

def worker_process(
    worker_id,
    worker_files,
):
    """
    One worker processes its assigned batch sequentially.
    """

    results = {
        "success": [],
        "failed": [],
        "skipped": [],
    }

    safe_print("\n" + "=" * 60)

    safe_print(
        f"WORKER {worker_id} STARTED"
    )

    safe_print(
        f"Assigned videos: {len(worker_files)}"
    )

    safe_print("=" * 60)

    total = len(worker_files)

    for index, filename in enumerate(
        worker_files,
        start=1
    ):

        try:

            status = process_one(
                filename=filename,
                worker_id=worker_id,
                index=index,
                total=total,
            )

            results[status].append(filename)

        except Exception as e:

            safe_print(
                f"\n[Worker {worker_id}] "
                f"{filename} -> UNEXPECTED ERROR"
            )

            safe_print(
                f"  Error: {e}"
            )

            results["failed"].append(
                filename
            )

    safe_print(
        "\n" + "-" * 60
    )

    safe_print(
        f"WORKER {worker_id} FINISHED"
    )

    safe_print(
        f"Success: {len(results['success'])}"
    )

    safe_print(
        f"Skipped: {len(results['skipped'])}"
    )

    safe_print(
        f"Failed:  {len(results['failed'])}"
    )

    safe_print(
        "-" * 60
    )

    return results


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # CHECK FFMPEG
    # --------------------------------------------------------

    check_ffmpeg_installed()

    # --------------------------------------------------------
    # CHECK LOGO
    # --------------------------------------------------------

    if not os.path.isfile(LOGO_PATH):

        print(
            f"ERROR: Logo file not found:\n"
            f"{os.path.abspath(LOGO_PATH)}"
        )

        print(
            "\nPlace your logo at:"
        )

        print(
            os.path.abspath(LOGO_PATH)
        )

        return

    # --------------------------------------------------------
    # CREATE DIRECTORIES
    # --------------------------------------------------------

    os.makedirs(
        INPUT_DIR,
        exist_ok=True
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # FIND VIDEOS
    # --------------------------------------------------------

    files = sorted(
        filename
        for filename in os.listdir(INPUT_DIR)
        if (
            os.path.isfile(
                os.path.join(
                    INPUT_DIR,
                    filename
                )
            )
            and
            os.path.splitext(
                filename
            )[1].lower()
            in SUPPORTED_EXTENSIONS
        )
    )

    if not files:

        print(
            f"No supported video files found "
            f"in '{INPUT_DIR}'."
        )

        print(
            "Supported extensions: "
            + ", ".join(
                SUPPORTED_EXTENSIONS
            )
        )

        return

    total_videos = len(files)

    # --------------------------------------------------------
    # LOAD CHECKPOINT
    # --------------------------------------------------------

    completed = load_checkpoint()

    # --------------------------------------------------------
    # EXISTING OUTPUT FILES
    # --------------------------------------------------------

    if not OVERWRITE_EXISTING:

        for filename in files:

            output_path = os.path.join(
                OUTPUT_DIR,
                filename
            )

            if (
                filename not in completed
                and os.path.isfile(output_path)
            ):

                mark_completed(filename)

        completed = load_checkpoint()

    # --------------------------------------------------------
    # REMAINING FILES
    # --------------------------------------------------------

    remaining_files = [
        filename
        for filename in files
        if filename not in completed
    ]

    completed_count = len(
        completed.intersection(files)
    )

    # --------------------------------------------------------
    # START INFORMATION
    # --------------------------------------------------------

    print("\n" + "=" * 60)

    print(
        "PARALLEL VIDEO PROCESSOR"
    )

    print("=" * 60)

    print(
        f"Total videos:       {total_videos}"
    )

    print(
        f"Workers:            "
        f"{min(WORKERS, total_videos)}"
    )

    print(
        f"Already completed:  "
        f"{completed_count}"
    )

    print(
        f"Remaining videos:   "
        f"{len(remaining_files)}"
    )

    print(
        f"Trim last seconds:  "
        f"{TRIM_LAST_SECONDS}"
    )

    print(
        f"Output resolution:  "
        f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}"
    )

    print(
        f"Logo:               "
        f"{LOGO_PATH}"
    )

    print(
        f"Checkpoint:         "
        f"{CHECKPOINT_FILE}"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # NOTHING TO PROCESS
    # --------------------------------------------------------

    if not remaining_files:

        print(
            "\nAll videos are already completed."
        )

        print(
            f"\nOutput directory:"
            f"\n{os.path.abspath(OUTPUT_DIR)}"
        )

        return

    # --------------------------------------------------------
    # CREATE BATCHES
    # --------------------------------------------------------

    batches = split_into_worker_batches(
        remaining_files,
        WORKERS
    )

    print(
        "\nVideo distribution:"
    )

    for worker_id, batch in enumerate(
        batches,
        start=1
    ):

        print(
            f"  Worker {worker_id}: "
            f"{len(batch)} video(s)"
        )

    print(
        "\nStarting parallel processing..."
    )

    print(
        "Each video belongs to exactly ONE worker."
    )

    # --------------------------------------------------------
    # TIMER
    # --------------------------------------------------------

    start_time = time.time()

    all_results = {
        "success": [],
        "failed": [],
        "skipped": [],
    }

    # --------------------------------------------------------
    # START WORKERS
    # --------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=len(batches)
    ) as executor:

        futures = {}

        for worker_id, batch in enumerate(
            batches,
            start=1
        ):

            future = executor.submit(
                worker_process,
                worker_id,
                batch,
            )

            futures[future] = worker_id

        # ----------------------------------------------------
        # COLLECT RESULTS
        # ----------------------------------------------------

        for future in as_completed(futures):

            worker_id = futures[future]

            try:

                results = future.result()

                all_results["success"].extend(
                    results["success"]
                )

                all_results["failed"].extend(
                    results["failed"]
                )

                all_results["skipped"].extend(
                    results["skipped"]
                )

            except Exception as e:

                safe_print(
                    f"\nWORKER {worker_id} CRASHED"
                )

                safe_print(
                    f"Error: {e}"
                )

    # --------------------------------------------------------
    # TIMER END
    # --------------------------------------------------------

    elapsed = time.time() - start_time

    # --------------------------------------------------------
    # FINAL CHECKPOINT
    # --------------------------------------------------------

    final_completed = load_checkpoint()

    final_completed_count = len(
        final_completed.intersection(files)
    )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print("\n" + "=" * 60)

    print(
        "PROCESSING COMPLETE"
    )

    print("=" * 60)

    print(
        f"\nTotal videos:       "
        f"{total_videos}"
    )

    print(
        f"Successful this run: "
        f"{len(all_results['success'])}"
    )

    print(
        f"Skipped this run:   "
        f"{len(all_results['skipped'])}"
    )

    print(
        f"Failed this run:    "
        f"{len(all_results['failed'])}"
    )

    print(
        f"Checkpoint complete: "
        f"{final_completed_count}/{total_videos}"
    )

    print(
        f"Time taken:         "
        f"{format_seconds(elapsed)}"
    )

    print(
        f"\nOutput directory:"
        f"\n{os.path.abspath(OUTPUT_DIR)}"
    )

    # --------------------------------------------------------
    # FAILED FILES
    # --------------------------------------------------------

    if all_results["failed"]:

        print(
            "\nFailed files:"
        )

        for filename in all_results["failed"]:

            print(
                f"- {filename}"
            )

        print(
            "\nRun the script again to retry "
            "the failed videos."
        )

    # --------------------------------------------------------
    # REMAINING FILES
    # --------------------------------------------------------

    remaining_after_run = [
        filename
        for filename in files
        if filename not in final_completed
    ]

    if remaining_after_run:

        print(
            "\nRemaining videos:"
        )

        for filename in remaining_after_run:

            print(
                f"- {filename}"
            )

        print(
            "\nRun the script again to continue "
            "from the checkpoint."
        )

    else:

        print(
            "\nAll videos are completed."
        )

    # --------------------------------------------------------
    # CHECKPOINT LOCATION
    # --------------------------------------------------------

    print(
        "\nCheckpoint saved at:"
    )

    print(
        os.path.abspath(
            CHECKPOINT_FILE
        )
    )

    print(
        "\nDone."
    )


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
