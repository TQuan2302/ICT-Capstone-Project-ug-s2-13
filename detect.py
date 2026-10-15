from pathlib import Path
from datetime import timedelta
import sys
import shutil
import cv2
import numpy as np
import csv
from ultralytics import YOLO
import json

import detection_settings

try:
    from gps_from_mov import extract_mov_gps_points
except Exception:
    extract_mov_gps_points = None

try:
    from video_convert import convert_mov_to_mp4
except Exception:
    convert_mov_to_mp4 = None

try:
    from gps_from_gpx import extract_gpx_points
except Exception:
    extract_gpx_points = None

# =========================
# Basic paths
# =========================

# Read-only bundle assets (models, etc.) — use sys._MEIPASS when frozen.
if getattr(sys, 'frozen', False):
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent

# Writable user data lives outside the bundle so it survives updates.
_DATA_DIR = Path.home() / "Documents" / "RoadSight"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

INPUT_DIR = _DATA_DIR / "uploads"
OUTPUT_DIR = _DATA_DIR / "results"
REPORT_DIR = _DATA_DIR / "reports"
PROCESSED_DIR = INPUT_DIR / "processed"
CONVERTED_DIR = INPUT_DIR / "converted"

FOOTPATH_MODEL = ROOT / "models" / "footpath_best.pt"
ROAD_MODEL = ROOT / "models" / "road_evidence_best.pt"
TRUNK_MODEL = ROOT / "models" / "trunk.pt"
POLE_MODEL = ROOT / "models" / "pole.pt"
TRAFFIC_LIGHT_MODEL = ROOT / "models" / "trafficlight.pt"
ROAD_BARRIER_MODEL = ROOT / "models" / "road_barriers.pt"
BIKE_LANE_MODEL = ROOT / "models" / "bike_lane.pt"
TRAFFIC_SIGN_MODEL = ROOT / "models" / "traffic_sign.pt"

SETTINGS_FILE = _DATA_DIR / "detection_settings.json"

# Load per-model settings saved by detection_settings.py.
# Returns an empty dict if the file does not exist or is corrupt.
def load_user_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# =========================
# Base confidence settings
# =========================
# Important:
# For models with per-class confidence, use a low base confidence first.
# Then filter by class-specific thresholds later.

FOOTPATH_CONF = 0.10

ROAD_CONF = 0.05

TRUNK_CONF = 0.55
POLE_CONF = 0.25

# YOLO default traffic light model.
# Keep this higher because we only want reliable traffic light boxes.
TRAFFIC_LIGHT_CONF = 0.35

ROAD_BARRIER_CONF = 0.25
BIKE_LANE_CONF = 0.1

# Traffic sign model has many classes.
# Keep base confidence low, then apply TRAFFIC_SIGN_CLASS_CONF below.
TRAFFIC_SIGN_CONF = 0.05


# =========================
# Per-class confidence settings
# =========================

ROAD_CLASS_CONF = {
    "crosswalk_marking": 0.60,
    "lane_marking": 0.60,
    "stop_line": 0.01,
}

TRAFFIC_SIGN_CLASS_CONF = {
    "bicycle_sign": 0.25,
    "curve_ahead": 0.25,
    "give_way": 0.20,
    "information": 0.30,
    "intersection": 0.25,
    "keep_left_right": 0.25,
    "no_entry": 0.30,
    "no_parking": 0.30,
    "no_stopping": 0.30,
    "one_way": 0.30,
    "other_sign": 0.45,
    "parking": 0.30,
    "pedestrian_crossing": 0.25,
    "railroad_crossing": 0.20,
    "road_works": 0.25,
    "roundabout": 0.25,
    "school_zone": 0.20,
    "speed_limit": 0.35,
    "stop_sign": 0.25,
    "traffic_signals": 0.30,
    "turn_restriction": 0.30,
    "vehicle_restriction": 0.30,
    "warning": 0.35,
    "wildlife_crossing": 0.20,
}


# =========================
# Video and file settings
# =========================

VIDEO_SIZE = (640, 360)
SKIP_FRAMES = 2

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".insv"}


# =========================
# Labels
# =========================

ROAD_EVIDENCE_LABELS = {
    "crosswalk_marking",
    "lane_marking",
    "stop_line",
}

