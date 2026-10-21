"""Build one map from every video report.

Saves reports/all_detections_map.html.
If that file is already newer than every detection CSV, it is reused.
Snapshot photos for unchanged videos come from snapshot_cache.
"""

from pathlib import Path

import geo_mapping
import snapshot_cache

import locationsa

# GPS detail file written for each processed video.
DETAILS_CSV_NAME = "detection_details_with_gps.csv"


# Find reports/<video>/detection_details_with_gps.csv.
# iterdir raises if macOS blocks the folder. glob would hide that and look empty.
def list_report_csvs(reports_folder):
    reports_folder = Path(reports_folder)
    if not reports_folder.exists():
        raise FileNotFoundError(f"Reports folder not found: {reports_folder}")

    try:
        children = list(reports_folder.iterdir())
    except PermissionError:
        raise PermissionError(f"macOS blocked access to {reports_folder}")

    csv_paths = []
    for child in children:
        csv_path = child / DETAILS_CSV_NAME
        if child.is_dir() and csv_path.is_file():
            csv_paths.append(csv_path)
    csv_paths.sort()
    return csv_paths


# True when the saved HTML is newer than every video CSV, so nothing needs rebuilding.
def combined_map_is_current(reports_folder, output_html):
    output_html = Path(output_html)
    if not output_html.is_file():
        return False
    html_mtime_ns = output_html.stat().st_mtime_ns
    for csv_path in list_report_csvs(reports_folder):
        if csv_path.stat().st_mtime_ns > html_mtime_ns:
            return False
    return True


# Encode this video's snapshot JPEGs. Used only when its cache is missing or stale.
def encode_snapshot_images(points, csv_path):
    images = {}
    for point in points:
        image_path = geo_mapping.snapshot_path_for_point(point, csv_path)
        uri = geo_mapping.image_to_data_uri(image_path)
        if uri is not None:
            images[image_path.name] = uri
    return images


# Attach each point's photo from the cache, and record which video it came from.
def attach_cached_snapshots(points, csv_path, reports_folder):
    video_name = csv_path.parent.name

    # Runs only when this video's cache is missing or its CSV is newer.
    def encode_this_video():
        return encode_snapshot_images(points, csv_path)

    images = snapshot_cache.images_for_video(
        reports_folder,
        video_name,
        csv_path.stat().st_mtime_ns,
        encode_this_video,
    )
    for point in points:
        point["source_video"] = video_name
        image_name = geo_mapping.snapshot_path_for_point(point, csv_path).name
        point["snapshot_data_uri"] = images.get(image_name)
    return points


# Read every video CSV into one point list. object_id can repeat, so each point keeps its video name.
def read_all_report_csvs(reports_folder):
    reports_folder = Path(reports_folder)
    csv_paths = list_report_csvs(reports_folder)
    if not csv_paths:
        raise ValueError("No detection reports found")

    points = []
    for csv_path in csv_paths:
        video_points = geo_mapping.read_csv_input(csv_path, encode_snapshots=False)
        points.extend(attach_cached_snapshots(video_points, csv_path, reports_folder))
        
    # the below is a temporary proof of concept, to show that we are indeed able to plot API points on the map
    points = points + locationsa.getRandomStatePoints()
    
    print(list(points[0]))

    if not points:
        raise ValueError("No data to map, csv file coordinates empty")
    return points


# Open the existing combined map, or write a new one.
# A new HTML file is written only when at least one CSV is newer than the saved map.
def build_map_from_reports(reports_folder, output, selected_classes=None):
    if combined_map_is_current(reports_folder, output):
        return str(output)
    points = read_all_report_csvs(reports_folder)
    return geo_mapping.build_map(points, output, selected_classes=selected_classes)
