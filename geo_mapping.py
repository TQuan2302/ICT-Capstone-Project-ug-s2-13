from pathlib import Path
from folium.plugins import FeatureGroupSubGroup, MarkerCluster
import csv
import folium
import base64

#for confidence level slider: 
from branca.element import MacroElement, Template


LATITUDE = "camera_latitude"
LONGITUDE = "camera_longitude" 


#Check if the entry is there or not: 
def clean_text(row, column):
    value = row.get(column)
    
    if value is None: 
        value = ""
    return value.strip()

#retrieve the details of a specific point: 
def retrieve_info(point):
    html_file =  (
            f"<b>{point['class_name']}</b>"
            f"<br>id: {point['object_id']}"
            f"<br>confidence score: {point['confidence']}"
            f"<br>({point['latitude']:.6f}, {point['longitude']:.6f})"
        )
    source_video = point.get("source_video")
    if source_video:
        html_file = html_file + f"<br>video: {source_video}"

    data_uri = point.get("snapshot_data_uri")

    #Generate the html onbject for the snapshot and add it to html_file
    if data_uri is not None: 
        html_file = html_file + (
            f'<br><img src="{data_uri}" width="420" '
            f'style="margin-top:6px;border-radius:4px;">'
        )

    return html_file



#Read a ~/Documents/RoadSight/reports/<Input File Name>/detection_details_with_gps.csv
#and return only the rows are not empty. 

#Returns a list of dicts in the form of:
#[{"lat": float, "lon": float, "class_name": str, "object_id": str, "confidence": str}, ...]

def read_csv_input(csv_path, encode_snapshots=True):
    
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
            point = {
                "latitude": lat,
                "longitude": lon,
                "class_name": clean_text(row, "class_name"),
                "object_id": clean_text(row,"object_id"),
                "confidence": clean_text(row,"confidence"),
            }

            if encode_snapshots:
                point["snapshot_data_uri"] = image_to_data_uri(snapshot_path_for_point(point, csv_path))
            else:
                point["snapshot_data_uri"] = None

            points.append(point)
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

#Helper Functions for filtering: 
#Keep only detections whose class_name is in selected_classes.
#Selected_classes=None (or empty) means show every class.
#Matching is case-insensitive and ignores extra spaces.

def filter_points_by_class(points, selected_classes=None):

    if not selected_classes:
        return points

    allowed = set()
    #remove blank class and class with space only: 
    for name in selected_classes: 
        if name is not None and name.strip() != "":
            cleaned_text = name.strip().lower()
            allowed.add(cleaned_text)

    if not allowed:
        return points
    
    filtered_points = []
    #Retrieve only points with allowed class: 
    for point in points: 
        class_name = point["class_name"].lower()
        if class_name in allowed: 
            filtered_points.append(point)
    return filtered_points


def class_layer_name(class_name):
    return class_name or "unknown"

# Function for Layer Control checkbox per class. Markers still share the same cluster
# show=False: start hidden / unchecked; user must tick a class to see it
def get_class_layer(class_name, cluster, layers, folium_map):
    
    name = class_layer_name(class_name)

    if name not in layers:
        #Create the "named group" which is named of "name" inside the specific "cluster"
        layer = FeatureGroupSubGroup(cluster, name=name, show=False)
        folium_map.add_child(layer)
        layers[name] = layer
    return layers[name]


# Helpers for image displaying.

# Snapshots live next to the CSV as: snapshots/<class_name>_id<track_id>_last.jpg
# object_id in the CSV is usually "<class_name>_<track_id>" (e.g. "pothole_12").

#generate the path for each object displayed in the cluster: 
def snapshot_path_for_point(point, csv_path):
    class_name = point["class_name"]
    object_id = point["object_id"]

    #Get the object id: 
    # try to get teh known class prefix, otherwise take the part after the last "_".
    expected_prefix = f"{class_name}_"
    if object_id.startswith(expected_prefix):
        track_id = object_id.removeprefix(expected_prefix)
    else:
        track_id = object_id.rsplit("_", 1)[-1]

    snapshot_name = f"{class_name}_id{track_id}_last.jpg"
    return Path(csv_path).parent / "snapshots" / snapshot_name