TRAFFIC_LIGHT_LABELS = {
    "traffic_light",
}

TRAFFIC_SIGN_LABELS = {
    "bicycle_sign",
    "curve_ahead",
    "give_way",
    "information",
    "intersection",
    "keep_left_right",
    "no_entry",
    "no_parking",
    "no_stopping",
    "one_way",
    "other_sign",
    "parking",
    "pedestrian_crossing",
    "railroad_crossing",
    "road_works",
    "roundabout",
    "school_zone",
    "speed_limit",
    "stop_sign",
    "traffic_signals",
    "turn_restriction",
    "vehicle_restriction",
    "warning",
    "wildlife_crossing",
}


# =========================
# Colors
# =========================
# OpenCV uses BGR color order.

COLOR_MAP = {
    "footpath": (0, 255, 0),              # green
    "crosswalk_marking": (255, 0, 0),     # blue
    "lane_marking": (0, 0, 255),          # red
    "stop_line": (0, 255, 255),           # yellow
    "trunk": (0, 165, 255),               # orange
    "pole": (255, 0, 255),                # purple
    "traffic_light": (255, 255, 0),       # cyan
    "road_barrier": (255, 128, 0),        # light blue
    "bike_lane": (128, 0, 255),           # violet
}

TRAFFIC_SIGN_COLOR = (0, 128, 255)        # orange-like


# =========================
# Model configuration
# =========================

MODEL_CONFIGS = [
    {
        "name": "footpath",
        "path": FOOTPATH_MODEL,
        "conf": FOOTPATH_CONF,
        "force_label": "footpath",
        "allowed_labels": None,
        "class_conf": None,
        "alpha": 0.40,
    },
    {
        "name": "road_evidence",
        "path": ROAD_MODEL,
        "conf": ROAD_CONF,
        "force_label": None,
        "allowed_labels": ROAD_EVIDENCE_LABELS,
        "class_conf": ROAD_CLASS_CONF,
        "alpha": 0.50,
    },
    {
        "name": "trunk",
        "path": TRUNK_MODEL,
        "conf": TRUNK_CONF,
        "force_label": "trunk",
        "allowed_labels": None,
        "class_conf": None,
        "alpha": 0.45,
    },
    {
        "name": "pole",
        "path": POLE_MODEL,
        "conf": POLE_CONF,
        "force_label": "pole",
        "allowed_labels": None,
        "class_conf": None,
        "alpha": 0.45,
    },
    {
        "name": "traffic_light",
        "path": TRAFFIC_LIGHT_MODEL,
        "conf": TRAFFIC_LIGHT_CONF,

        # Do not force all YOLO default detections to traffic_light.
        # Only keep actual traffic light detections.
        "force_label": None,
        "allowed_labels": TRAFFIC_LIGHT_LABELS,

        "class_conf": None,
        "alpha": 0.45,
    },
    {
        "name": "road_barrier",
        "path": ROAD_BARRIER_MODEL,
        "conf": ROAD_BARRIER_CONF,
        "force_label": "road_barrier",
        "allowed_labels": None,
        "class_conf": None,
        "alpha": 0.45,
    },
    {
        "name": "bike_lane",
        "path": BIKE_LANE_MODEL,
        "conf": BIKE_LANE_CONF,
        "force_label": "bike_lane",
        "allowed_labels": None,
        "class_conf": None,
        "alpha": 0.45,
    },
    {
        "name": "traffic_sign",
        "path": TRAFFIC_SIGN_MODEL,
        "conf": TRAFFIC_SIGN_CONF,

        # Keep original traffic sign class names.
        # Example: speed_limit, stop_sign, no_parking, warning.
        "force_label": None,
        "allowed_labels": TRAFFIC_SIGN_LABELS,

        # Apply per-class confidence for each traffic sign type.
        "class_conf": TRAFFIC_SIGN_CLASS_CONF,
        "alpha": 0.45,
    },
]


# =========================
# Helper functions
# =========================

def save_report_csv_by_stem(report_stem, counts):
    """
    Save normal summary report.

    This keeps the existing UI working because the report still uses:
    Class, Count
    """
    report_folder = REPORT_DIR / report_stem
    report_folder.mkdir(parents=True, exist_ok=True)

    csv_path = report_folder / "detection_report.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Class", "Count"])

        for label, count in counts.items():
            writer.writerow([label, count])

    print(f"CSV report saved: {csv_path}")


