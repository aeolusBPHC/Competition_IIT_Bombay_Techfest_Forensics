"""
Tests for platform-independent media extraction.

Synthetic fixtures are built inside the tests (no files to ship). The
real-world tests run only when MEDIA_SAMPLES_DIR points at samples fetched
with tools/fetch_media_samples.sh; their expected values were taken from
ExifTool 12.x output on the same files.
"""

from __future__ import annotations

import io
import os
import shutil
import struct
import subprocess
from datetime import datetime, timezone

import pytest
from PIL import Image

from media import signatures, srt, video, xmp
from media.extractor import MediaExtractor, to_gps_records
from media.normalize import normalize

DJI_NS = "http://www.dji.com/drone-dji/1.0/"


# ------------------------------------------------------------------ helpers
def _dms(value: float):
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = round(((value - d) * 60 - m) * 60, 4)
    return (float(d), float(m), float(s))


def make_jpeg(make="TestMake", model="TestModel", lat=None, lon=None, alt=None,
              dto=None, gps_date=None, gps_time=None, xmp_packet: bytes | None = None) -> bytes:
    img = Image.new("RGB", (16, 16), (120, 130, 140))
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = make, model
    if dto:
        exif.get_ifd(0x8769)[0x9003] = dto
    if lat is not None:
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2] = ("N" if lat >= 0 else "S"), _dms(lat)
        gps[3], gps[4] = ("E" if lon >= 0 else "W"), _dms(lon)
        if alt is not None:
            gps[5], gps[6] = 0, float(alt)
        if gps_date:
            gps[29], gps[7] = gps_date, gps_time
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    data = buf.getvalue()
    if xmp_packet:
        payload = b"http://ns.adobe.com/xap/1.0/\x00" + xmp_packet
        seg = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
        data = data[:2] + seg + data[2:]
    return data


def dji_style_xmp(**props) -> bytes:
    attrs = " ".join(f'drone:{k}="{v}"' for k, v in props.items())
    return (f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            f'<rdf:Description rdf:about="" xmlns:drone="{DJI_NS}" {attrs}/></rdf:RDF></x:xmpmeta>').encode()


def element_style_xmp() -> bytes:
    return b"""<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
<rdf:Description rdf:about='' xmlns:sf='http://ns.example.com/fixedwing/1.0/'>
<sf:AutopilotSN>AP-1234</sf:AutopilotSN><sf:Height>66.1</sf:Height><sf:Heading>70.0</sf:Heading>
<sf:BandName><rdf:Seq><rdf:li>Red</rdf:li><rdf:li>Green</rdf:li></rdf:Seq></sf:BandName>
</rdf:Description></rdf:RDF></x:xmpmeta>"""


def make_mp4(creation_1904: int = 3743229600, iso6709: bytes = b"+47.6437+016.4759+513.000/") -> bytes:
    def box(t, b):
        return struct.pack(">I", 8 + len(b)) + t + b
    mvhd = box(b"mvhd", b"\x00" * 4 + struct.pack(">IIII", creation_1904, creation_1904, 1000, 65000) + b"\x00" * 80)
    xyz = box(b"\xa9xyz", struct.pack(">HH", len(iso6709), 0x15C7) + iso6709)
    return box(b"ftyp", b"isom\x00\x00\x02\x00isommp41") + box(b"moov", mvhd + box(b"udta", xyz)) + box(b"mdat", b"\x00" * 64)


KEYED_SRT = """1
00:00:00,000 --> 00:00:00,033
<font size="36">FrameCnt : 1, DiffTime : 33ms
2022-05-01 15:01:58,531,716
[iso : 100] [latitude: 41.420684] [longitude: 2.162162] [rel_alt: 12.5 abs_alt: 140.2] </font>

2
00:00:00,033 --> 00:00:00,066
<font size="36">FrameCnt : 2, DiffTime : 33ms
2022-05-01 15:01:58,564,000
[iso : 100] [latitude: 41.420700] [longtitude: 2.162200] [rel_alt: 12.6 abs_alt: 140.3] </font>
"""
LON_LAT_SRT = """1
00:00:01,000 --> 00:00:02,000
HOME(149.0251,-20.2532) 2017.08.05 14:11:51
GPS(149.0251,-20.2533,16) BAROMETER:1.9
"""
AMBIGUOUS_SRT = """1
00:00:00,000 --> 00:00:01,000
2022.06.21 16:06:17
GPS(36.6146,-6.1120,0.0M) BAROMETER:0.3M
"""


