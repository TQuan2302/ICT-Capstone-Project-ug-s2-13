# Tests for the Map page routes in src/webapp.py.
# The web app normally copies model files into Documents on startup.
# These tests point that folder at a temporary home and skip the copy.

import os
import tempfile

os.environ["HOME"] = tempfile.mkdtemp(prefix="roadsight-map-tests-")

import roadsight_paths

roadsight_paths.seed_runtime_data = lambda: roadsight_paths.DATA_DIR
roadsight_paths.install_shutdown_sync = lambda: None

import webapp
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from helpers import write_api_csv, write_gps_csv

ONE_DETECTION = ("-34.9285", "138.6007", "speed_limit", "speed_limit_3", "0.8")
client = TestClient(webapp.app)


# Make the map routes read this folder instead of Documents/RoadSight/reports.
def use_reports_folder(monkeypatch, reports_folder):
    monkeypatch.setattr(webapp, "REPORT_FOLDER", str(reports_folder))
    # createReadingAPIReport uses DATA_DIR / "reports" / video
    monkeypatch.setattr(webapp, "DATA_DIR", str(reports_folder.parent))


# Folders are listed in name order. A folder with no GPS file is left out.
def test_the_map_list_shows_videos_that_have_a_gps_report(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    write_gps_csv(reports / "beta" / "detection_details_with_gps.csv", [ONE_DETECTION])
    write_gps_csv(reports / "Alpha" / "detection_details_with_gps.csv", [ONE_DETECTION])
    (reports / "no_csv").mkdir(parents=True)
    use_reports_folder(monkeypatch, reports)

    response = client.get("/map-list")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Alpha", "beta"]


# .map_cache is storage for photos, not a processed video.
def test_the_map_list_hides_the_snapshot_cache_folder(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    cache = reports / ".map_cache"
    cache.mkdir(parents=True)
    (cache / "detection_details_with_gps.csv").write_text("not a video\n", encoding="utf-8")
    use_reports_folder(monkeypatch, reports)

    response = client.get("/map-list")

    assert response.status_code == 200
    assert response.json() == []


# A missing reports folder is an empty list, not an error page.
def test_the_map_list_is_empty_when_there_is_no_reports_folder(tmp_path, monkeypatch):
    use_reports_folder(monkeypatch, tmp_path / "missing")

    response = client.get("/map-list")

    assert response.status_code == 200
    assert response.json() == []


# A video name that has no report cannot open a map.
def test_opening_an_unknown_video_returns_not_found(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    use_reports_folder(monkeypatch, reports)

    response = client.get("/map/not-a-video")

    assert response.status_code == 404


# ".." must not open a file above the reports folder.
def test_a_video_name_cannot_point_outside_the_reports_folder(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    use_reports_folder(monkeypatch, reports)

    with pytest.raises(HTTPException) as error:
        webapp.show_one_map("..")

    assert error.value.status_code == 404


# The page for one video is the HTML map built from that video's CSV.
def test_opening_a_video_returns_its_map_page(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    write_gps_csv(reports / "clip" / "detection_details_with_gps.csv", [ONE_DETECTION])
    write_api_csv(reports / "clip" / "api_report.csv")
    use_reports_folder(monkeypatch, reports)

    response = client.get("/map/clip")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "speed_limit" in response.text


# The combined map has nothing to draw if no video has a GPS report.
def test_show_all_maps_returns_not_found_when_there_are_no_reports(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    use_reports_folder(monkeypatch, reports)

    response = client.get("/map/all")

    assert response.status_code == 404


# DELETE /detections/<name> removes the result, report, cache, and combined map,
# and clears the in-memory status so the entry does not stay marked as done.
def test_deleting_a_video_removes_its_map_files_and_status(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    results = tmp_path / "results"
    results.mkdir()

    report_dir = reports / "clip"
    write_gps_csv(report_dir / "detection_details_with_gps.csv", [ONE_DETECTION])
    (report_dir / "detection_map.html").write_text("ONE MAP", encoding="utf-8")
    (report_dir / "snapshots").mkdir()
    (report_dir / "snapshots" / "speed_limit_id3_last.jpg").write_bytes(b"jpg")

    cache_file = reports / ".map_cache" / "clip.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text('{"csv_mtime_ns": 1, "images": {}}', encoding="utf-8")

    combined = reports / "all_detections_map.html"
    combined.write_text("ALL MAPS", encoding="utf-8")

    result_file = results / "detected_clip.mp4"
    result_file.write_bytes(b"video")
    browser_copy = results / "detected_clip.browser.mp4"
    browser_copy.write_bytes(b"browser")

    use_reports_folder(monkeypatch, reports)
    monkeypatch.setattr(webapp, "RESULT_FOLDER", str(results))
    with webapp.detection_queue_lock:
        webapp.detection_status["clip.mov"] = "done"

    response = client.delete("/detections/clip")

    assert response.status_code == 200
    assert response.json() == {"deleted": "clip"}
    assert result_file.exists() is False
    assert browser_copy.exists() is False
    assert report_dir.exists() is False
    assert cache_file.exists() is False
    assert combined.exists() is False
    with webapp.detection_queue_lock:
        assert "clip.mov" not in webapp.detection_status


# A name with nothing left to remove is reported as not found.
def test_deleting_an_unknown_video_returns_not_found(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    results = tmp_path / "results"
    reports.mkdir()
    results.mkdir()
    use_reports_folder(monkeypatch, reports)
    monkeypatch.setattr(webapp, "RESULT_FOLDER", str(results))

    response = client.delete("/detections/missing")

    assert response.status_code == 404