def save_report_csv(file_path, counts):
    """
    Original function kept for image processing compatibility.
    """
    save_report_csv_by_stem(file_path.stem, counts)


def save_detection_details_csv(report_stem, rows):
    """
    Save detailed object-level detection rows.

    This is the useful GPS/geospatial output file.
    One row = one unique tracked object.
    """
    report_folder = REPORT_DIR / report_stem
    report_folder.mkdir(parents=True, exist_ok=True)

    csv_path = report_folder / "detection_details_with_gps.csv"

    fieldnames = [
        "source_file",
        "processed_file",
        "object_id",
        "class_name",
        "last_frame_time_sec",
        "camera_latitude",
        "camera_longitude",
        "camera_elevation",
        "camera_speed",
        "camera_angle",
        "confidence",
        "side_of_frame",
    ]
    

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Detection details CSV saved: {csv_path}")

def normalize_label_name(label):
    """
    Normalize YOLO class names.

    Examples:
        "traffic light" -> "traffic_light"
        "0_crosswalk_marking" -> "crosswalk_marking"
        "1_lane_marking" -> "lane_marking"
        "2_stop_line" -> "stop_line"
    """
    text = str(label).strip().lower()
    text = text.replace("-", "_").replace(" ", "_")

    parts = text.split("_", 1)
    if len(parts) == 2 and parts[0].isdigit():
        text = parts[1]

    return text


def normalize_label_set(labels):
    """
    Normalize every label in a set.
    """
    if labels is None:
        return None

    return {normalize_label_name(label) for label in labels}


def normalize_conf_dict(conf_dict):
    """
    Normalize keys in a confidence dictionary.
    """
    if conf_dict is None:
        return None

    return {
        normalize_label_name(label): conf
        for label, conf in conf_dict.items()
    }


def get_label_name(result, class_id):
    """
    Convert YOLO class id to normalized class name.
    """
    try:
        raw_label = result.names[int(class_id)]
    except Exception:
        raw_label = str(class_id)

    return normalize_label_name(raw_label)


def get_color(label):
    """
    Get drawing color for a label.
    """
    label = normalize_label_name(label)

    if label in TRAFFIC_SIGN_LABELS:
        return TRAFFIC_SIGN_COLOR

    return COLOR_MAP.get(label, (255, 255, 255))


def should_keep_detection(label, conf, class_conf=None):
    """
    Apply class-specific confidence threshold.

    If class_conf is None, keep all detections that passed YOLO's base conf.
    If class_conf exists, use the threshold for that class.
    """
    if class_conf is None:
        return True

    label = normalize_label_name(label)
    class_conf = normalize_conf_dict(class_conf)

    threshold = class_conf.get(label, 0.25)
    return conf >= threshold

# Draw readable label text with black outline.
# font_scale controls the OpenCV text size (default 0.55).
def put_label(frame, text, x, y, color, font_scale=0.55):
    y = max(20, y)

    # Outline pass
    cv2.putText(
        frame,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (0, 0, 0),
        4,
    )

    # Coloured pass
    cv2.putText(
        frame,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        color,
        2,
    )


