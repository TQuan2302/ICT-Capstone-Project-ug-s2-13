import pytest
import datetime

try:
    import gps_from_gpx

    extract_gpx_points = gps_from_gpx.extract_gpx_points
except Exception:
    extract_gpx_points = None


def test_import():
    assert extract_gpx_points != None


inputs_z = [
    "2026-09-08T23:54:12Z",
    "2026-05-14T06:12:45Z",
    "2025-11-22T14:30:00Z",
    "2025-03-10T09:30:12Z",
    "2024-07-19T18:25:39Z",
    "2024-01-15T22:04:18Z",
    "2023-10-05T11:45:55Z",
    "2022-08-12T05:19:22Z",
    "2021-04-30T13:02:47Z",
]
inputs = [
    "2026-09-08T23:54:12",
    "2026-05-14T06:12:45",
    "2025-11-22T14:30:00",
    "2025-03-10T09:30:12",
    "2024-07-19T18:25:39",
    "2024-01-15T22:04:18",
    "2023-10-05T11:45:55",
    "2022-08-12T05:19:22",
    "2021-04-30T13:02:47",
]
expected_outputs = [
    datetime.datetime(2026, 9, 8, 23, 54, 12, tzinfo=datetime.timezone.utc),
    datetime.datetime(2026, 5, 14, 6, 12, 45, tzinfo=datetime.timezone.utc),
    datetime.datetime(2025, 11, 22, 14, 30, 0, tzinfo=datetime.timezone.utc),
    datetime.datetime(2025, 3, 10, 9, 30, 12, tzinfo=datetime.timezone.utc),
    datetime.datetime(2024, 7, 19, 18, 25, 39, tzinfo=datetime.timezone.utc),
    datetime.datetime(2024, 1, 15, 22, 4, 18, tzinfo=datetime.timezone.utc),
    datetime.datetime(2023, 10, 5, 11, 45, 55, tzinfo=datetime.timezone.utc),
    datetime.datetime(2022, 8, 12, 5, 19, 22, tzinfo=datetime.timezone.utc),
    datetime.datetime(2021, 4, 30, 13, 2, 47, tzinfo=datetime.timezone.utc),
]


class TestGPXParser:
    def test_start(self):
        """Test the theoretical limits defined in ISO 8601"""
        result = gps_from_gpx.parse_gpx_time("2026-03-20T15:56:03Z")

        assert result == datetime.datetime(
            2026, 3, 20, 15, 56, 3, tzinfo=datetime.timezone.utc
        )

    @pytest.mark.parametrize(
        "time_string,expected_datetime", list(zip(inputs_z, expected_outputs))
    )
    def test_random_z(self, time_string, expected_datetime):
        """Test conversion of a random assortment of GPX datetime strings in Zulu (UTC) time"""
        assert gps_from_gpx.parse_gpx_time(time_string) == expected_datetime

    @pytest.mark.parametrize(
        "time_string,expected_datetime", list(zip(inputs_z, expected_outputs))
    )
    def test_random(self, time_string, expected_datetime):
        """Test conversion of a random assortment of GPX datetime strings in local time"""
        assert gps_from_gpx.parse_gpx_time(time_string) == expected_datetime


class TestCalculateTrack:
    def test_same(self):
        lat = -34.920275513503185
        long = 138.60656282721035

        assert gps_from_gpx.calculate_track(lat, long, lat, long) == 0
