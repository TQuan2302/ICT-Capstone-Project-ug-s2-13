import locationsa
import geo_mapping
import combined_map

from pathlib import Path


p = Path("/home/jaima/Library/Application Support/RoadSight")

locationsa.createReadingAPIReport(p,"fourdoor")

csvp = p / "reports/fourdoor/detection_details_with_gps.csv"
apip = p / "reports/fourdoor/api_report.csv"
out = p / "reports/fourdoor/detection_map.html"


geo_mapping.build_map_from_csv(csvp,apip,out)

# p2 = Path("/home/jaima/Library/Application Support/RoadSight")

# print(combined_map.list_reports(p2))

# out = p2 / "reports" / "all_detections_map.html"

# combined_map.build_map_from_reports(p2,out)
