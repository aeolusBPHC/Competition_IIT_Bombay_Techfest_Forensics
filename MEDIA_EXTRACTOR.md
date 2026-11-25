# Platform-independent media extraction

```bash
python -m media.extractor --input <dir | media file | sdcard.img> --output repository/cases/CASE-004/analysis/media_report.json
```

Install FFmpeg to enable video frame indexing on Ubuntu/Debian:

```bash
sudo apt install ffmpeg
ffprobe -version
```

Choose the sample interval with `--frame-interval-s`; for example, `--frame-interval-s 2`
indexes about one frame every two seconds. Use `--frame-interval-s 0` to index every
decoded frame, which may make the JSON report large.

When FFmpeg is installed, indexed frames also get small, rotation-aware JPEG
previews encoded in the JSON. Each frame timeline records the source evidence
path and SHA-256. Tune review thresholds with `--position-disagreement-m`,
`--max-ground-speed-m-s`, and `--max-vertical-speed-m-s`; defaults are 50 m,
100 m/s, and 60 m/s. The values used are recorded in the report.

The input can be a mounted (write-blocked) card, an extraction directory, one
file, or a raw `dd` image. Images are processed with The Sleuth Kit, which
recovers both allocated and deleted-but-recoverable files. The report states
`media_present: false` when there is nothing to extract.

For raw disk images, the extractor also runs `fls` and adds a
`filesystem_timeline` to the JSON report. It preserves allocated and deleted
directory entries and records filesystem `atime`, `mtime`, `ctime`, and
`crtime` values when present. The main HTML case report renders a bounded event
table and shows entry counts. A deleted directory entry is marked as deleted;
the report does not infer a deletion time from the other timestamp fields.
Timestamps are filesystem observations rendered as UTC from Sleuth Kit epoch
values; device clock, timezone interpretation, timestamp resolution, filesystem
semantics, and access-time behavior can limit what they mean. `fsstat` adds
FAT, exFAT, or NTFS-specific precision/semantics notes when identifiable. FAT
commonly has two-second modification precision and date-only access times. The
media extractor does not write to the image. This feature requires The Sleuth
Kit (`fls`, `mmls`, `fsstat`, and `tsk_recover`).

## What makes it platform-independent

| Layer | How |
|---|---|
| Finding media | Magic bytes (JPEG, PNG, TIFF/DNG, HEIF, MP4/MOV, AVI, SRT), never extension or vendor. Renamed files are found and flagged. |
| Position, time, make, serials | Standard EXIF/TIFF tags, identical for every manufacturer. |
| Drone telemetry | XMP matched by *local name* through an alias table (`media/normalize.py`). |
| Video | ISO-BMFF box walk (`mvhd` time and duration, ISO-6709 location); sampled frame presentation-time index; embedded GoPro GPMF and DJI `djmd` telemetry when decodable. |
| Frame telemetry | `.SRT` sidecars in all observed DJI variants, linked to their video. |

Matching XMP by local name rather than by vendor namespace matters in practice.
The real Autel EVO II sample writes its telemetry under **DJI's** namespace,
including DJI's misspelling `GpsLongtitude`. Supporting a new vendor spelling
means adding one alias.

Every normalized value records its source tag, for example
`XMP:{http://www.dji.com/drone-dji/1.0/}RelativeAltitude`. Every file is
SHA-256 hashed, and the report gets a `.sha256` sidecar.

Each video report includes `frame_timeline`: one entry per interval (one second
by default), with decoded frame number, presentation timestamp (`pts_s`), offset
from the first timed frame (`offset_s`), key-frame status, and dimensions. Set
`--frame-interval-s 0` to index every decoded frame. Indexing requires `ffprobe`
(usually installed with FFmpeg); without it, the report records an unavailable
status and warning. These timestamps are on the video media clock, not wall-clock
capture times. The source video is read-only.

The same video item includes `embedded_telemetry`. `ffprobe` identifies MP4
tracks tagged `gpmd` (GoPro GPMF), `djmd` (DJI timed metadata), or `dbgi` (DJI
debug metadata). GoPro GPMF KLV packets are demuxed by FFmpeg and decoded by the
included parser for GPS5/GPS9, GPS time, accelerometer, and gyroscope streams;
ExifTool supplies normalized metadata when available. DJI `djmd`/`dbgi`
decoding is delegated to ExifTool's `-ee3` parser. Each result retains its
source track and clock basis. GPMF sensor values include source axis order,
scale, and units when established. Altitude datum and any unrecognized units
remain explicitly unknown. Per-sample timing is not shifted onto wall-clock or
frame time, and accelerometer/gyro vectors are not rotated into camera/world
coordinates.

Install FFmpeg and ExifTool. DJI `djmd` decoding needs ExifTool 13.05 or newer;
later camera protocols may need a newer release. GoPro GPMF decoding needs both
`ffprobe` and `ffmpeg`. If a tool is missing or a stream is unsupported, the
report records the status and warning instead of inventing telemetry.

## Media anomaly report

Each item includes an `anomalies` list, and the case summary includes
`anomaly_count` and `media_with_anomalies`. Findings cover gaps in indexed video
presentation times and SRT/embedded telemetry clocks, unusually fast movement
between time-aligned GPS fixes, and location disagreement among EXIF, XMP,
QuickTime container metadata, and a single embedded telemetry fix. Existing
EXIF/XMP make, position, and camera-clock flags are included in the same list.
Every finding records the source, measurements, thresholds, and relevant clock
basis where available. These are review flags, not conclusions about alteration.

