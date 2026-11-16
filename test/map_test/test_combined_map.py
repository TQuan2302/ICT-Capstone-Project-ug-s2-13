#Tests for the combined map in src/combined_map.py.

import json
from pathlib import Path

import pytest

import combined_map
from helpers import set_file_time, write_api_csv, write_gps_csv

ONE_DETECTION = ("-34.9285", "138.6007", "speed_limit", "speed_limit_1", "0.9")
REPORT_NAME = combined_map.DETAILS_CSV_NAME
API_NAME = combined_map.API_CSV_NAME


def write_video_reports(reports_folder, video_name, rows):
    csv_path = write_gps_csv(reports_folder / video_name / REPORT_NAME, rows)
    api_path = write_api_csv(reports_folder / video_name / API_NAME)
    return csv_path, api_path


def stub_api_report(roadsight, video):
    return write_api_csv(Path(roadsight) / "reports" / video / API_NAME)


#Test case - combined map: The combined map reads folder with detection_details_with_gps.csv and skip the other folders.
def test_skip_folder(tmp_path):
    
    write_gps_csv(tmp_path / "b_video" / REPORT_NAME, [ONE_DETECTION])
    write_gps_csv(tmp_path / "a_video" / REPORT_NAME, [ONE_DETECTION])
    
    (tmp_path / "notes_only").mkdir()
    cache = tmp_path / ".map_cache"
    cache.mkdir()
    (cache / "a_video.json").write_text("{}", encoding="utf-8")

    reports = combined_map.list_report_csvs(tmp_path)

    assert reports == [
        tmp_path / "a_video" / REPORT_NAME,
        tmp_path / "b_video" / REPORT_NAME,
    ]

#Test case - combined map: missing "report" folder
def test_a_missing_reports_folder_fails(tmp_path):
    
    with pytest.raises(FileNotFoundError):
        combined_map.list_report_csvs(tmp_path / "missing")


#Test case - combined map: No saved HTML file means the combined map html must be built.
def test_the_combined_map_is_missing_until_the_html_file_exists(tmp_path):
   
    write_video_reports(tmp_path, "a_video", [ONE_DETECTION])

    is_current = combined_map.combined_map_is_current(tmp_path, tmp_path / "all_detections_map.html")

    assert is_current is False

#Test case - Caching: Skip generating a new html if the current htmt timestamp is newer than all CSVs. 
def test_the_combined_map_is_current_when_it_is_newer_than_every_report(tmp_path):
    
    first_csv, first_api = write_video_reports(tmp_path, "a_video", [ONE_DETECTION])
    second_csv, second_api = write_video_reports(tmp_path, "b_video", [ONE_DETECTION])
    saved_map = tmp_path / "all_detections_map.html"
    saved_map.write_text("<html></html>", encoding="utf-8")
    set_file_time(first_csv, 1_000)
    set_file_time(first_api, 1_000)
    set_file_time(second_csv, 1_000)
    set_file_time(second_api, 1_000)
    set_file_time(saved_map, 5_000)

    assert combined_map.combined_map_is_current(tmp_path, saved_map) is True


#Test case - Caching: A saved combined page is not reused after every video has been removed.
def test_a_saved_combined_map_is_dropped_when_no_video_remains(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    saved_map = reports / "all_detections_map.html"
    saved_map.write_text("OLD MAP", encoding="utf-8")

    assert combined_map.combined_map_is_current(reports, saved_map) is False

    with pytest.raises(ValueError, match="No detection reports found"):
        combined_map.build_map_from_reports(tmp_path, saved_map)

    assert saved_map.exists() is False


# Test case - Caching: If one CSV is newer than the combined HTML, rebuild.
# After rebuild, the newer video gets a new .map_cache file.
# The older video already has a matching cache file, so that file stays unchanged.
def test_one_newer_report_makes_the_combined_map_out_of_date(tmp_path, monkeypatch):
    monkeypatch.setattr(combined_map.locationsa, "createReadingAPIReport", stub_api_report)

    reports = tmp_path / "reports"
    old_csv, old_api = write_video_reports(reports, "old_video", [ONE_DETECTION])
    new_csv, new_api = write_video_reports(
        reports,
        "new_video",
        [("-35.1000", "138.8000", "bike_lane", "bike_lane_2", "0.7")],
    )
    combined_html = reports / "all_detections_map.html"
    combined_html.write_text("OLD MAP", encoding="utf-8")
    set_file_time(old_csv, 1_000)
    set_file_time(old_api, 1_000)
    set_file_time(combined_html, 5_000)
    set_file_time(new_csv, 9_000)
    set_file_time(new_api, 9_000)

    assert combined_map.combined_map_is_current(reports, combined_html) is False

    # Old video already has a photo cache that matches its CSV time.
    old_cache = reports / ".map_cache" / "old_video.json"
    old_cache.parent.mkdir()
    old_cache.write_text(
        json.dumps(
            {
                "csv_mtime_ns": old_csv.stat().st_mtime_ns,
                "images": {"speed_limit_id1_last.jpg": "data:image/jpeg;base64,old"},
            }
        ),
        encoding="utf-8",
    )
    set_file_time(old_cache, 2_000)
    old_cache_before = old_cache.read_text(encoding="utf-8")
    old_cache_mtime = old_cache.stat().st_mtime_ns

    new_cache = reports / ".map_cache" / "new_video.json"
    assert new_cache.exists() is False

    combined_map.build_map_from_reports(tmp_path, combined_html)

    # Newer video was encoded, so its cache file is created.
    assert new_cache.is_file()
    # Older video reused its cache, so that file is unchanged.
    assert old_cache.read_text(encoding="utf-8") == old_cache_before
    assert old_cache.stat().st_mtime_ns == old_cache_mtime


# Test case - combined map: entries from two different videos are drawn on one map.
def test_two_videos_are_plotted_on_the_same_map(tmp_path, monkeypatch):
    # Skip network API generation; empty api_report.csv files are already written.
    monkeypatch.setattr(combined_map.locationsa, "createReadingAPIReport", stub_api_report)

    reports = tmp_path / "reports"
    write_video_reports(
        reports,
        "north_video",
        [("-34.9285", "138.6007", "speed_limit", "speed_limit_1", "0.9")],
    )
    write_video_reports(
        reports,
        "south_video",
        [("-35.1000", "138.8000", "bike_lane", "bike_lane_2", "0.7")],
    )

    points = combined_map.read_all_report_csvs(reports)
    videos = {point["source_video"] for point in points if "source_video" in point}
    assert videos == {"north_video", "south_video"}

    saved_map = reports / "all_detections_map.html"
    combined_map.build_map_from_reports(tmp_path, saved_map)

    html = saved_map.read_text(encoding="utf-8")
    assert "north_video" in html
    assert "south_video" in html
    assert "-34.928500" in html
    assert "-35.100000" in html
