# Batch Video Processor

Automatically trims, upscales, and adds a logo watermark to every supported
video in `input/`, saving the processed videos to `output/` under the
**exact same filename**.

The processor supports **parallel video processing**, **automatic checkpointing**,
**resume after interruption**, and **skipping already completed videos**.

---

## What it does to every video

1. Removes the last `TRIM_LAST_SECONDS` seconds from the end.
2. Scales the video to `OUTPUT_WIDTH x OUTPUT_HEIGHT` using a high-quality
   Lanczos filter.
3. Preserves the original aspect ratio.
4. Adds black padding when the input aspect ratio does not match the target
   resolution.
5. Adds your logo in the bottom-right corner.
6. Keeps the logo at a fixed width while automatically preserving its aspect ratio.
7. Preserves the original audio when available and re-encodes it.
8. Uses H.264/AAC for normal formats.
9. Automatically uses VP9/Opus for `.webm` files.
10. Processes multiple videos in parallel using **5 workers by default**.
11. Saves a checkpoint after every successfully completed video.
12. Automatically resumes from the checkpoint if the program is interrupted.
13. Skips videos that have already been completed.
14. Uses temporary output files and atomically moves completed files into place,
    preventing incomplete outputs from being treated as finished files.

---

## 1. Installation

### Install FFmpeg (Windows)

This tool drives FFmpeg and FFprobe under the hood, so both must be installed
and available on your system `PATH`.

**Easiest — winget (Windows 10/11):**

```text
winget install ffmpeg
```

Then close and reopen PowerShell.

Test with:

```text
ffmpeg -version
```

and:

```text
ffprobe -version
```

**Manual install:**