Telemetry samples whose clock bases differ are not compared. A multi-sample
embedded GPS track is not compared directly with a file-level location because
the aircraft may have moved and the sources may not be time-aligned. Timing gaps
are measured on the relevant media or telemetry clock and are not interpreted
as wall-clock capture gaps.

## Evidence gallery in the HTML case report

The normalized HTML case report automatically looks for
`repository/cases/<CASE-ID>/analysis/media_report.json` (and a report beside
its input/output files). You can also pass `--media-report` to link a report
stored elsewhere. The **Evidence Gallery** shows still images, playable video
files, metadata and hash details, per-finding values, and seek buttons with frame
previews. Disk-image reports also include a **Removable-media Timeline** table.
Pass `--portable-media` to copy hash-verified files beside the HTML into
`<report-stem>_assets/`; these report derivatives leave source evidence untouched.
Keep the HTML and assets directory together. Large videos may require substantial
additional disk space.

The DJI flight-record CSV paired with the Zenodo video is not currently a
registered flight-log format. The media report and Evidence Gallery analyze
the MOV, but they do not parse or correlate that CSV with the video. For the
main flight-analysis sections, use a log format supported by the parser
registry and link the media JSON separately.

```bash
python -m media.extractor \
  --input repository/cases/CASE-004/evidence_media \
  --output repository/cases/CASE-004/analysis/media_report.json

python -m reporting.normalized_report_generator \
  --input repository/cases/CASE-004/analysis/normalized_report.json \
  --output repository/cases/CASE-004/reports/forensic_report.html \
  --media-report repository/cases/CASE-004/analysis/media_report.json

# Add verified media copies beside the HTML for a portable report package:
python -m reporting.normalized_report_generator \
  --input repository/cases/CASE-004/analysis/normalized_report.json \
  --output repository/cases/CASE-004/reports/forensic_report.html \
  --media-report repository/cases/CASE-004/analysis/media_report.json \
  --portable-media
```

To run the optional hash-pinned GoPro GPMF integration test, provide the public
Hero5 sample from the official GoPro parser repository as `GPMF_SAMPLE`:

```bash
curl -L https://raw.githubusercontent.com/gopro/gpmf-parser/main/samples/hero5.mp4 -o /tmp/hero5.mp4
GPMF_SAMPLE=/tmp/hero5.mp4 python -m pytest -q tests/media/test_gpmf.py
```

The test verifies the sample SHA-256 before running and checks that GPS5,
accelerometer, and gyroscope streams decode.

On Ubuntu/Debian, the package is `libimage-exiftool-perl`:

```bash
sudo apt install libimage-exiftool-perl
exiftool -ver
```

Check the version before analyzing DJI `djmd`; some distribution packages are
older than the minimum and need a current ExifTool release.

## Forensic safeguards

- **SRT positional `GPS(a, b, c)` has no fixed axis order.** Mavic Pro writes
  longitude first and Matrice 300 writes latitude first. The order is resolved
  from the values (a coordinate beyond ±90° can only be a longitude) or from
  keyed frames in the same file. Otherwise latitude/longitude stay `None`, the
  raw pair is kept, and a warning is issued. Use `--srt-gps-axis-order` only
  after checking against another source.
- **Cross-checks are observations, not conclusions:**
  - `EXIF_XMP_POSITION_DISAGREE` (more than 50 m apart);
  - `EXIF_XMP_MAKE_DISAGREE`;
  - `CAMERA_CLOCK_IRREGULAR_OFFSET` (the camera clock is not a whole
    time-zone offset from GPS UTC, ±60 s).
- **Deleted files** are labelled `image_deleted`, with a note that their
  content may be partly overwritten.
- **Timestamps.** GPS records are created only with a GPS-UTC time base (photos)
  or a video-relative time base (SRT frames). Camera clocks and the SRT device
  time (whose time zone is not recorded) stay in `raw`.

## Validation

- **Synthetic tests:** 25, covering EXIF signs, both XMP forms, malformed XMP,
  every SRT variant, the MP4 box parser, truncated files, and a FAT32 image
  with a deleted file.
- **Real samples:** 13 more tests run on open data, fetched and hash-verified
  with `tools/fetch_media_samples.sh`:
  - 8 photos from OpenDroneMap datasets (DJI Phantom 3, Autel EVO II, senseFly
    eBee payloads, plain cameras). All positions, altitudes, makes and XMP
    telemetry values match ExifTool exactly.
  - 20 DJI `.SRT` files from 18 models, including broken ones.

For full-card evidence, the **VTO Labs Drone Forensic Program** images on NIST
CFReDS (63 drones, 25 models: DJI, Parrot, Yuneec, Skydio and others) are the
reference dataset. They are hosted on NIST and were not reachable from the
build environment, so they have **not yet** been run.

## Not decoded (stated limits)

- Vendor MakerNotes, whose presence is recorded only.
- Embedded telemetry details that the installed ExifTool version does not decode.
- HEIF EXIF (the file is found and hashed, but Pillow does not read HEIF metadata).
- Encrypted DJI app flight records.

## Dependencies

- Optional video frame indexing: `ffprobe` (FFmpeg).
- Optional embedded video telemetry decoding: `ffprobe`, `ffmpeg`, and ExifTool
  (ExifTool is needed for DJI telemetry and normalized metadata).

- Python: `pillow`.
- For disk images: `sleuthkit`.
- For the disk-image test: `dosfstools` and `mtools`.
