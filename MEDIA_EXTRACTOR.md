# Platform-independent media extraction

```bash
python -m media.extractor --input <dir | media file | sdcard.img> --output repository/cases/CASE-004/analysis/media_report.json
```

The input can be a mounted (write-blocked) card, an extraction directory, one
file, or a raw `dd` image. Images are processed with The Sleuth Kit, which
recovers both allocated and deleted-but-recoverable files. The report states
`media_present: false` when there is nothing to extract.

## What makes it platform-independent

| Layer | How |
|---|---|
| Finding media | Magic bytes (JPEG, PNG, TIFF/DNG, HEIF, MP4/MOV, AVI, SRT), never extension or vendor. Renamed files are found and flagged. |
| Position, time, make, serials | Standard EXIF/TIFF tags, identical for every manufacturer. |
| Drone telemetry | XMP matched by *local name* through an alias table (`media/normalize.py`). |
| Video | ISO-BMFF box walk (`mvhd` time and duration, ISO-6709 location). |
| Frame telemetry | `.SRT` sidecars in all observed DJI variants, linked to their video. |

Matching XMP by local name rather than by vendor namespace matters in practice.
The real Autel EVO II sample writes its telemetry under **DJI's** namespace,
including DJI's misspelling `GpsLongtitude`. Supporting a new vendor spelling
means adding one alias.

Every normalized value records its source tag, for example
`XMP:{http://www.dji.com/drone-dji/1.0/}RelativeAltitude`. Every file is
SHA-256 hashed, and the report gets a `.sha256` sidecar.

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
- Embedded video GPS tracks (GoPro GPMF, DJI `djmd`).
- HEIF EXIF (the file is found and hashed, but Pillow does not read HEIF metadata).
- Encrypted DJI app flight records.

## Dependencies

- Python: `pillow`.
- For disk images: `sleuthkit`.
- For the disk-image test: `dosfstools` and `mtools`.