1. Download a "release full" build from the FFmpeg website.
2. Extract it to a location such as `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your Windows PATH.
4. Open a new terminal.
5. Verify the installation using:

```text
ffmpeg -version
```

and:

```text
ffprobe -version
```

If FFmpeg or FFprobe is not found, the script prints installation
instructions and stops before processing videos.

### Install Python

Python 3.8+ is required.

Download Python from the official Python website and make sure Python is
available from your terminal.

**No external Python packages are required.**

The script uses Python's built-in libraries and calls FFmpeg/FFprobe directly.

---

## 2. Usage

Project structure:

```text
video-processor/
├── input/                 ← put your videos here
├── output/                ← processed videos appear here
├── logo/
│   └── logo.png           ← watermark logo
├── process_videos.py
├── requirements.txt
├── run.bat
└── README.md
```

### Step 1 — Add videos

Put your videos inside:

```text
input/
```

Supported formats:

```text
.mp4
.mov
.mkv
.avi
.webm
```

### Step 2 — Check the logo

The default logo location is:

```text
logo/logo.png
```

Replace the file if you want to use another logo.

### Step 3 — Run the processor

On Windows, you can double-click:

```text
run.bat
```

or run the Python script directly:

```text
python process_videos.py
```

The script will automatically:

* Find all supported videos.
* Check the checkpoint.
* Detect videos already completed.
* Divide the remaining videos between workers.
* Process multiple videos simultaneously.
* Save each successful result.
* Update the checkpoint immediately after each successful video.

---

## 3. Parallel Processing

The processor uses multiple workers so that several videos can be processed
at the same time.

The default setting is:

```python
WORKERS = 5
```

For example, if there are 100 videos:

```text
Worker 1 → assigned videos
Worker 2 → assigned videos
Worker 3 → assigned videos
Worker 4 → assigned videos
Worker 5 → assigned videos
```

Each worker processes its assigned videos sequentially, while all workers run
in parallel.

### Worker distribution

The script automatically distributes videos as evenly as possible.

For example:

```text
103 videos
5 workers
```

The distribution will be approximately:

```text
Worker 1 → 21 videos
Worker 2 → 21 videos
Worker 3 → 21 videos
Worker 4 → 20 videos
Worker 5 → 20 videos
```

Each video is assigned to **exactly one worker**.

The number of workers is automatically reduced when fewer videos are available.

For example:

```text
3 videos
5 workers
```

The script will use only:

```text
3 workers
```

instead of starting unnecessary workers.

### Important

Increasing `WORKERS` does not always make processing faster.

Video processing is CPU-intensive and can also require significant disk
I/O. Choose a worker count appropriate for your CPU, RAM, and storage.

The default value is:

```python
WORKERS = 5
```

You can change it in the configuration section if required.

---

## 4. Checkpoint and Resume

The processor maintains a checkpoint file:

```text
output/.processing_checkpoint.json
```

Every time a video finishes successfully, its filename is immediately added
to the checkpoint.

Example:

```json
{
    "completed": [
        "video1.mp4",
        "video2.mp4",
        "video3.mp4"
    ]
}
```

### Why the checkpoint is useful

If processing 100 videos is interrupted after 60 videos, running the script
again does **not** start from the beginning.

The processor checks the checkpoint and skips the videos that were already
completed.

For example:

```text
Total videos:       100
Already completed:  60
Remaining videos:   40
```

Only the remaining 40 videos are processed.

### Checkpoint safety

The checkpoint is written to a temporary file first and then replaced using
an atomic file operation.

This helps prevent a partially written checkpoint from replacing the valid
checkpoint if the program is interrupted while saving it.

---

## 5. Automatic Skip System

The processor has two ways to determine whether a video is already complete.

### Checkpoint

If the filename exists in:

```text
.processing_checkpoint.json
```

the video is skipped.

Example:

```text
video1.mp4 → CHECKPOINT COMPLETE, SKIPPED
```

### Existing output

If an output file already exists in `output/` but is not yet present in the
checkpoint, the script treats that output as completed and adds it to the
checkpoint.

Example:

```text
input/video1.mp4
output/video1.mp4
```

If:

```python
OVERWRITE_EXISTING = False
```

the existing output is skipped.

---

## 6. Configuration

All main settings are located at the top of `process_videos.py`.

| Variable               | Meaning                                        |
| ---------------------- | ---------------------------------------------- |
| `INPUT_DIR`            | Input video directory                          |
| `OUTPUT_DIR`           | Output video directory                         |
| `LOGO_PATH`            | Path to the watermark logo                     |
| `WORKERS`              | Number of videos processed simultaneously      |
| `CHECKPOINT_FILE`      | Location of the processing checkpoint          |
| `OUTPUT_WIDTH`         | Target output width                            |
| `OUTPUT_HEIGHT`        | Target output height                           |
| `TRIM_LAST_SECONDS`    | Number of seconds removed from the end         |
| `LOGO_WIDTH`           | Logo width in pixels                           |
| `LOGO_RIGHT_MARGIN`    | Distance of logo from right edge               |
| `LOGO_BOTTOM_MARGIN`   | Distance of logo from bottom edge              |
| `VIDEO_CODEC`          | Default video codec                            |
| `CRF`                  | Video quality setting                          |
| `PRESET`               | H.264 encoding speed/quality preset            |
| `AUDIO_CODEC`          | Default audio codec                            |
| `AUDIO_BITRATE`        | Audio bitrate                                  |
| `OVERWRITE_EXISTING`   | Whether existing outputs should be reprocessed |
| `SUPPORTED_EXTENSIONS` | Video extensions detected in `input/`          |
| `WEBM_VIDEO_CODEC`     | Video codec used for WebM                      |
| `WEBM_AUDIO_CODEC`     | Audio codec used for WebM                      |

### Default configuration

```python
INPUT_DIR = "input"
OUTPUT_DIR = "output"
LOGO_PATH = os.path.join("logo", "logo.png")

WORKERS = 5

OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080

TRIM_LAST_SECONDS = 10

LOGO_WIDTH = 280
LOGO_RIGHT_MARGIN = 11
LOGO_BOTTOM_MARGIN = 11

VIDEO_CODEC = "libx264"
CRF = 18
PRESET = "medium"

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"

