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
API_CSV_NAME = "api_report.csv"


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

def list_reports(folder):
    reports_folder = Path(folder)
    
    if not reports_folder.exists():
        raise FileNotFoundError(f"Reports folder not found: {reports_folder}")

    try:
        children = list(reports_folder.iterdir())
    except PermissionError:
        raise PermissionError(f"macOS blocked access to {reports_folder}")

    rl = []

    for child in children:
        csv_path = child / DETAILS_CSV_NAME
        if child.is_dir() and csv_path.is_file():
            rl.append(child.name)

    return rl

# True when the saved HTML is newer than every remaining video CSV.
# No remaining CSV means the saved page is stale, even though nothing is newer than it.
def combined_map_is_current(reports_folder, output_html):
    
    reports_folder = Path(reports_folder)
    output_html = Path(output_html)
    
    if not output_html.is_file(): return False
    
    reports = list_reports(reports_folder)
    if not reports: return False
    
    html_mtime_ns = output_html.stat().st_mtime_ns
    
    for r in reports:
        csv = reports_folder / r / DETAILS_CSV_NAME
        api = reports_folder / r / API_CSV_NAME
        
        if csv.stat().st_mtime_ns > html_mtime_ns: return False
        if api.stat().st_mtime_ns > html_mtime_ns: return False
        
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
    
    reports = list_reports(reports_folder)
    
    if not reports: raise ValueError("No detection reports found")

    points = []
    
    apipoints = []
    
    routes = []
    
    for r in reports:
        csv = reports_folder / r / DETAILS_CSV_NAME
        api = reports_folder / r / API_CSV_NAME
        
        video_points = geo_mapping.read_csv_input(csv, encode_snapshots=False)
        points.extend(attach_cached_snapshots(video_points, csv, reports_folder))
        
        apipoints = apipoints + geo_mapping.read_api_csv_input(api)
        
        route = geo_mapping.getCarRoute(csv.parent.parent.parent, csv.parent.name)
        if route: routes.append(route)
        
        
    apipoints = deconflict(apipoints)
            
    if not points and not apipoints: raise ValueError("No data to map, csv file coordinates empty")
    
    return points + apipoints + routes

# get rid of duplicates
def deconflict(points):
    seen = set()
    unique_points = []

    for p in points:
        object_id = p["object_id"]
        if object_id not in seen:
            seen.add(object_id)
            unique_points.append(p)

    return unique_points


# Open the existing combined map, or write a new one.
# A new HTML file is written only when at least one CSV is newer than the saved map.
# When no video remains, the saved page is removed so it cannot be opened again.
def build_map_from_reports(roadsight, output, selected_classes=None):
    
    print(0)
        
    # Paths
    reports_folder = Path(roadsight) / "reports"
    output = Path(output)
    
    reports = list_reports(reports_folder)
        
    # do nothing if there are no sub-folders
    if not reports:
        if output.is_file():
            output.unlink()
        raise ValueError("No detection reports found")
    
    # Create API reports, if they don't exist
    for r in reports:
        locationsa.createReadingAPIReport(roadsight,r)
    
    # do nothing if we're already up to date
    if combined_map_is_current(reports_folder, output):
        return str(output)
        
    # get the points
    points = read_all_report_csvs(reports_folder)
        
    # build the map
    return geo_mapping.build_map(points, output, selected_classes=selected_classes)

# References:  AI (Cursor) has been used for generating part of the script and suggesting solution