def draw_masks_and_boxes(
    frame,
    result,
    allowed_labels=None,
    force_display_label=None,
    alpha=0.45,
    draw_contours=True,
    draw_boxes=True,
    class_conf=None,
    font_scale=0.55,  
):
    """
    Draw YOLO result on frame.

    Supports:
        1. segmentation models with masks
        2. detection models with boxes only
    """
    output = frame.copy()
    overlay = frame.copy()
    counts = {}

    h, w = frame.shape[:2]

    boxes = result.boxes
    masks = result.masks

    if boxes is None:
        return output, counts

    allowed_labels = normalize_label_set(allowed_labels)
    class_conf = normalize_conf_dict(class_conf)

    class_ids = boxes.cls.cpu().numpy().astype(int)
    confs = boxes.conf.cpu().numpy()

    # =========================
    # Draw segmentation masks
    # =========================

    if masks is not None:
        mask_data = masks.data.cpu().numpy()

        for i, mask_raw in enumerate(mask_data):
            class_id = class_ids[i]
            conf = float(confs[i])

            original_label = get_label_name(result, class_id)

            if force_display_label is not None:
                display_label = normalize_label_name(force_display_label)
            else:
                display_label = original_label

            if allowed_labels is not None and original_label not in allowed_labels:
                continue

            if not should_keep_detection(original_label, conf, class_conf):
                continue

            color = get_color(display_label)

            mask_resized = cv2.resize(mask_raw, (w, h))
            mask = mask_resized > 0.5

            mask_area = int(mask.sum())
            frame_area = h * w
            area_ratio = mask_area / max(frame_area, 1)

            if area_ratio < 0.00003:
                continue

            counts[display_label] = counts.get(display_label, 0) + 1

            if display_label == "lane_marking":
                mask_uint8 = mask.astype(np.uint8) * 255
                contours, _ = cv2.findContours(
                    mask_uint8,
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE,
                )
                cv2.drawContours(overlay, contours, -1, color, 3)

            elif display_label == "stop_line":
                mask_uint8 = mask.astype(np.uint8) * 255
                contours, _ = cv2.findContours(
                    mask_uint8,
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE,
                )
                cv2.drawContours(overlay, contours, -1, color, 4)

                overlay[mask] = (
                    0.65 * overlay[mask]
                    + 0.35 * np.array(color, dtype=np.uint8)
                ).astype(np.uint8)

            elif display_label in {
                "trunk",
                "pole",
                "traffic_light",
                "road_barrier",
                "bike_lane",
            } or display_label in TRAFFIC_SIGN_LABELS:
                overlay[mask] = (
                    (1 - alpha) * overlay[mask]
                    + alpha * np.array(color, dtype=np.uint8)
                ).astype(np.uint8)

                mask_uint8 = mask.astype(np.uint8) * 255
                contours, _ = cv2.findContours(
                    mask_uint8,
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE,
                )
                cv2.drawContours(overlay, contours, -1, color, 3)

            else:
                overlay[mask] = (
                    (1 - alpha) * overlay[mask]
                    + alpha * np.array(color, dtype=np.uint8)
                ).astype(np.uint8)

                if draw_contours:
                    mask_uint8 = mask.astype(np.uint8) * 255
                    contours, _ = cv2.findContours(
                        mask_uint8,
                        cv2.RETR_EXTERNAL,
                        cv2.CHAIN_APPROX_SIMPLE,
                    )
                    cv2.drawContours(overlay, contours, -1, color, 2)

            x1, y1, x2, y2 = map(int, boxes.xyxy[i].tolist())
            


            put_label(
                overlay,
                f"{display_label} {conf:.2f}",
                x1,
                y1 - 6,
                color,
                font_scale
            )

    # =========================
    # Draw boxes only
    # =========================

    else:
        for i, b in enumerate(boxes):
            class_id = int(b.cls[0])
            conf = float(b.conf[0])

            original_label = get_label_name(result, class_id)

            if force_display_label is not None:
                display_label = normalize_label_name(force_display_label)
            else:
                display_label = original_label

            if allowed_labels is not None and original_label not in allowed_labels:
                continue

            if not should_keep_detection(original_label, conf, class_conf):
                continue

            counts[display_label] = counts.get(display_label, 0) + 1

            color = get_color(display_label)
            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())

            if draw_boxes:
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

            put_label(
                overlay,
                f"{display_label} {conf:.2f}",
                x1,
                y1 - 6,
                color,
                font_scale
            )

    output = overlay
    return output, counts


def merge_counts(a, b):
    """
    Merge two count dictionaries.
    """
    merged = dict(a)

    for key, value in b.items():
        merged[key] = merged.get(key, 0) + value

    return merged


def print_counts(title, counts):
    """
    Print detection counts.
    """
    print(title)

    if not counts:
        print("  No detections")
        return

    for label, count in counts.items():
        print(f"  {label}: {count}")