OVERWRITE_EXISTING = False
```

---

## 7. Video Processing

### Resolution

The default output resolution is:

```text
1920 × 1080
```

The video is scaled using:

```text
Lanczos
```

for high-quality resizing.

The script does not simply change the video's metadata. The video is
actually re-rendered.

### Aspect ratio

The script preserves the original aspect ratio.

For videos that are not 16:9, the video is scaled to fit inside the
`1920x1080` frame and black padding is added.

This prevents:

* stretched faces
* distorted objects
* unwanted cropping

For example:

```text
Original:       1280 × 720
Output:         1920 × 1080
```

A 16:9 video fills the complete output frame.

For a non-16:9 video, black bars may be added.

---

## 8. Trimming

The default configuration removes the last:

```text
10 seconds
```

from every video.

This is controlled by:

```python
TRIM_LAST_SECONDS = 10
```

For example:

```text
Original: 1 minute 30 seconds
Final:    1 minute 20 seconds
```

If a video is 10 seconds or shorter, it cannot be processed because removing
10 seconds would leave no usable video.

The script reports this video as failed and continues processing the other
videos.

---

## 9. Logo Watermark

The logo is loaded from:

```text
logo/logo.png
```

The default logo settings are:

```python
LOGO_WIDTH = 280
LOGO_RIGHT_MARGIN = 11
LOGO_BOTTOM_MARGIN = 11
```

The logo is positioned at the bottom-right of the output frame.

Its height is automatically calculated so that the original logo aspect ratio
is preserved.

The logo appears for the entire duration of the processed video.

### Default position

```text
1920 × 1080 output

Right margin:  11 px
Bottom margin: 11 px
Logo width:    280 px
```

---

## 10. Audio

If the input video contains an audio stream, the audio is preserved and
re-encoded.

Default settings:

```python
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"
```

If the source video has no audio track, the output is created without audio.

---

## 11. WebM Support

WebM files are handled separately because WebM normally uses codecs such as
VP9 and Opus rather than H.264/AAC.

For `.webm` input files, the script automatically uses:

```python
WEBM_VIDEO_CODEC = "libvpx-vp9"
WEBM_AUDIO_CODEC = "libopus"
```

The WebM output therefore uses:

```text
Video → VP9
Audio → Opus
```

For other formats, the default codecs are:

```text
Video → H.264
Audio → AAC
```

You do not need to manually change the codec settings when processing WebM
files.

---

## 12. Temporary Output and Safe Saving

The processor does not write directly to the final output filename.

Instead, it creates a temporary file inside the `output/` directory.

FFmpeg writes the processed video to this temporary file.

Only after FFmpeg successfully finishes does the script move the temporary
file to the final filename using an atomic replacement operation.

This means an interrupted or failed FFmpeg operation should not leave a
partially generated video at the final output path.

The final sequence is:

```text
Input video
     ↓
FFmpeg processing
     ↓
Temporary output
     ↓
Successful verification
     ↓
Atomic rename
     ↓
Final output
     ↓
