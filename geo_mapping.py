from pathlib import Path
from folium.plugins import MarkerCluster
import csv
import folium 



LATITUDE = "camera_latitude"
LONGITUDE = "camera_longitude" 


def clean_text(row, column):
    value = row.get(column)
    
    if value is None: 
        value = ""
    return value.strip()

#retrieve the details of a specific point: 
def retrieve_info(point):
    return (
            f"<b>{point['class_name']}</b>"
            f"<br>id: {point['object_id']}"
            f"<br>confidence score: {point['confidence']}"
            f"<br>({point['latitude']:.6f}, {point['longitude']:.6f})"
        )



#Read a ~/Documents/RoadSight/reports/<Input File Name>/detection_details_with_gps.csv
#and return only the rows are not empty. 

#Returns a list of dicts in the form of:
#[{"lat": float, "lon": float, "class_name": str, "object_id": str, "confidence": str}, ...]

def read_csv_input(csv_path):
    
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    points = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            #Get raw long and lat text only the non-empty rows:  
            latitude_text = clean_text(row, LATITUDE)
            longtitude_text = clean_text(row, LONGITUDE)
            

            # Skip rows with no GPS (empty lat/lon)
            if not latitude_text or not longtitude_text:
                continue
            try:
                #convert to float
                lat = float(latitude_text)
                lon = float(longtitude_text)
            except ValueError:
                continue
            #Read the columns from row
            points.append({
                "latitude": lat,
                "longitude": lon,
                "class_name": clean_text(row, "class_name"),
                "object_id": clean_text(row,"object_id"),
                "confidence": clean_text(row,"confidence"),
            })
    return points


#Give a color for each class of object
CLASS_COLORS = [
    "red", "blue", "green", "purple", "orange",
    "darkred", "cadetblue", "darkgreen", "darkblue", "pink"]

#Assign and remember a color for each class name
#color is assigned based on order in csv file 
def assign_color_for_class(class_name, mapping):
    
    if class_name not in mapping:
        mapping[class_name] = CLASS_COLORS[len(mapping) % len(CLASS_COLORS)]
    return mapping[class_name]



# Build a folium map from a list of point from read_csv_input and then save it as html
# Returns the output path as a string 

def build_map(points, output_html):
    #
    output_html = Path(output_html)
    if not points:
        raise ValueError("No data to map, csv file coordinates empty")
    # Center the map on the average of all points.

    avg_lat = sum(p["latitude"] for p in points) / len(points)
    avg_lon = sum(p["longitude"] for p in points) / len(points)

    #Set the location of the map at center of all points calculated above:  
    folium_map = folium.Map(location=[avg_lat, avg_lon], zoom_start=12)

    #cluster for seperating overlapse marker: 
    cluster = MarkerCluster().add_to(folium_map)
    color_map = {}
    for p in points:
        color = assign_color_for_class(p["class_name"], color_map)
        popup_html = retrieve_info(p)
        folium.Marker(
            location=[p["latitude"], p["longitude"]],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=p["class_name"],
            icon=folium.Icon(color=color, icon="info-sign"),
        ).add_to(cluster)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    folium_map.save(str(output_html))
    return str(output_html)


#Entry point function: Calling read_csv_input and build_map
def build_map_from_csv(csv_path, output):

    points = read_csv_input(csv_path)
    map = build_map(points, output)
    return map 