#Check if the path of an image is exist or not
#If it exist then convert it to the text string so the HTML map can read it and display it 
def image_to_data_uri(image_path):
    image_path = Path(image_path)
    if not image_path.exists():
        return None
    
    #Read the file and encode it as an ascii text
    encoded_sring = base64.b64encode(image_path.read_bytes()).decode("ascii")

    #Build the full uri
    return f"data:image/jpeg;base64,{encoded_sring}"

# Copy the slider CSS and JavaScript into the saved map HTML.
class ConfidenceSlider(MacroElement):
    def __init__(self, items_js):
        super().__init__()
        self._name = "ConfidenceSlider"

        # Marker list from build_map: each marker, its class layer, and its confidence.
        self.items_js = items_js

        code_folder = Path(__file__).parent
        self.slider_css = (code_folder / "confidence_slider.css").read_text(encoding="utf-8")
        self.slider_js = (code_folder / "confidence_slider.js").read_text(encoding="utf-8")

        # Inject the .css file into the html <style>.
        css_part = """
            {% macro header(this, kwargs) %}
                <style>
                    {{ this.slider_css }}
                </style>
            {% endmacro %}
        """

        # Inject the .js file into the page html <script> then start the slider.
        js_part = """
            {% macro script(this, kwargs) %}
                {{ this.slider_js }}
                addConfidenceSlider({{ this._parent.get_name() }}, [
                    {{ this.items_js }}
                ]);
            {% endmacro %}
        """
        self._template = Template(css_part + js_part)

# Build a folium map from a list of point from read_csv_input and then save it as html
# Returns the output path as a string 

def build_map(points, output_html, selected_classes=None):
    output_html = Path(output_html)
    points = filter_points_by_class(points, selected_classes)

    if not points:
        raise ValueError("No data to map, csv file coordinates empty")

    # Center the map on the average of all points.
    avg_lat = sum(p["latitude"] for p in points) / len(points)
    avg_lon = sum(p["longitude"] for p in points) / len(points)

    
    # test Esri map: 
    folium_map = folium.Map(
        location=[avg_lat, avg_lon],
        zoom_start=12,
        tiles="Esri.WorldStreetMap",
    )

    # Shared cluster so overlapping pins still group; LayerControl lists each class.
    cluster = MarkerCluster(control=False)
    folium_map.add_child(cluster)
    class_layers = {}

    color_map = {}
    tracked_markers = []
    for p in points:
        try:
            confidence_value = float(p["confidence"])
        except ValueError:
            confidence_value = 0.0

        color = assign_color_for_class(p["class_name"], color_map)
        popup_html = retrieve_info(p)
        class_layer = get_class_layer(p["class_name"], cluster, class_layers, folium_map)
        tooltip = p["class_name"]
        if p.get("source_video"):
            tooltip = f"{p['class_name']} ({p['source_video']})"
        marker = folium.Marker(
            location=[p["latitude"], p["longitude"]],
            popup=folium.Popup(popup_html, max_width=470),
            tooltip=tooltip,
            icon=folium.Icon(color=color, icon="info-sign"),
            confidence=confidence_value,
        )
        marker.add_to(class_layer)
        tracked_markers.append((marker.get_name(), class_layer.get_name(), confidence_value))

    folium.LayerControl(collapsed=False).add_to(folium_map)

    marker_lines = []
    for marker_name, group_name, confidence_value in tracked_markers:
        marker_lines.append(
            f"{{marker: {marker_name}, group: {group_name}, confidence: {confidence_value}}}"
        )
    ConfidenceSlider(",\n".join(marker_lines)).add_to(folium_map)
    #Create the folder holding the map html file if necessary
    output_html.parent.mkdir(parents=True, exist_ok=True)

    #Draw the map to  html file
    folium_map.save(str(output_html))
    return str(output_html)


# True when this video's saved HTML is newer than its CSV, so nothing needs rebuilding.
def map_html_is_current(csv_path, output_html):
    output_html = Path(output_html)
    csv_path = Path(csv_path)
    if not output_html.is_file() or not csv_path.is_file():
        return False
    return csv_path.stat().st_mtime_ns <= output_html.stat().st_mtime_ns


#Entry point function: Calling read_csv_input and build_map.
#Opens the saved detection_map.html when it is already newer than this video's CSV.
def build_map_from_csv(csv_path, output, selected_classes=None):
    if not selected_classes and map_html_is_current(csv_path, output):
        return str(output)

    points = read_csv_input(csv_path)
    map = build_map(points, output, selected_classes=selected_classes)
    return map 