Checkpoint update
```

The checkpoint is updated **only after the final output has been successfully
saved**.

---

## 13. Error Handling

A failure in one video does not stop the entire batch.

For example:

```text
video01.mp4 → SUCCESS
video02.mp4 → SUCCESS
video03.mp4 → FAILED
video04.mp4 → SUCCESS
video05.mp4 → SUCCESS
```

The failed video is not added to the checkpoint.

When the script is run again, the failed video can be retried.

For FFmpeg failures, the script prints the last 30 lines of FFmpeg's error
output to help identify the problem.

---

## 14. Processing Output

Suppose the input directory contains:

```text
input/
├── video1.mp4
├── video2.mp4
├── video3.mp4
├── video4.mp4
└── video5.mp4
```

The output will be:

```text
output/
├── video1.mp4
├── video2.mp4
├── video3.mp4
├── video4.mp4
└── video5.mp4
```

The filenames remain exactly the same.

For example:

```text
input/data analytics - 1.mp4
```

becomes:

```text
output/data analytics - 1.mp4
```

There are no automatic prefixes or suffixes added to the filename.

---

## 15. Project Structure

```text
video-processor/
├── input/                       ← source videos
│   └── data analytics - 1.mp4
│
├── output/                      ← processed videos
│   ├── data analytics - 1.mp4
│   └── .processing_checkpoint.json
│
├── logo/
│   └── logo.png                 ← watermark logo
│
├── process_videos.py            ← main processor
├── requirements.txt
├── run.bat
└── README.md
```

The source videos inside `input/` are never modified.

---

## 16. Git Tracking Policy

The repository can keep a small sample set tracked for demonstration while
ignoring user-generated videos and outputs.

Recommended policy:

| Path                                 | Status     | Reason                  |
| ------------------------------------ | ---------- | ----------------------- |
| `input/data analytics - 1.mp4`       | ✅ tracked  | Sample source video     |
| `output/data analytics - 1.mp4`      | ✅ tracked  | Sample processed output |
| `logo/logo.png`                      | ✅ tracked  | Watermark logo          |
| `output/.processing_checkpoint.json` | 🚫 ignored | Local processing state  |
| Any other file in `input/`           | 🚫 ignored | User/private videos     |
| Any other file in `output/`          | 🚫 ignored | Generated outputs       |
| Any other image in `logo/`           | 🚫 ignored | Alternative logos       |

Large video files can significantly increase Git repository size, so only
the required sample files should normally be committed.

---

## 17. Troubleshooting

### "ffmpeg/ffprobe not found"

Install FFmpeg and make sure both `ffmpeg` and `ffprobe` are available in
your Windows PATH.

Test:

```text
ffmpeg -version
```

and:

```text
ffprobe -version
```

Then restart PowerShell or your terminal.

### A specific video fails

The script continues processing the other videos.

The console displays the last 30 lines of FFmpeg's error output.

Common causes include:

* Corrupted input video
* Unsupported/corrupted codec
* Video shorter than `TRIM_LAST_SECONDS`
* Missing or invalid video stream
* Insufficient disk space
* FFmpeg encoding error

Run the script again after fixing the problem. Failed videos are not marked
as completed and can therefore be retried.

### Processing was interrupted

Simply run:

```text
python process_videos.py
```

again.

The processor reads:

```text
output/.processing_checkpoint.json
```

and skips videos that were already completed.

### An output file already exists

With:

```python
OVERWRITE_EXISTING = False
```

existing output files are skipped.

If you want to reprocess existing output files, change:

```python
OVERWRITE_EXISTING = True
```

Then run the script again.

### Processing is too slow

The processor uses:

```python
WORKERS = 5
```

Try adjusting the worker count based on your CPU and storage performance.

Higher worker counts can increase CPU and disk usage and may not always
produce faster results.

---

## 18. Processing Flow

The complete workflow is:

```text
                 START
                   │
                   ▼
          Check FFmpeg/FFprobe
                   │
                   ▼
             Check logo
                   │
                   ▼
          Find input videos
                   │
                   ▼
          Load checkpoint
                   │
                   ▼
       Remove already completed
                   │
                   ▼
          Divide remaining
          videos among workers
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
       Worker   Worker    Worker
          │        │        │
          ▼        ▼        ▼
       FFmpeg   FFmpeg    FFmpeg
          │        │        │
          └────────┼────────┘
                   ▼
          Save completed output
                   │
                   ▼
          Update checkpoint
                   │
                   ▼
          Process next video
                   │
                   ▼
          All workers finish
                   │
                   ▼
            Final summary
                   │
                   ▼
                  DONE
```

---

## 19. Summary

This batch processor provides:

* ✅ Automatic video discovery
* ✅ MP4 support
* ✅ MOV support
* ✅ MKV support
* ✅ AVI support
* ✅ WebM support
* ✅ Last 10-second trimming
* ✅ 1920×1080 output
* ✅ Lanczos scaling
* ✅ Aspect-ratio preservation
* ✅ Black padding for non-16:9 videos
* ✅ Bottom-right logo watermark
* ✅ Original audio preservation
* ✅ H.264/AAC encoding
* ✅ Automatic VP9/Opus encoding for WebM
* ✅ 5-worker parallel processing
* ✅ Even worker distribution
* ✅ Checkpoint after every successful video
* ✅ Automatic resume after interruption
* ✅ Automatic skipping of completed files
* ✅ Failed-video retry support
* ✅ Temporary output files
* ✅ Atomic final output replacement
* ✅ Thread-safe console output
* ✅ Exact original filenames
* ✅ Processing summary and failure list

The processor is designed to safely process large batches of videos without
having to restart the entire batch when an individual video fails or the
program is interrupted.
