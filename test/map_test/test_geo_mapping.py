"""Tests for one video's map in src/geo_mapping.py."""

import base64

import pytest

import geo_mapping
from helpers import set_file_time, write_api_csv, write_gps_csv

# Define a fixed entry for testing
ONE_DETECTION = ("-34.9285", "138.6007", "speed_limit", "speed_limit_3", "0.8")


def make_point(class_name, object_id, latitude=-34.9285, longitude=138.6007):
    return {
        "source": "detection",
        "latitude": latitude,
        "longitude": longitude,
        "class_name": class_name,
        "object_id": object_id,
        "confidence": "0.8",
        "speed_value": "",
        "bearing": "",
        "screen": "",
        "snapshot_data_uri": None,
    }

#if a row with numbers for latitude and longitude is kept.
def test_a_valid_gps_row_becomes_a_map_point(tmp_path):
    csv_path = write_gps_csv(
        tmp_path / "clip" / "detection_details_with_gps.csv",
        [ONE_DETECTION],
    )

    points = geo_mapping.read_csv_input(csv_path, encode_snapshots=False)

    assert points == [make_point("speed_limit", "speed_limit_3")]

#if a detections with no GPS cannot be placed on the map.
def test_a_row_with_a_blank_coordinate_is_skipped(tmp_path):
    
    csv_path = write_gps_csv(
        tmp_path / "clip" / "detection_details_with_gps.csv",
        [("", "138.6", "speed_limit", "speed_limit_1", "0.4")],
    )

    points = geo_mapping.read_csv_input(csv_path, encode_snapshots=False)

    assert points == []

#if a coordinate that is not a number is ignored.
def test_a_row_with_text_instead_of_a_coordinate_is_skipped(tmp_path):
    
    csv_path = write_gps_csv(
        tmp_path / "clip" / "detection_details_with_gps.csv",
        [("-34.9", "not-a-number", "speed_limit", "speed_limit_2", "0.5")],
    )

    points = geo_mapping.read_csv_input(csv_path, encode_snapshots=False)

    assert points == []

#Reading a CSV file that does not exist raises FileNotFoundError.
def test_reading_a_missing_csv_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        geo_mapping.read_csv_input(tmp_path / "missing.csv")

#if no class is passed to "filter_points_by_class" then all objects are displayed
def test_no_class_filter_keeps_every_point():
    
    points = [make_point("Speed Limit", "speed_limit_1"), make_point("Bike Lane", "bike_lane_1")]
    assert geo_mapping.filter_points_by_class(points, None) == points


#A blank selection, such as spaces or None, keeps every point.
def test_blank_class_names_do_not_filter_anything():
    
    points = [make_point("Speed Limit", "speed_limit_1")]
    assert geo_mapping.filter_points_by_class(points, ["  ", None]) == points



#if the class that is not in the selection is not displayed on the map.
def test_class_filter_drops_a_class_that_was_not_selected():
    points = [make_point("Speed Limit", "speed_limit_1")]
    assert geo_mapping.filter_points_by_class(points, ["pothole"]) == []

#Each class is given one colour and that colour does not change.
def test_the_same_class_keeps_the_same_colour():
    colours = {}

    first = geo_mapping.assign_color_for_class("speed_limit", colours)
    again = geo_mapping.assign_color_for_class("speed_limit", colours)

    assert again == first

#The next class receives the next colour in the list.
def test_a_new_class_gets_a_different_colour():
    
    colours = {}
    speed_limit = geo_mapping.assign_color_for_class("speed_limit", colours)
    bike_lane = geo_mapping.assign_color_for_class("bike_lane", colours)

    assert bike_lane != speed_limit

#There are 10 colours, so class 11 reuses the colour of class 1.
def test_colours_start_again_after_the_list_runs_out():
    colours = {}
    assigned = [
        geo_mapping.assign_color_for_class(f"class_{number}", colours)
        for number in range(11)
    ]

    assert assigned[0] == assigned[10]


