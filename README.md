# SER Viewer

**English** | [日本語](README.ja.md)

A player for **SER video files**, the format used in solar, lunar and planetary
astronomy imaging. It offers the features of
[SER Player](https://github.com/cgarry/ser-player) plus **FITS export**, and
runs on both macOS and Windows.

![Main window](docs/images/main-window.png)

---

## Features

### Playback
- Play, pause, step frame by frame, play in reverse, loop
- Frame slider, frame number entry, per-frame UTC timestamp display
- In/out markers (`[` / `]`) that limit both playback and every export
- Adjustable playback rate, initialised from the frame rate recorded in the file
- Zoom from 5% to 1600%, drag to pan, fit to window, actual size
- Cursor position and the **raw ADU value** shown in the status bar
- Drag and drop to open, recent file list

### Processing (applied live to the display)
- Debayer (RGGB / GRBG / GBRG / BGGR, CMYG patterns approximated, pattern can be forced)
- Gain, gamma, black level, per-frame auto stretch
- Saturation and RGB colour balance
- Channel alignment for atmospheric dispersion (shifts red and blue by pixels)
- Monochrome conversion (luminance / average / single channel / two-channel mixes)
- Invert, flip horizontally or vertically, rotate in 90° steps
- Crop from a selection box, snapped to even coordinates so the Bayer phase survives
- Histogram per channel, logarithmic scale, min/max/mean/median and clipping percentages
- Full SER header inspector, including the measured effective bit depth

### Export
| Format | Details |
|---|---|
| **FITS** | One 3D cube or a numbered sequence - see below |
| Still images | PNG / TIFF (8 and 16 bit), BMP, JPEG |
| Video | AVI (lossless: uncompressed RGB, FFV1 / lossy: Motion JPEG, MPEG-4), MP4 (H.264) |
| Animated GIF | Frame delay, final frame delay, colour count, looping |
| SER | A trimmed and cropped copy; with processing off the pixel values are untouched |

---

## FITS export

![FITS export dialog](docs/images/fits-export.png)

### Pixel values are left alone by default
With *Apply the display processing* **off** (the default), the pixel values
recorded in the SER file are written to the FITS file unchanged. A 12 bit
camera keeps its 0-4095 values, so the result can go straight into stacking or
photometry. Switching it on writes what you see in the player instead, which
destroys the linearity - and says so in the `HISTORY` cards.

### Layout
- **One 3D cube** - monochrome data becomes `(frames, height, width)`. Colour
  data becomes a 4D `(frames, 3, height, width)` cube, which collapses to an
  ordinary `(3, height, width)` RGB image when a single frame is exported.
  Per-frame times go into a `FRAMETIME` binary table extension
  (FRAME / MJD_UTC / DATE_OBS). The cube is streamed to disk, so even a
  multi-gigabyte SER file does not need matching memory.
- **Numbered sequence** - `name_000001.fits`, `name_000002.fits`, … Use this to
  feed AutoStakkert!, RegiStax, Siril, PIPP and similar stacking software.

### Colour handling
- **Raw sensor data (no debayer)** - keeps the Bayer mosaic and writes
  `BAYERPAT`, `XBAYROFF` and `YBAYROFF`. Stacking software normally prefers to
  debayer itself, so this is preselected for Bayer files.
- **Debayered RGB** - `NAXIS3 = 3` with `CTYPE3 = 'RGB'`.
- **Monochrome** - colour or Bayer data collapsed to a single plane.

### Bit depth
`Keep the original depth` / `16 bit unsigned` / `32 bit float (normalised to
0.0-1.0)`. Unsigned 16 bit data is written with `BZERO = 32768` as the FITS
standard requires.

### Header keywords written
| Keyword | Meaning |
|---|---|
| `DATE-OBS` / `MJD-OBS` / `DATE-END` | Frame times in UTC, taken from the SER timestamps |
| `OBSERVER` / `TELESCOP` / `INSTRUME` | From the SER header, editable in the dialog |
| `OBJECT` / `EXPTIME` / `FOCALLEN` / `XPIXSZ` / `YPIXSZ` | Optional, entered in the dialog |
| `BAYERPAT` / `XBAYROFF` / `YBAYROFF` | Raw Bayer export only |
| `ROWORDER` | `TOP-DOWN` by default, `BOTTOM-UP` when the rows are flipped |
| `SERFILE` / `SERFRAME` / `SERCOLID` / `SERDEPTH` / `SERFRAMS` / `NFRAMES` | Provenance of the source file |
| `HISTORY` | States whether the data was processed |

> **About row order:** SER stores the top row of the image first. FITS
> traditionally starts at the bottom, but most astronomy software reads the
> `ROWORDER` keyword (introduced by Siril, understood by PixInsight and others).
> SER Viewer keeps the pixels in place and writes `ROWORDER = 'TOP-DOWN'`. If
> your software shows the image upside down, tick *Store rows bottom-up* in the
> export dialog.

---

## Installation

### Prebuilt binaries
Download them from
[Releases](https://github.com/kiyo-astro/ser-viewer/releases); pushing a tag
builds them automatically.

- **macOS** - `SER-Viewer-<version>-macOS-arm64.dmg` (Apple silicon) or
  `-x86_64.dmg` (Intel). Open the DMG and drag `SER Viewer.app` into
  Applications. The app is unsigned, so Gatekeeper blocks the first launch:
  **right click the app and choose Open**, or allow it under
  System Settings → Privacy & Security.
- **Windows** - `SER-Viewer-<version>-windows-x64.zip`. Unpack it and run
  `SER Viewer.exe`. If SmartScreen appears, choose *More info → Run anyway*.

### Running from source
```bash
git clone https://github.com/kiyo-astro/ser-viewer.git
cd ser-viewer
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m serview            # or: python -m serview path/to/file.ser
```
Python 3.10 or newer is required.

> **Use a venv, not a conda environment.**
> The conda build of OpenCV (`libopencv_highgui`) loads conda's own Qt6, which
> then coexists with the Qt6 that pip's PySide6 brings. With two copies of the
> same Qt classes in one process the application crashes at random - roughly
> one run in three or four in our testing. A venv with
> `opencv-python-headless` does not have the problem, and the prebuilt
> application ships only its own Qt, so it is unaffected.

---

## Using the application

| Action | Shortcut |
|---|---|
| Open a file | `Ctrl/Cmd + O` |
| Play / pause | `Space` (or double click the image) |
| Previous / next frame | `←` / `→` |
| Jump 10 frames | `PageUp` / `PageDown` |
| First / last frame | `Home` / `End` |
| Set start / end marker | `[` / `]` (clear with `Ctrl + [`) |
| Zoom in / out | `Ctrl/Cmd + +` / `-` |
| Actual size / fit to window | `Ctrl/Cmd + 1` / `Ctrl/Cmd + 0` |
| Selection box mode | `Ctrl/Cmd + B` |
| Processing dialog | `Ctrl/Cmd + P` |
| Histogram | `Ctrl/Cmd + H` |
| File details | `Ctrl/Cmd + I` |
| Export to FITS | `Ctrl/Cmd + E` |
| Export images, video or SER | `Ctrl/Cmd + Shift + E` |

**Setting a crop:** press *Use selection box* in the processing dialog and drag
on the image, or press `Ctrl/Cmd + B` to enter selection mode and drag.

**Dialog size:** the processing, FITS export and frame export dialogs shrink to
fit the height of the screen when they open, and their contents scroll. The
buttons stay pinned at the bottom, so they never end up off-screen on a laptop.

![Processing dialog](docs/images/processing.png)

![Histogram](docs/images/histogram.png)

## Troubleshooting

| Symptom | What to do |
|---|---|
| The image is black or very dark | Turn on *Auto stretch each frame* in the processing dialog, or raise the gain and gamma. Files that misreport their bit depth are corrected automatically, but genuinely faint data still needs adjusting |
| Colours look wrong or the image looks like a checkerboard | The Bayer pattern may be misdetected. Force RGGB / GRBG / GBRG / BGGR under *Pattern* in the processing dialog |
| Other software shows the exported FITS upside down | Enable *Store rows bottom-up* in the FITS export dialog |
| Stacking software does not see the colour | Export as *Raw sensor data* so that `BAYERPAT` is written; debayered RGB does not carry it |
| macOS says the developer cannot be verified | Right click the app and choose Open, or allow it under System Settings → Privacy & Security |
| Running from source crashes at random, or `Class Qt... is implemented in both` appears | Two copies of Qt are loaded. Use a venv rather than a conda environment (see *Running from source*) |

---

## SER format support

| Aspect | Support |
|---|---|
| ColorID | MONO (0), Bayer RGGB/GRBG/GBRG/BGGR (8-11), CYYM/YCMY/YMCY/MYYC (16-19), RGB (100), BGR (101) |
| Bit depth | 1-8 bit (1 byte per sample), 9-16 bit (2 bytes per sample) |
| Byte order | Little endian and big endian, including the quirk that `LittleEndian = 1` actually means **big** endian |
| Timestamps | Per-frame timestamps from the trailer; recorders that store local time instead of UTC are detected and corrected |
| Effective bit depth | `PixelDepthPerPlane` is not trusted. The data is scanned to measure the real depth (10, 12, 14 bit …) so the image is displayed at the right brightness |
| Damaged files | If the header claims more frames than the file holds, the count is clamped and a warning is shown |

---

## Development

```bash
python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen pytest -q      # 49 tests
```

Test SER files can be synthesised:
```bash
python tests/tools/make_test_ser.py /tmp/test.ser --width 640 --height 480 \
    --frames 90 --depth 12 --colour BAYER_RGGB
```

### Self-test
```bash
python -m serview --selftest
# it also runs against a packaged build
"./dist/SER Viewer.app/Contents/MacOS/SER Viewer" --selftest
"dist\SER Viewer\SER Viewer.exe" --selftest
```
It writes a SER file to a temporary directory, reads it back, debayers it,
exports FITS and PNG, and starts the Qt interface off-screen. A packaged build
that is missing a library or a Qt plugin fails here, which is why CI runs it
against every artefact it produces - it caught two missing astropy data files
during development.

### Building the distributables
```bash
./packaging/build_macos.sh --venv     # macOS: "dist/SER Viewer.app" and a DMG
packaging\build_windows.bat --venv    # Windows: "dist\SER Viewer\SER Viewer.exe" and a zip
```
`--venv` builds inside a throw-away virtual environment, which keeps whatever
is installed in your everyday environment out of the bundle.

### CI
`.github/workflows/build.yml` does the following:
1. Runs the tests on Ubuntu, macOS and Windows
2. Builds macOS (arm64 and x86_64) and Windows (x64) artefacts and runs the
   self-test against each one
3. Creates a release with the DMGs and the zip attached when a `v*` tag is pushed

### Packaging notes
- `packaging/pyinstaller_hooks/hook-astropy.py` replaces the stock astropy
  hook. The stock hook calls `collect_submodules("astropy")`, which imports
  `astropy.visualization.wcsaxes`; on a build machine without matplotlib that
  **aborts the build itself**.
- Always build with `--venv`, or in a clean environment such as CI. Building
  inside an everyday Anaconda environment pulls in pandas, pyarrow and a second
  Qt, which adds hundreds of megabytes and loads Qt twice.

### Layout
```
serview/
├── ser/          SER reading and writing (format.py / reader.py / writer.py)
├── imaging/      debayer, tone and colour processing, histogram
├── export/       fits.py / images.py / video.py / ser.py
└── ui/           the Qt (PySide6) interface
```

---

## Credits

Application developed by Kiyoaki Okudaira - Kyushu University Hanada Lab
(Space Systems Dynamics)

Supported by JSPS KAKENHI Grant Number JP26H02172.

## License

MIT License.

Inspired by SER Player by Chris Garry (GPL-3.0); no code was taken from it,
this is an independent implementation. The SER format follows the public
specification by Heiko Wilkens and Grischa Hahn. Built with PySide6 / Qt,
NumPy, OpenCV, Astropy and Pillow.
