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

from helpers import write_gps_csv

ONE_DETECTION = ("-34.9285", "138.6007", "speed_limit", "speed_limit_3", "0.8")
client = TestClient(webapp.app)


# Make the map routes read this folder instead of Documents/RoadSight/reports.
def use_reports_folder(monkeypatch, reports_folder):
    monkeypatch.setattr(webapp, "REPORT_FOLDER", str(reports_folder))


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