def get_output_path(file_path):
    """
    Generate output path in results folder.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    if file_path.suffix.lower() in IMAGE_EXTS:
        return OUTPUT_DIR / f"detected_{file_path.stem}.png"

    return OUTPUT_DIR / f"detected_{file_path.stem}.mp4"


# =========================
# Model loading
# =========================

#   Load all available models, applying any user settings from
#   detection_settings.json (enabled flag, alpha, font_scale).
#   Missing models are skipped.
#   Disabled models are skipped.
#   At least one model must be enabled and present.

def load_models():
    user_settings = load_user_settings()
    loaded_models = []

    for config in MODEL_CONFIGS:
        model_name = config["name"]
        model_path = config["path"]

        # ── Respect enabled/disabled toggle ───────────────────────────
        model_setting = user_settings.get(model_name, {})
        if not model_setting.get("enabled", True):
            print(f"{model_name} model disabled by user settings, skipped.")
            continue

        # ── Apply user overrides (shallow copy keeps MODEL_CONFIGS clean)
        effective_config = dict(config)

        if "alpha" in model_setting:
            effective_config["alpha"] = float(model_setting["alpha"])

        # font_scale defaults to 0.55 if not yet in the settings file
        effective_config["font_scale"] = float(
            model_setting.get("font_scale", 0.55)
        )

        if not model_path.exists():
            print(f"{model_name} model not found, skipped: {model_path}")
            continue

        print(
            f"Using {model_name} model: {model_path}  "
            f"alpha={effective_config['alpha']:.2f}  "
            f"font_scale={effective_config['font_scale']:.2f}"
        )

        model = YOLO(str(model_path))
        print(f"{model_name} model classes: {model.names}")

        loaded_models.append({
            "config": effective_config,
            "model": model,
        })

    if not loaded_models:
        expected = "\\n".join(str(c["path"]) for c in MODEL_CONFIGS)
        raise FileNotFoundError(
            "No detection models found or all are disabled.\\n"
            "Please place at least one model in models folder or re-enable "
            "models in Detection Settings:\\n" + expected
        )

    return loaded_models


# =========================
# Core processing
# =========================

def process_frame(frame, loaded_models):
    """
    Process one frame using all loaded models.
    """
    result_frame = frame.copy()
    total_counts = {}

    for item in loaded_models:
        config = item["config"]
        model = item["model"]

        result = model.predict(
            source=frame,
            conf=config["conf"],
            save=False,
            verbose=False,
        )[0]

        result_frame, counts = draw_masks_and_boxes(
            frame=result_frame,
            result=result,
            allowed_labels=config["allowed_labels"],
            force_display_label=config["force_label"],
            alpha=config["alpha"],
            draw_contours=True,
            draw_boxes=True,
            class_conf=config["class_conf"],
            font_scale=config.get("font_scale", 0.55),
        )

        total_counts = merge_counts(total_counts, counts)

    return result_frame, total_counts


def process_image(file_path, loaded_models):
    """
    Process one image file.
    """
    frame = cv2.imread(str(file_path))

    if frame is None:
        print(f"Cannot read image: {file_path}")
        return False

    result, counts = process_frame(frame, loaded_models)

    output_path = get_output_path(file_path)
    cv2.imwrite(str(output_path), result)

    print(f"Image: {file_path.name}")
    print_counts("Detections:", counts)
    print(f"Output: {output_path}")

    save_report_csv(file_path, counts)

    return True

def frame_side(x1, x2, frame_width):
    """
    Simple estimate of where the object appears in the frame.
    This does not calculate real-world object position.
    It only says whether the object is visually left, center, or right.
    """
    center_x = (x1 + x2) / 2

    if center_x < frame_width / 3:
        return "left"
    elif center_x < 2 * frame_width / 3:
        return "center"
    else:
        return "right"


def find_closest_gps_point(target_time, gps_points):
    """
    Match a video frame time to the closest GPS timestamp.
    """
    if not gps_points:
        return None

    return min(
        gps_points,
        key=lambda p: abs((p["time"] - target_time).total_seconds())
    )


def get_gps_for_frame(frame_index, fps, gps_points):
    """
    Convert frame number into video time, then match to GPS.
    """
    if not gps_points:
        return None, None

    video_start_time = gps_points[0]["time"]
    frame_time_sec = frame_index / fps
    frame_absolute_time = video_start_time + timedelta(seconds=frame_time_sec)

    gps_point = find_closest_gps_point(frame_absolute_time, gps_points)

    return gps_point, frame_time_sec


def try_extract_gps_from_mov(file_path):
    """
    Try to extract GPS from MOV.

    If it fails, do not crash the whole detection.
    The system can still run normal detection without GPS.
    """
    if extract_mov_gps_points is None:
        print("GPS extraction module not available. Skipping GPS.")
        return []

    try:
        gps_points = extract_mov_gps_points(file_path)
        print(f"Loaded {len(gps_points)} GPS points from MOV.")
        return gps_points
    except Exception as e:
        print(f"GPS extraction failed. Continuing without GPS. Reason: {e}")
        return []

def try_extract_gps_from_gpx(gpx_path):
    """
    Try to extract GPS points from a GPX file.

    This is mainly used for Insta360 exports:
    MP4/INSV video + matching GPX file.
    """
    if not gpx_path:
        return []

    if extract_gpx_points is None:
        print("GPX extraction module not available. Skipping GPX.")
        return []

    try:
        gps_points = extract_gpx_points(gpx_path)
        print(f"Loaded {len(gps_points)} GPS points from GPX.")
        return gps_points
    except Exception as e:
        print(f"GPX extraction failed. Continuing without GPS. Reason: {e}")
        return []


def try_convert_insv_for_processing(file_path):
    """
    Convert INSV into clean MP4 for OpenCV.

    Some INSV files may work directly, but OpenCV is more reliable with MP4.
    This uses the same FFmpeg conversion function as MOV.
    """
    if convert_mov_to_mp4 is None:
        print("Video converter module not available. Trying original INSV.")
        return file_path

    try:
        CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

        clean_path = CONVERTED_DIR / f"{file_path.stem}_clean.mp4"

        convert_mov_to_mp4(
            str(file_path),
            str(clean_path)
        )

        print(f"INSV converted for processing: {clean_path}")
        return clean_path

    except Exception as e:
        print(f"INSV conversion failed. Trying original INSV. Reason: {e}")
        return file_path

def try_convert_mov_for_processing(file_path):
    """
    Convert MOV into clean MP4 for OpenCV.

    If conversion fails, fall back to the original file.
    """
    if convert_mov_to_mp4 is None:
        print("MOV converter module not available. Trying original MOV.")
        return file_path

    try:
        CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

        clean_path = CONVERTED_DIR / f"{file_path.stem}_clean.mp4"

        convert_mov_to_mp4(
            str(file_path),
            str(clean_path)
        )

        print(f"MOV converted for processing: {clean_path}")
        return clean_path

    except Exception as e:
        print(f"MOV conversion failed. Trying original MOV. Reason: {e}")
        return file_path


def get_video_output_path(output_stem):
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR / f"detected_{output_stem}.mp4"

def process_video(
    file_path,
    loaded_models,
    gps_points=None,
    source_file_path=None,
    output_stem=None
):
    """
    Process one video file.

    Supports:
    - normal MP4/AVI/MKV detection
    - MOV detection with optional GPS
    - object-level GPS CSV output
    """
    file_path = Path(file_path)

    if gps_points is None:
        gps_points = []

    if source_file_path is None:
        source_file_path = file_path
    else:
        source_file_path = Path(source_file_path)

    if output_stem is None:
        output_stem = source_file_path.stem

    cap = cv2.VideoCapture(str(file_path))

    if not cap.isOpened():
        print(f"Cannot open video: {file_path}")
        return False

    fps = cap.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        fps = 25

    output_path = get_video_output_path(output_stem)

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        VIDEO_SIZE,
    )

    if not writer.isOpened():
        cap.release()
        print(f"Cannot create output video: {output_path}")
        return False

    # label -> set of unique integer track IDs seen so far
    seen_ids = {}

    # Stores the LATEST frame data for each unique detected object.
    # Overwritten on every frame so the final entry holds the last
    # position and GPS reading for that object.
    last_seen_data = {}

    frame_count = 0
    last_result_frame = None

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        frame = cv2.resize(frame, VIDEO_SIZE)

        if frame_count % SKIP_FRAMES == 0 or last_result_frame is None:
            result_frame = frame.copy()

            gps_point, frame_time_sec = get_gps_for_frame(
                frame_index=frame_count,
                fps=fps,
                gps_points=gps_points
            )

            if frame_time_sec is None:
                frame_time_sec = frame_count / fps

            for item in loaded_models:
                config = item["config"]
                model = item["model"]

                # Track individual detected elements
                track_results = model.track(
                    source=frame,
                    conf=config["conf"],
                    persist=True,
                    # Ultralystics library feature -> keep same ID for same object across frames
                    tracker="bytetrack.yaml", 
                    save=False,
                    verbose=False,
                )

                if not track_results:
                    continue

                result = track_results[0]

                result_frame, _ = draw_masks_and_boxes(
                    frame=result_frame,
                    result=result,
                    allowed_labels=config["allowed_labels"],
                    force_display_label=config["force_label"],
                    alpha=config["alpha"],
                    draw_contours=True,
                    draw_boxes=True,
                    class_conf=config["class_conf"],
                )

                boxes = result.boxes

                if boxes is None or boxes.id is None:
                    continue

                track_ids = boxes.id.cpu().numpy().astype(int)
                class_ids = boxes.cls.cpu().numpy().astype(int)
                confs = boxes.conf.cpu().numpy()

                allowed = normalize_label_set(config["allowed_labels"])
                class_conf = normalize_conf_dict(config["class_conf"])

                for i, track_id in enumerate(track_ids):
                    track_id = int(track_id)

                    label = get_label_name(result, class_ids[i])
                    conf = float(confs[i])

                    if allowed is not None and label not in allowed:
                        continue

                    if not should_keep_detection(label, conf, class_conf):
                        continue

                    display_label = (
                        normalize_label_name(config["force_label"])
                        if config["force_label"]
                        else label
                    )

                    if display_label not in seen_ids:
                        seen_ids[display_label] = set()

                    # Register this ID as seen whether new or not.
                    seen_ids[display_label].add(track_id)

                    x1, y1, x2, y2 = map(int, boxes.xyxy[i].tolist())
                    # Use red for every snapshot box/label regardless of class - for visualization purpose
                    box_color = (0, 0, 255)

                    # Draw box + label on this object's last-seen frame
                    snapshot = frame.copy()
                    cv2.rectangle(snapshot, (x1, y1), (x2, y2), box_color, 2)
                    put_label(
                        snapshot,
                        f"{display_label} {conf:.2f}", #Draw confident level
                        x1, #position of the lable horizontally
                        y1 - 6, #position of the lable vertically  - 6 pixels above the top edge
                        box_color,
                    )

                    # Always overwrite with the current frame's data.
                    # On first detection this creates the entry.
                    # On every subsequent detection this updates it with
                    # fresher GPS so the final entry holds the last frame.
                    last_seen_data[(display_label, track_id)] = {
                        "snapshot": snapshot,
                        "row": {
                            "source_file": source_file_path.name,
                            "processed_file": file_path.name,
                            "object_id": f"{display_label}_{track_id}",
                            "class_name": display_label,
                            "last_frame_time_sec": round(frame_time_sec, 3),
                            "camera_latitude": gps_point["latitude"] if gps_point else "",
                            "camera_longitude": gps_point["longitude"] if gps_point else "",
                            "camera_elevation": gps_point["elevation"] if gps_point else "",
                            "camera_speed": gps_point["speed"] if gps_point else "",
                            "camera_angle": gps_point["track"] if gps_point else "",
                            "confidence": round(conf, 4),
                            "side_of_frame": frame_side(x1, x2, VIDEO_SIZE[0]),
                        }
                    }

            last_result_frame = result_frame

        writer.write(last_result_frame)
        frame_count += 1

        if frame_count % 30 == 0:
            print(f"Frames processed: {frame_count}")

    cap.release()
    writer.release()

    snapshot_dir = REPORT_DIR / output_stem / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Build CSV rows and save snapshots from each object's last frame.
    detail_rows = []
    for (label, tid), data in last_seen_data.items():
        snap_path = snapshot_dir / f"{label}_id{tid}_last.jpg"
        cv2.imwrite(str(snap_path), data["snapshot"])
        detail_rows.append(data["row"])

    total_counts = {
        label: len(ids)
        for label, ids in seen_ids.items()
    }

    print(f"Video: {source_file_path.name}")
    print(f"Processed video file: {file_path.name}")
    print(f"Frames processed: {frame_count}")
    print_counts("Unique detections:", total_counts)
    print(f"Output: {output_path}")
    print(f"Snapshots saved to: {snapshot_dir}")

    if gps_points:
        print(f"GPS used: yes, {len(gps_points)} points")
    else:
        print("GPS used: no")

    save_report_csv_by_stem(output_stem, total_counts)
    save_detection_details_csv(output_stem, detail_rows)

    return True


def move_to_processed(file_path):
    """
    Move processed file to uploads/processed.
    """
    PROCESSED_DIR.mkdir(exist_ok=True)

    target_path = PROCESSED_DIR / file_path.name

    if target_path.exists():
        target_path = PROCESSED_DIR / f"{file_path.stem}_processed{file_path.suffix}"

    shutil.move(str(file_path), str(target_path))
    print(f"Moved original file to: {target_path}")


# =========================
# Public detection function
# =========================

def run_detection(input_path, gpx_path=None, move_original=False):
    """
    Process one image or video.

    MOV:
    - extract GPS from MOV automatically
    - convert MOV to clean MP4
    - run detection with GPS

    MP4:
    - if GPX is provided, use GPX GPS
    - otherwise run detection without GPS

    INSV:
    - if GPX is provided, use GPX GPS
    - convert INSV to clean MP4
    - run detection with GPS if available
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = input_path.suffix.lower()

    if suffix not in IMAGE_EXTS and suffix not in VIDEO_EXTS:
        raise ValueError(f"Unsupported file type: {input_path.suffix}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    loaded_models = load_models()

    if suffix in IMAGE_EXTS:
        success = process_image(input_path, loaded_models)

    else:
        gps_points = []
        process_video_path = input_path
        source_file_path = input_path
        output_stem = input_path.stem

        if suffix == ".mov":
            # MOV can use its own embedded GPS.
            gps_points = try_extract_gps_from_mov(input_path)
            process_video_path = try_convert_mov_for_processing(input_path)

        elif suffix == ".insv":
            # INSV uses matching GPX file for the safe workflow.
            gps_points = try_extract_gps_from_gpx(gpx_path)
            process_video_path = try_convert_insv_for_processing(input_path)

        else:
            # MP4/MKV/AVI can optionally use GPX.
            gps_points = try_extract_gps_from_gpx(gpx_path)

        success = process_video(
            file_path=process_video_path,
            loaded_models=loaded_models,
            gps_points=gps_points,
            source_file_path=source_file_path,
            output_stem=output_stem
        )

    if success and move_original:
        move_to_processed(input_path)

    return success


def process_all_uploads():
    """
    Process all images/videos in uploads folder.
    """
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Input folder not found: {INPUT_DIR}")

    files = [
        f for f in INPUT_DIR.iterdir()
        if f.is_file()
        and (
            f.suffix.lower() in IMAGE_EXTS
            or f.suffix.lower() in VIDEO_EXTS
        )
    ]

    if not files:
        print("No image or video files found in uploads.")
        return

    loaded_models = load_models()

    for file_path in files:
        suffix = file_path.suffix.lower()

        success = False

        if suffix in IMAGE_EXTS:
            success = process_image(file_path, loaded_models)

        elif suffix in VIDEO_EXTS:

            gps_points = []
            process_video_path = file_path

            if suffix == ".mov":
                gps_points = try_extract_gps_from_mov(file_path)
                process_video_path = try_convert_mov_for_processing(file_path)

            success = process_video(
                file_path=process_video_path,
                loaded_models=loaded_models,
                gps_points=gps_points,
                source_file_path=file_path,
                output_stem=file_path.stem
            )

        if success:
            move_to_processed(file_path)


# =========================
# Main script mode
# =========================

def main():
    """
    Usage:
        python detect.py
        python detect.py uploads/test.mp4
        python detect.py uploads/test.mp4 uploads/test.gpx
        python detect.py uploads/test.insv uploads/test.gpx
        python detect.py uploads/test.mov
    """
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]

        gpx_path = None
        if len(sys.argv) >= 3:
            gpx_path = sys.argv[2]

        run_detection(
            input_path=input_path,
            gpx_path=gpx_path,
            move_original=False
        )

    else:
        process_all_uploads()


if __name__ == "__main__":
    main()