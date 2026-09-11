# Batch Video Processor

Automatically trims, upscales, and adds a logo watermark to every video in
`input/`, saving the results to `output/` under the **exact same filename**.

## What it does to every video

1. Removes the last `TRIM_LAST_SECONDS` seconds from the end.
2. Scales the video to `OUTPUT_WIDTH x OUTPUT_HEIGHT` using a high-quality
   Lanczos filter (real re-render, not just a metadata change).
3. Overlays your logo in the bottom-right corner, at a fixed pixel size and
   margin, for the entire duration of the video.
4. Preserves the original audio (re-encoded to keep file size/quality sane),
   unless the source has no audio track at all.

---

## 1. Installation

### Install FFmpeg (Windows)

This tool drives FFmpeg under the hood, so it must be installed and on your
PATH.

**Easiest — winget (Windows 10/11):**
```
winget install ffmpeg
```
Then close and reopen your terminal.

**Manual install:**
1. Download a "release full" build from https://www.gyan.dev/ffmpeg/builds/
2. Extract it to e.g. `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your Windows PATH (Start Menu → search
   "Environment Variables" → edit "Path" → add the entry).
4. Open a **new** terminal and confirm with `ffmpeg -version`.

If FFmpeg isn't found, the script will print these same instructions and
stop before doing anything.

### Install Python

Python 3.8+ is required. Get it from https://www.python.org/downloads/ and
make sure to check "Add Python to PATH" during install.

**No external Python packages are needed** — see `requirements.txt`.

---

## 2. Usage

```
video-processor/
├── input/     ← put your videos here
├── output/    ← processed videos appear here
├── logo/
│   └── logo.png   ← your logo (already included)
```

1. Drop your videos into `input/` (`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`).
2. Your logo already sits at `logo/logo.png` — replace it if needed.
3. Double-click `run.bat` (Windows), or run:
   ```
   python process_videos.py
   ```
4. Grab your finished videos from `output/`.

`input/video1.mp4` → `output/video1.mp4` (same name, no prefixes/suffixes).

A failure on one file is logged and skipped — it never stops the rest of
the batch.

---

## 3. Configuration

All settings live in the `CONFIGURATION` block at the top of
`process_videos.py`:

| Variable | Meaning |
|---|---|
| `INPUT_DIR` / `OUTPUT_DIR` / `LOGO_PATH` | Folder locations |
| `OUTPUT_WIDTH` / `OUTPUT_HEIGHT` | Target resolution (e.g. `3840`/`2160` for 4K) |
| `TRIM_LAST_SECONDS` | Seconds removed from the end of every video |
| `LOGO_WIDTH` | Logo width in pixels on the output canvas (height auto-scales to preserve aspect ratio — never stretched) |
| `LOGO_RIGHT_MARGIN` / `LOGO_BOTTOM_MARGIN` | Distance from the right/bottom edge of the frame, in pixels |
| `VIDEO_CODEC` / `CRF` / `PRESET` | H.264 encoding quality/speed settings |
| `AUDIO_CODEC` / `AUDIO_BITRATE` | Audio encoding settings |
| `OVERWRITE_EXISTING` | `False` = skip files that already exist in `output/`; `True` = reprocess them |
| `SUPPORTED_EXTENSIONS` | Which file extensions are picked up from `input/` |

Change any of these and re-run — nothing else in the code needs editing.

**Note on `.webm`:** the WebM container can't hold H.264/AAC, so `.webm`
inputs are automatically encoded with VP9/Opus instead, regardless of the
`VIDEO_CODEC`/`AUDIO_CODEC` settings above. This is handled for you.

---

## 4. How the reference sample was analyzed

You provided a logo file and two reference frames (rather than full sample
videos) showing the desired before/after look. Here's what was measured
directly from those files and used to set the defaults above:

**Before frame:** `1280x720` (720p, 16:9).

**After frame:** `1920x1080` (1080p, 16:9) — confirms the 720p → 1080p
upscale target.

**Logo, measured on the 1920x1080 after-frame** (by diffing pixels against
the frame's background color to find the logo's bounding box):
- Size on canvas: **~277 x 55 px** (width:height ≈ 5.04, close to the logo
  file's native ratio of 1598:327 ≈ 4.89 — small difference is measurement
  rounding at edges).
- Right margin: **~11 px** from the right edge.
- Bottom margin: **~11 px** from the bottom edge.

These became the defaults: `LOGO_WIDTH = 280`, `LOGO_RIGHT_MARGIN = 11`,
`LOGO_BOTTOM_MARGIN = 11`. If you'd like it larger/smaller or with more
breathing room, just change these three numbers.

**Aspect-ratio handling:** since your before/after samples are both 16:9,
a video that's already 16:9 is scaled straight to `1920x1080` with no
padding. If a future input has a different aspect ratio, the script scales
it to fit inside the frame and adds black letterbox/pillarbox bars rather
than stretching or cropping the image — this keeps every video safe by
default without guessing what you'd want cropped away. If you'd rather
crop-to-fill for non-16:9 inputs, this is a one-line filter change
(`force_original_aspect_ratio=decrease` → `increase` + crop) — ask if you
want that swapped in.

**A note on your uploaded logo file:** its embedded EXIF metadata chunk is
slightly malformed, which makes some image libraries (e.g. Python's
Pillow) fail to open it — but FFmpeg reads it without any problem, so no
change was needed for this script to work correctly with it as-is.

---

## 5. Project structure

```
video-processor/
├── input/                 ← source videos (never modified)
├── output/                ← processed videos land here
├── logo/
│   └── logo.png
├── process_videos.py      ← the script — all config at the top
├── requirements.txt
├── run.bat                ← double-click to run on Windows
└── README.md
```

## 6. Troubleshooting

- **"ffmpeg/ffprobe not found"** — see the installation section above.
- **A specific file fails** — the console prints the last 30 lines of
  FFmpeg's error output for that file, and processing continues with the
  next one. Common causes: corrupted source file, or a video shorter than
  `TRIM_LAST_SECONDS`.
- **Re-processing a file** — set `OVERWRITE_EXISTING = True`, or delete the
  existing file from `output/`.