# ------------------------------------------------------------ signatures
def test_detection_is_by_content_not_extension(tmp_path):
    (tmp_path / "notes.txt").write_bytes(make_jpeg())
    (tmp_path / "telemetry").write_text(KEYED_SRT)
    (tmp_path / "readme.txt").write_text("plain text, not media")
    report = MediaExtractor(tmp_path).extract()
    kinds = {i["path"]: (i["format"], i["extension_matches_content"]) for i in report["items"]}
    assert kinds == {"notes.txt": ("JPEG", False), "telemetry": ("SRT", False)}
    assert report["summary"]["extension_mismatches"] == 2


def test_disk_image_signature():
    boot = bytearray(512)
    boot[510:512] = b"\x55\xaa"
    assert signatures.looks_like_disk_image(bytes(boot))
    assert not signatures.looks_like_disk_image(b"\x00" * 512)


# ------------------------------------------------------------ images
def test_exif_gps_signs_and_values(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(make_jpeg(lat=-34.650200, lon=-59.409424, alt=123.4))
    f = MediaExtractor(p).extract()["items"][0]["metadata"]["fields"]
    assert f["latitude"]["value"] == pytest.approx(-34.650200, abs=1e-6)
    assert f["longitude"]["value"] == pytest.approx(-59.409424, abs=1e-6)
    assert f["gps_altitude_m"]["value"] == pytest.approx(123.4)
    assert f["latitude"]["source"] == "EXIF:GPSLatitude"


def test_vendor_neutral_xmp_matching_by_local_name(tmp_path):
    # Another vendor writing DJI's namespace, including DJI's "Longtitude" typo.
    packet = dji_style_xmp(RelativeAltitude="+49.98", GimbalYawDegree="-149.39",
                           FlightYawDegree="-148.96", GpsLatitude="47.6436873", GpsLongtitude="16.4759271")
    p = tmp_path / "MAX_0002.JPG"
    p.write_bytes(make_jpeg(make="Autel Robotics\x00\x00\x00", model="XT705", xmp_packet=packet))
    md = MediaExtractor(p).extract()["items"][0]["metadata"]
    f = md["fields"]
    assert f["make"]["value"] == "Autel Robotics"                      # NUL padding stripped
    assert f["relative_altitude_m"]["value"] == pytest.approx(49.98)
    assert f["camera_yaw_deg"]["value"] == pytest.approx(-149.39)
    assert f["longitude"]["value"] == pytest.approx(16.4759271)
    assert f["longitude"]["source"] == f"XMP:{{{DJI_NS}}}GpsLongtitude"
    assert md["drone_telemetry_present"] is True


def test_element_form_xmp_with_serials_and_lists():
    props = xmp.extract(element_style_xmp())
    md = normalize({"tags": {}, "gps": {}}, props)
    assert md["serial_numbers"] == {"XMP:{http://ns.example.com/fixedwing/1.0/}AutopilotSN": "AP-1234"}
    assert md["fields"]["relative_altitude_m"]["value"] == pytest.approx(66.1)
    assert md["fields"]["aircraft_yaw_deg"]["value"] == pytest.approx(70.0)
    assert any(p.local_name == "BandName" and p.value == ["Red", "Green"] for p in props)


def test_malformed_xmp_is_salvaged():
    broken = b'<x:xmpmeta><rdf:Description drone:RelativeAltitude="+12.5" <broken></x:xmpmeta>'
    props = xmp.extract(broken)
    assert any(p.local_name == "RelativeAltitude" and p.value == "+12.5" for p in props)


def test_exif_xmp_position_disagreement_is_flagged(tmp_path):
    packet = dji_style_xmp(GpsLatitude="47.70", GpsLongitude="16.47")
    p = tmp_path / "x.jpg"
    p.write_bytes(make_jpeg(lat=47.6436873, lon=16.4759271, xmp_packet=packet))
    md = MediaExtractor(p).extract()["items"][0]["metadata"]
    flag = next(f for f in md["flags"] if f["flag"] == "EXIF_XMP_POSITION_DISAGREE")
    assert 6000 < flag["distance_m"] < 7000
    assert md["fields"]["latitude"]["source"] == "EXIF:GPSLatitude"   # EXIF keeps priority


@pytest.mark.parametrize("local,utc,flagged", [
    ("2014:10:19 13:20:51", ("2014:10:19", (18.0, 20.0, 51.0)), False),   # exactly -5 h
    ("2016:10:25 08:20:13", ("2016:10:25", (12.0, 21.0, 39.934)), True),  # -4 h and 86 s drift
])
def test_camera_clock_offset(tmp_path, local, utc, flagged):
    p = tmp_path / "c.jpg"
    p.write_bytes(make_jpeg(lat=41.0, lon=-81.0, dto=local, gps_date=utc[0], gps_time=utc[1]))
    md = MediaExtractor(p).extract()["items"][0]["metadata"]
    assert any(f["flag"] == "CAMERA_CLOCK_IRREGULAR_OFFSET" for f in md["flags"]) is flagged


def test_zero_zero_gps_is_not_a_position(tmp_path):
    p = tmp_path / "z.jpg"
    p.write_bytes(make_jpeg(lat=0.0, lon=0.0))
    assert "latitude" not in MediaExtractor(p).extract()["items"][0]["metadata"]["fields"]


# ------------------------------------------------------------ SRT
def test_srt_keyed_format_including_typo():
    t = srt.parse_text(KEYED_SRT)
    assert t.gps_axis_order == "keyed"
    assert [(f.latitude, f.longitude) for f in t.frames] == [(41.420684, 2.162162), (41.4207, 2.1622)]
    assert t.frames[0].relative_altitude_m == 12.5 and t.frames[0].absolute_altitude_m == 140.2
    assert t.frames[0].device_time == "2022-05-01T15:01:58.531"
    assert t.frames[1].start_s == pytest.approx(0.033)


def test_srt_positional_order_proven_by_value_range():
    t = srt.parse_text(LON_LAT_SRT)
    assert (t.gps_axis_order, t.gps_axis_order_source) == ("lon_lat", "value_range")
    assert (t.frames[0].latitude, t.frames[0].longitude) == (-20.2533, 149.0251)
    assert t.frames[0].positional_gps_third == "16"    # meaning not assumed
    assert t.frames[0].barometric_height_m == 1.9


def test_srt_ambiguous_order_is_refused_not_guessed():
    t = srt.parse_text(AMBIGUOUS_SRT)
    assert t.gps_axis_order == "ambiguous"
    assert t.frames[0].latitude is None and t.frames[0].positional_gps == (36.6146, -6.112)
    assert t.frames[0].altitude_m == 0.0                # explicit "M" unit
    assert any("not assigned" in w for w in t.warnings)


def test_srt_examiner_override():
    t = srt.parse_text(AMBIGUOUS_SRT, gps_axis_order="lat_lon")
    assert (t.frames[0].latitude, t.frames[0].longitude) == (36.6146, -6.112)
    assert t.gps_axis_order_source == "examiner_override"


def test_srt_mixed_file_resolved_by_keyed_frames():
    mixed = KEYED_SRT.replace("41.420684", "-34.651180").replace("2.162162", "-59.409483") + """
3
00:00:02,000 --> 00:00:03,000
GPS (-59.409424, -34.650200, 16), H 17.39m, H.S 1.84m/s, F.PRY (-8.9°, 2.9°, -75.0°)
"""
    t = srt.parse_text(mixed)
    assert (t.gps_axis_order, t.gps_axis_order_source) == ("lon_lat", "keyed_frames_in_same_file")
    last = t.frames[-1]
    assert (last.latitude, last.longitude) == (-34.6502, -59.409424)
    assert last.height_m == 17.39 and last.horizontal_speed_m_s == 1.84
    assert last.aircraft_pitch_roll_yaw == (-8.9, 2.9, -75.0)


@pytest.mark.parametrize("text", ["", "1\n", "\ufeff1\n00:00:00,000 --> 00:00:01,000\n"])
def test_srt_broken_files_do_not_crash(text):
    t = srt.parse_text(text)
    assert all(f.latitude is None for f in t.frames) and t.warnings


# ------------------------------------------------------------ video
def test_mp4_container_metadata_and_sidecar_link(tmp_path):
    (tmp_path / "DJI_0100.MP4").write_bytes(make_mp4())
    (tmp_path / "DJI_0100.SRT").write_text(KEYED_SRT)
    report = MediaExtractor(tmp_path).extract()
    v = next(i for i in report["items"] if i["kind"] == "video")
    f = v["metadata"]["fields"]
    assert f["capture_time_utc"]["value"] == "2022-08-13T10:00:00+00:00"
    assert f["duration_s"]["value"] == 65.0
    assert f["latitude"]["value"] == pytest.approx(47.6437)
    assert v["sidecars"] == ["DJI_0100.SRT"]


def test_truncated_video_does_not_crash(tmp_path):
    p = tmp_path / "cut.mp4"
    p.write_bytes(make_mp4()[:40])
    assert MediaExtractor(p).extract()["media_present"] is True


def test_iso6709_rejects_out_of_range():
    assert video.parse_iso6709("+95.0000+016.0000/") is None


# ------------------------------------------------------------ report / records
def test_no_media_present(tmp_path):
    (tmp_path / "a.txt").write_text("nothing here")
    report = MediaExtractor(tmp_path).extract()
    assert report["media_present"] is False and report["items"] == []
    assert MediaExtractor.identify(tmp_path)["supported"] is False


def test_every_item_is_hashed(tmp_path):
    data = make_jpeg()
    (tmp_path / "a.jpg").write_bytes(data)
    import hashlib
    item = MediaExtractor(tmp_path).extract()["items"][0]
    assert item["sha256"] == hashlib.sha256(data).hexdigest()


def test_gps_records_utc_and_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    (tmp_path / "utc.jpg").write_bytes(make_jpeg(lat=41.0, lon=-81.0, gps_date="2016:10:25",
                                                 gps_time=(12.0, 21.0, 39.0)))
    (tmp_path / "noutc.jpg").write_bytes(make_jpeg(lat=41.0, lon=-81.0))
    (tmp_path / "t.srt").write_text(KEYED_SRT)
    records, skipped = to_gps_records(MediaExtractor(tmp_path).extract())
    photo = next(r for r in records if r.raw.get("timestamp_basis") == "gps_utc")
    assert datetime.fromtimestamp(photo.timestamp, timezone.utc).isoformat() == "2016-10-25T12:21:39+00:00"
    assert skipped == 1                                  # position without GPS time
    assert sum(r.source_platform == "Media:SRT" for r in records) == 2


# ------------------------------------------------------------ disk image
TOOLS = all(shutil.which(t) for t in ("tsk_recover", "mmls", "mkfs.vfat", "mcopy", "mdel"))


@pytest.mark.skipif(not TOOLS, reason="needs sleuthkit, dosfstools and mtools")
def test_disk_image_allocated_and_deleted(tmp_path):
    img = tmp_path / "card.img"
    subprocess.run(["dd", "if=/dev/zero", f"of={img}", "bs=1M", "count=33", "status=none"], check=True)
    subprocess.run(["mkfs.vfat", "-F", "32", str(img)], check=True, capture_output=True)
    env = {**os.environ, "MTOOLS_SKIP_CHECK": "1"}
    keep, gone = tmp_path / "keep.jpg", tmp_path / "gone.jpg"
    keep.write_bytes(make_jpeg(make="Keep"))
    gone.write_bytes(make_jpeg(make="Gone", lat=10.0, lon=20.0))
    subprocess.run(["mcopy", "-i", str(img), str(keep), "::/KEEP.JPG"], check=True, env=env)
    subprocess.run(["mcopy", "-i", str(img), str(gone), "::/GONE.JPG"], check=True, env=env)
    subprocess.run(["mdel", "-i", str(img), "::/GONE.JPG"], check=True, env=env)

    report = MediaExtractor(img).extract()
    assert report["input"]["type"] == "disk_image" and report["input"]["sha256"]
    origins = {i["metadata"]["fields"]["make"]["value"]: i["origin"] for i in report["items"]}
    assert origins == {"Keep": "image_allocated", "Gone": "image_deleted"}
    import hashlib
    deleted = next(i for i in report["items"] if i["origin"] == "image_deleted")
    assert deleted["sha256"] == hashlib.sha256(gone.read_bytes()).hexdigest()


# ------------------------------------------------------------ real samples
SAMPLES = os.environ.get("MEDIA_SAMPLES_DIR")
needs_samples = pytest.mark.skipif(not SAMPLES, reason="set MEDIA_SAMPLES_DIR (tools/fetch_media_samples.sh)")

# Expected values from ExifTool on the same files (exiftool -n).
EXIFTOOL_TRUTH = {
    "helenenschacht_MAX_0002.JPG": {"make": "Autel Robotics", "latitude": 47.6436873207778,
                                    "longitude": 16.4759271684167, "gps_altitude_m": 512.99768,
                                    "relative_altitude_m": 49.98, "camera_yaw_deg": -149.39},
    "toledo_1JI_0062.JPG": {"make": "DJI", "latitude": 41.5490988333333, "longitude": -83.6989743611111,
                            "gps_altitude_m": 122.3},
    "zoo_DSC01605.JPG": {"make": "SONY", "latitude": 41.4423440833333, "longitude": -81.7163142222222,
                         "gps_altitude_m": 303.018},
    "bellus_IMG_1297_RGB.jpg": {"make": "Canon", "latitude": 41.2256725199861, "longitude": -81.702534789995},
    "caliterra_IMG_9354.jpg": {"make": "Canon", "latitude": 30.1712233333333, "longitude": -98.0899916666667},
    "seneca_IMG_0446.jpg": {"make": "Canon", "latitude": 41.0346708, "longitude": -83.3057253000056},
    "langley_IMG_0525.jpg": {"make": "Canon", "latitude": None},
    "copr_IMG_0022.jpg": {"make": "Canon", "latitude": None},
}


@needs_samples
def test_real_images_match_exiftool():
    report = MediaExtractor(os.path.join(SAMPLES, "odm")).extract()
    items = {os.path.basename(i["path"]): i["metadata"]["fields"] for i in report["items"]}
    assert set(items) == set(EXIFTOOL_TRUTH)
    for name, expected in EXIFTOOL_TRUTH.items():
        for key, value in expected.items():
            got = items[name].get(key, {}).get("value")
            if value is None or isinstance(value, str):
                assert got == value, (name, key)
            else:
                assert got == pytest.approx(value, abs=1e-6), (name, key)


@needs_samples
def test_real_images_platform_independent_telemetry():
    report = MediaExtractor(os.path.join(SAMPLES, "odm")).extract()
    by_name = {os.path.basename(i["path"]): i["metadata"] for i in report["items"]}
    assert by_name["seneca_IMG_0446.jpg"]["serial_numbers"]  # senseFly autopilot/frame serials
    drone = {n for n, m in by_name.items() if m["drone_telemetry_present"]}
    assert drone == {"helenenschacht_MAX_0002.JPG", "bellus_IMG_1297_RGB.jpg",
                     "zoo_DSC01605.JPG", "seneca_IMG_0446.jpg"}
    zoo_flags = [f["flag"] for f in by_name["zoo_DSC01605.JPG"]["flags"]]
    assert zoo_flags == ["CAMERA_CLOCK_IRREGULAR_OFFSET"]


SRT_EXPECTED = {  # file: (frames, frames_with_position, axis order)
    "MAVIC3.srt": (12318, 12318, "keyed"), "air2s.srt": (17, 17, "keyed"),
    "mavic_pro.SRT": (468, 468, "lon_lat"), "old_format.SRT": (468, 468, "lon_lat"),
    "mavic_mini.SRT": (117, 117, "lon_lat"), "Mini_SE.SRT": (8148, 8148, "lon_lat"),
    "mix_p4rtk_mavic2pro.srt": (12, 12, "lon_lat"), "matrice_300.srt": (381, 0, "ambiguous"),
    "p4_rtk.SRT": (55, 0, "ambiguous"), "mavic_air.SRT": (2, 0, "keyed"),
    "broken_empty.SRT": (0, 0, "not_applicable"),
}


@needs_samples
@pytest.mark.parametrize("name", sorted(SRT_EXPECTED))
def test_real_srt_files(name):
    s = srt.summarize(srt.parse_file(os.path.join(SAMPLES, "srt", name)))
    assert (s["frame_count"], s["frames_with_position"], s["gps_axis_order"]) == SRT_EXPECTED[name]