#object_id 'pothole_12' looks for snapshots/pothole_id12_last.jpg.
def test_snapshot_photo_path_uses_the_id_after_the_class_name(tmp_path):
    
    csv_path = tmp_path / "clip" / "detection_details_with_gps.csv"

    photo = geo_mapping.snapshot_path_for_point(
        {"class_name": "pothole", "object_id": "pothole_12"},
        csv_path,
    )

    assert photo == tmp_path / "clip" / "snapshots" / "pothole_id12_last.jpg"


#If the id does not start with the class name, the part after the last _ is used.
def test_snapshot_photo_path_uses_the_last_id_when_the_prefix_differs(tmp_path):
    
    csv_path = tmp_path / "clip" / "detection_details_with_gps.csv"

    photo = geo_mapping.snapshot_path_for_point(
        {"class_name": "pothole", "object_id": "other_7"},
        csv_path,
    )

    assert photo == tmp_path / "clip" / "snapshots" / "pothole_id7_last.jpg"

#The map popup needs the photo as text, not as a separate file.
def test_an_existing_snapshot_becomes_image_text_for_the_popup(tmp_path):
   
    photo = tmp_path / "snap.jpg"
    photo_bytes = b"\xff\xd8fake-jpeg"
    photo.write_bytes(photo_bytes)

    image_text = geo_mapping.image_to_data_uri(photo)

    expected = "data:image/jpeg;base64," + base64.b64encode(photo_bytes).decode("ascii")
    assert image_text == expected

#A missing photo file returns None, so no picture is added.
def test_a_missing_snapshot_does_not_add_a_photo(tmp_path):
   
    assert geo_mapping.image_to_data_uri(tmp_path / "missing.jpg") is None

#build_map raises an error when the point list is empty.
def test_building_a_map_with_no_points_fails(tmp_path):
    with pytest.raises(ValueError, match="No data to map"):
        geo_mapping.build_map([], tmp_path / "map.html")

#The saved HTML contains the chosen class and leaves the other class out.
def test_building_a_map_keeps_only_the_selected_class(tmp_path):
    
    output = tmp_path / "maps" / "one.html"

    geo_mapping.build_map(
        points=[
            make_point("speed_limit", "speed_limit_3"),
            make_point("bike_lane", "bike_lane_1", latitude=-34.93, longitude=138.61),
        ],
        output_html=output,
        selected_classes=["speed_limit"],
    )

    html = output.read_text(encoding="utf-8")
    assert "speed_limit" in html
    assert "bike_lane" not in html
    assert "-34.928500" in html


#If the HTML file is newer than the CSV and API report, the old map is opened again.
def test_an_unchanged_video_reuses_its_saved_map(tmp_path):
    csv_path = write_gps_csv(tmp_path / "clip" / "detection_details_with_gps.csv", [ONE_DETECTION])
    api_path = write_api_csv(tmp_path / "clip" / "api_report.csv")
    saved_map = tmp_path / "clip" / "detection_map.html"
    saved_map.write_text("OLD MAP", encoding="utf-8")
    set_file_time(csv_path, 1_000)
    set_file_time(api_path, 1_000)
    set_file_time(saved_map, 2_000)

    opened = geo_mapping.build_map_from_csv(csv_path, api_path, saved_map)

    assert opened == str(saved_map)
    assert saved_map.read_text(encoding="utf-8") == "OLD MAP"

#If the report changed after the map was saved, a new HTML file is written.
def test_a_newer_csv_makes_the_map_again(tmp_path):
    csv_path = write_gps_csv(tmp_path / "clip" / "detection_details_with_gps.csv", [ONE_DETECTION])
    api_path = write_api_csv(tmp_path / "clip" / "api_report.csv")
    saved_map = tmp_path / "clip" / "detection_map.html"
    saved_map.write_text("OLD MAP", encoding="utf-8")
    set_file_time(saved_map, 1_000)
    set_file_time(api_path, 1_000)
    set_file_time(csv_path, 2_000)

    geo_mapping.build_map_from_csv(csv_path, api_path, saved_map)

    html = saved_map.read_text(encoding="utf-8")
    assert "OLD MAP" not in html
    assert "speed_limit" in html
