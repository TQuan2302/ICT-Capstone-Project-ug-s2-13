import requests


def getRandomStatePoints():
    url = "https://dpti.geohub.sa.gov.au/server/rest/services/RoadAsset/RoadAncillaryAssetsPRODv2_Viewer/MapServer/1/query"

    params = {
        "where": "1=1",
        "outFields": "message",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
        "resultRecordCount": 2000
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()
    
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