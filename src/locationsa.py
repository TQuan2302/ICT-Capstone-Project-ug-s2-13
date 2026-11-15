import requests
import csv
from pathlib import Path

import gps_from_gpx
import gps_from_mov

# sign codes
signs = {
    # Speed
    **dict.fromkeys(["R4-1A", "R4-1B", "R4-1C", "R4-1D"], "Speed"),

    # Bicycle
    **dict.fromkeys([ "R7-1-4B", "R7-1-4C", "R7-1-4D"], "Bicycle"),

    # Bicycle times
    **dict.fromkeys(["R5-SA101-1N", "R5-SA101-2N","R5-SA101-1W", "R5-SA101-2W"], "Bicycle Times"),

    # Curves
    **dict.fromkeys(["W1-3A", "W1-3B", "W1-3C", "W1-3D"], "Curve"),

    # Sharp curves
    **dict.fromkeys(["W1-1A", "W1-1B", "W1-1C", "W1-1D"], "Sharp Curve"),

    # Winding road
    **dict.fromkeys(["W1-5A", "W1-5AA", "W1-5B","W1-5C", "W1-5D", "W1-5ES"], "Winding Road"),

    # Hump ahead
    **dict.fromkeys(["W5-10A", "W5-10B", "W5-10C"], "Hump")
}
st = list(signs.keys())

# Return 2000 random points
def getRandomStatePoints():
    url = "https://dpti.geohub.sa.gov.au/server/rest/services/RoadAsset/RoadAncillaryAssetsPRODv2_Viewer/MapServer/1/query"

    params = {
        "where": "1=1",
        "outFields": "message,uid",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
        "resultRecordCount": 2000
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()
    
    return(data)
    
    rList = []
    
    # ['latitude', 'longitude', 'class_name', 'object_id', 'confidence', 'snapshot_data_uri', 'source_video']
    for x in data["features"]:
        item = {
            "latitude": x["geometry"]["coordinates"][1],
            "longitude" : x["geometry"]["coordinates"][0],
            "class_name" : "state_api",
            "message" : x["properties"]["message"],
            "object_id" : x["properties"]["message"],
            "confidence" : 1,
        }
        
        rList.append(item)
        
    return rList

# Return permitted points within some boundary
def getBoundedStatePoints(minlat,maxlat,minlon,maxlon):
    # sign types we care about:
    
    # Get the points of interest on the map
    url = "https://dpti.geohub.sa.gov.au/server/rest/services/RoadAsset/RoadAncillaryAssetsPRODv2_Viewer/MapServer/1/query"
    params = {
        "where": f"signcode IN ({', '.join(repr(code) for code in st)})",
        "outFields": "message,uid,signcode",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
        "resultRecordCount": 2000,
        
        "geometry": f"{minlon},{minlat},{maxlon},{maxlat}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    rList = []
    for x in data["features"]:
        item = {
            "latitude": x["geometry"]["coordinates"][1],
            "longitude" : x["geometry"]["coordinates"][0],
            "class_name" : "state_"+signs[x["properties"]["signcode"]],
            "message" : x["properties"]["message"],
            "object_id" : x["properties"]["uid"],
        }
        
        rList.append(item)

    
    return(rList)

    
# Input: the main roadsight directory AND the name of this video
# Output: the path to our newly created CSV file
def createReadingAPIReport(roadsightDir, video):
    print(roadsightDir)
    roadsightDir = Path(roadsightDir)
    
    # Get the detection CSV file
    parentDirectory = roadsightDir / "reports" / video
    path = parentDirectory / "api_report.csv"
    
    # If it already exists, just return it!
    if path.is_file(): return path
    
    # TEST IF WORK
    for file in parentDirectory.iterdir():
        print(file)

    # Get the bounds
    if (roadsightDir / "uploads" / f"{video}.MOV").is_file():
        upload = roadsightDir / "uploads" / f"{video}.MOV"
        points = gps_from_mov.extract_mov_gps_points(upload)
    elif (roadsightDir / "uploads" / f"{video}.GPX").is_file():
        upload = roadsightDir / "uploads" / f"{video}.GPX"
        points = gps_from_gpx.extract_gpx_points(upload)
    else:
        raise FileNotFoundError(f"No MOV or GPX file found for {video}")
    
    padding_m = 100 # meters
    padding = padding_m / 111_320

    minlat = min(point["latitude"] for point in points) - padding
    maxlat = max(point["latitude"] for point in points) + padding
    minlon = min(point["longitude"] for point in points) - padding
    maxlon = max(point["longitude"] for point in points) + padding
        
    print(minlat, maxlat, minlon, maxlon)
    
    # Get the points
    apipoints = getBoundedStatePoints(minlat,maxlat,minlon,maxlon)
    
    # print(len(apipoints))
    # print(apipoints[19])
        
    # Create the csv
    fieldnames = ["latitude", "longitude", "class_name", "message", "object_id"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(apipoints)    
    
    # Return the newly created API report csv file
    print('hey whats up')
    return path


# References: AI used for some code snippets & advice (OpenAI's ChatGPT)