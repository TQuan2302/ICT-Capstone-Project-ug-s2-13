import geo_mapping
import folium
import math

point = {
    "latitude" : -35.12891667,
    "longitude" : 139.0429278,
    "bearing" : 118,
    "screen" : -0.5
}

def getit(p): return [p["latitude"],p["longitude"]]

# The following was created (almost) entirely with AI, to create a map to visualise all the relevant points

def create_map(points, output_file="map.html"):
    """
    points: List of (latitude, longitude) pairs.
    """

    # Centre map on average coordinates
    avg_lat = sum(p[0] for p in points) / len(points)
    avg_lon = sum(p[1] for p in points) / len(points)

    m = folium.Map(
        location=[avg_lat, avg_lon],
        zoom_start=17,
        tiles=None
    )

    # Esri satellite imagery
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri",
        name="Esri World Imagery",
        overlay=False,
        control=True
    ).add_to(m)

    # Add markers
    for i, (lat, lon) in enumerate(points):
        colour = "blue" if i == 0 else "purple"
        folium.CircleMarker(
            location=[lat, lon],
            radius=5,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=1
        ).add_to(m)

    folium.LayerControl().add_to(m)

    m.save(output_file)


# Example
points = [
    getit(point),
]


for k in [-1,-0.8,-0.6,-0.4,-0.2,0,0.2,0.4,0.6,0.8,1]:
    point["screen"] = k
    points.append(geo_mapping.offRoad(point))

print(point)
create_map(points, "test/map_test/camera_test.html")