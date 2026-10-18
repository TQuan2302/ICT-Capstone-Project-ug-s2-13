from pathlib import Path
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import math


def parse_gpx_time(time_text):
    """
    Parse GPX time into a timezone-aware datetime object.
    Common GPX format:
        2026-03-20T15:56:03Z
    """
    time_text = time_text.strip()

    if time_text.endswith("Z"):
        time_text = time_text.replace("Z", "+00:00")

    return datetime.fromisoformat(time_text).astimezone(timezone.utc)


def calculate_track(lat1, lon1, lat2, lon2):
    """
    Calculate approximate bearing angle from one GPS point to the next.
    This becomes camera_angle in the CSV.
    """
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    diff_lon = math.radians(lon2 - lon1)

    x = math.sin(diff_lon) * math.cos(lat2)
    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(diff_lon)
    )

    bearing = math.degrees(math.atan2(x, y))
    bearing = (bearing + 360) % 360

    return round(bearing, 2)


def extract_gpx_points(gpx_path):
    """
    Extract GPS points from a GPX file.

    Returns the same style of list used by MOV GPS extraction:
    [
        {
            "time": datetime,
            "latitude": float,
            "longitude": float,
            "elevation": str,
            "speed": str,
            "track": str
        }
    ]
    """
    gpx_path = Path(gpx_path)

    if not gpx_path.exists():
        raise FileNotFoundError(f"GPX file not found: {gpx_path}")

    tree = ET.parse(gpx_path)
    root = tree.getroot()

    gps_points = []

    # GPX usually uses namespaces, so this searches all trkpt tags
    for trkpt in root.iter():
        if not trkpt.tag.endswith("trkpt"):
            continue

        lat = trkpt.attrib.get("lat")
        lon = trkpt.attrib.get("lon")

        if lat is None or lon is None:
            continue

        elevation = ""
        time_value = None

        for child in trkpt:
            if child.tag.endswith("ele") and child.text:
                elevation = child.text.strip()

            elif child.tag.endswith("time") and child.text:
                time_value = parse_gpx_time(child.text)

        if time_value is None:
            continue

        gps_points.append({
            "time": time_value,
            "latitude": float(lat),
            "longitude": float(lon),
            "elevation": elevation,
            "speed": "",
            "track": ""
        })

    gps_points.sort(key=lambda p: p["time"])

    # Estimate camera track/bearing from movement direction.
    for i in range(len(gps_points) - 1):
        current_point = gps_points[i]
        next_point = gps_points[i + 1]

        current_point["track"] = calculate_track(
            current_point["latitude"],
            current_point["longitude"],
            next_point["latitude"],
            next_point["longitude"]
        )

    if len(gps_points) >= 2:
        gps_points[-1]["track"] = gps_points[-2]["track"]

    return gps_points