"""Saved snapshot photos for the combined map.

Each video gets reports/.map_cache/<video name>.json.
The file stores the encoded JPEG text so unchanged videos are not encoded again.
"""

import json
from pathlib import Path

# Hidden folder next to the video report folders.
CACHE_DIR_NAME = ".map_cache"


# Path of one video's cache file.
def snapshot_cache_file(reports_folder, video_name):
    return Path(reports_folder) / CACHE_DIR_NAME / f"{video_name}.json"


# Read a cache file. A missing or broken file means the snapshots must be encoded again.
def load_snapshot_cache(cache_path):
    try:
        with open(cache_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("images"), dict):
        return None
    return data


# Write the encoded snapshots and the CSV time they belong to.
def save_snapshot_cache(cache_path, csv_mtime_ns, images):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"csv_mtime_ns": csv_mtime_ns, "images": images}, f)


# Return saved images when the CSV has not changed. Otherwise encode and save them.
def images_for_video(reports_folder, video_name, csv_mtime_ns, encode_images):
    cache_path = snapshot_cache_file(reports_folder, video_name)
    cache = load_snapshot_cache(cache_path)
    if cache is not None and cache.get("csv_mtime_ns") == csv_mtime_ns:
        return cache["images"]

    images = encode_images()
    save_snapshot_cache(cache_path, csv_mtime_ns, images)
    return images
