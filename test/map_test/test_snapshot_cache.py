# Tests for the snapshot photo cache in src/snapshot_cache.py.

import json
import snapshot_cache


# Stands in for the real photo encoder and counts how often it runs.
class TestEncoder:
    def __init__(self, images):
        self.images = images
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.images


# The first request encodes the photos and writes .map_cache/<video>.json.
def test_a_missing_cache_encodes_the_photos_and_saves_them(tmp_path):
    encoder = TestEncoder({"snap.jpg": "data:image/jpeg;base64,abc"})

    images = snapshot_cache.images_for_video(tmp_path, "clip", 100, encoder)

    saved = json.loads((tmp_path / ".map_cache" / "clip.json").read_text(encoding="utf-8"))
    assert images == {"snap.jpg": "data:image/jpeg;base64,abc"}
    assert encoder.calls == 1
    assert saved["csv_mtime_ns"] == 100
    assert saved["images"] == images


# If the CSV time matches the cache, the photos are not encoded again.
def test_an_unchanged_video_reuses_the_saved_photos(tmp_path):
    snapshot_cache.images_for_video(tmp_path, "clip", 100, lambda: {"snap.jpg": "cached"})
    encoder = TestEncoder({"snap.jpg": "new"})

    images = snapshot_cache.images_for_video(tmp_path, "clip", 100, encoder)

    assert images == {"snap.jpg": "cached"}
    assert encoder.calls == 0


# A new CSV time means the saved photos are out of date.
def test_a_changed_csv_encodes_the_photos_again(tmp_path):
    snapshot_cache.images_for_video(tmp_path, "clip", 100, lambda: {"snap.jpg": "old"})

    images = snapshot_cache.images_for_video(tmp_path, "clip", 200, lambda: {"snap.jpg": "new"})

    assert images == {"snap.jpg": "new"}


# Unreadable JSON is treated as no cache, so the photos will be encoded again.
def test_a_broken_cache_file_is_ignored(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    assert snapshot_cache.load_snapshot_cache(broken) is None


# The cache must store photos as a dictionary of file name to image text.
def test_a_cache_file_without_a_photo_dictionary_is_ignored(tmp_path):
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text('{"csv_mtime_ns": 1, "images": []}', encoding="utf-8")

    assert snapshot_cache.load_snapshot_cache(incomplete) is None


# No cache file means the photos have not been saved yet.
def test_a_missing_cache_file_is_ignored(tmp_path):
    assert snapshot_cache.load_snapshot_cache(tmp_path / "missing.json") is None
