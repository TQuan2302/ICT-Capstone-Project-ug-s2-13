"""helpers for building the detection report."""

import os
from pathlib import Path

# define column for the marker information: lat, long, class name, object id and confidence level
CSV_HEADER = "camera_latitude,camera_longitude,class_name,object_id,confidence"


#Function for writing a GPS report. Each row is latitude, longitude, class, id, confidence.
def write_gps_csv(path, rows):
    
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [CSV_HEADER]
    for latitude, longitude, class_name, object_id, confidence in rows:
        lines.append(f"{latitude},{longitude},{class_name},{object_id},{confidence}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

#Set a file's modified time so tests can decide which file is newer. 
def set_file_time(path, time_ns):
   
    os.utime(path, ns=(time_ns, time_ns))
