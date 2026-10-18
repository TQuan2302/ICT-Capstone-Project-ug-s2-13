from pathlib import Path
from datetime import datetime, timezone
import re
import subprocess
import sys

def get_exiftool_path():
    if getattr(sys, 'frozen', False):
        # Running as bundled exe on Windows
        base = Path(sys._MEIPASS)
        return str(base / 'exiftool.exe')
    # Running in development (Linux/Mac) - use system exiftool
    return 'exiftool'

def infer_fallback_date(video_path):
    """
    Try to infer the real date from filenames like:
    FILE230923-151719-001998F.MOV

    That becomes:
    2023:09:23

    If the filename does not contain that pattern, use file modified date
    as a last fallback.
    """
    video_path = Path(video_path)
    name = video_path.name

    match = re.search(r"FILE(\d{2})(\d{2})(\d{2})-", name)

    if match:
        yy, mm, dd = match.groups()
        return f"20{yy}:{mm}:{dd}"

    return datetime.fromtimestamp(
        video_path.stat().st_mtime,
        tz=timezone.utc
    ).strftime("%Y:%m:%d")


def parse_time_generic(time_str, fallback_date_str):
    """
    Some MOV GPS entries may have a broken date like:
    2000:00:00 15:17:19Z

    In that case, we keep the time part and use the date from the filename.
    """
    time_str = time_str.strip()

    if time_str.startswith("2000:00:00 "):
        time_part = time_str.split(" ", 1)[1]
        time_str = f"{fallback_date_str} {time_part}"

    formats = [
        "%Y:%m:%d %H:%M:%SZ",
        "%Y:%m:%d %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(time_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    raise ValueError(f"Unsupported GPS time format: {repr(time_str)}")


def dms_to_decimal(dms_str):
    """
    Convert ExifTool GPS format into decimal degrees.

    Example:
    34 deg 55' 12.34" S
    """
    dms_str = dms_str.strip()

    match = re.match(
        r'(\d+(?:\.\d+)?)\s+deg\s+(\d+(?:\.\d+)?)\'\s+([\d.]+)"\s+([NSEW])',
        dms_str
    )

    if not match:
        return None

    deg = float(match.group(1))
    minutes = float(match.group(2))
    seconds = float(match.group(3))
    direction = match.group(4)

    decimal = deg + minutes / 60 + seconds / 3600

    if direction in ("S", "W"):
        decimal *= -1

    return decimal


def extract_mov_gps_points(video_path):
    """
    Extract GPS points from the original MOV file using ExifTool.

    Returns a list like:
    [
        {
            "time": datetime object,
            "latitude": -34.9,
            "longitude": 138.6,
            "elevation": "...",
            "speed": "...",
            "track": "..."
        }
    ]
    """
    video_path = Path(video_path).resolve()
    fallback_date_str = infer_fallback_date(video_path)
    exiftool_path = get_exiftool_path()
    cmd = [
        exiftool_path,
        "-api", "LargeFileSupport=1",
        "-ee",
        "-u",
        "-a",
        "-G3",
        "-s",
        str(video_path)
    ]

    try:
        
        run_kwargs = {
            'capture_output': True,
            'text': True,
        }
        
        # Only set cwd when running as bundled Windows exe
        if getattr(sys, 'frozen', False):
            run_kwargs['cwd'] = str(Path(exiftool_path).parent)
        
        result = subprocess.run(cmd, **run_kwargs)
        
    except FileNotFoundError:
        raise RuntimeError("ExifTool was not found. Please install ExifTool and make sure it is in PATH.")

    lines = result.stdout.splitlines()

    patterns = {
        "time": re.compile(r"GPSDateTime\s+:\s+(.+)"),
        "latitude": re.compile(r"GPSLatitude\s+:\s+(.+)"),
        "longitude": re.compile(r"GPSLongitude\s+:\s+(.+)"),
        "speed": re.compile(r"GPSSpeed\s+:\s+(.+)"),
        "track": re.compile(r"GPSTrack\s+:\s+(.+)"),
        "elevation": re.compile(r"GPSAltitude\s+:\s+(.+)"),
    }

    gps_points = []

    current = {
        "time": None,
        "latitude": None,
        "longitude": None,
        "elevation": "",
        "speed": "",
        "track": "",
    }

    def save_current_point():
        if (
            current["time"] is not None
            and current["latitude"] is not None
            and current["longitude"] is not None
        ):
            gps_points.append({
                "time": current["time"],
                "latitude": current["latitude"],
                "longitude": current["longitude"],
                "elevation": current["elevation"],
                "speed": current["speed"],
                "track": current["track"],
            })

    for line in lines:
        line = line.strip()

        time_match = patterns["time"].search(line)
        if time_match:
            save_current_point()

            current = {
                "time": parse_time_generic(time_match.group(1), fallback_date_str),
                "latitude": None,
                "longitude": None,
                "elevation": "",
                "speed": "",
                "track": "",
            }
            continue

        lat_match = patterns["latitude"].search(line)
        if lat_match:
            current["latitude"] = dms_to_decimal(lat_match.group(1))
            continue

        lon_match = patterns["longitude"].search(line)
        if lon_match:
            current["longitude"] = dms_to_decimal(lon_match.group(1))
            continue

        speed_match = patterns["speed"].search(line)
        if speed_match:
            current["speed"] = speed_match.group(1).strip()
            continue

        track_match = patterns["track"].search(line)
        if track_match:
            current["track"] = track_match.group(1).strip()
            continue

        alt_match = patterns["elevation"].search(line)
        if alt_match:
            current["elevation"] = alt_match.group(1).strip()
            continue

    save_current_point()

    gps_points.sort(key=lambda p: p["time"])
    return gps_points