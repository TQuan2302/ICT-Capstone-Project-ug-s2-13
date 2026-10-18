from pathlib import Path
from datetime import timedelta
from collections import Counter
import subprocess
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
if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)
else:
    here = Path(__file__).resolve().parent
    parent = here.parent
    ROOT = parent if (parent / "models").exists() else here

from roadsight_paths import DATA_DIR as DATA_DIR, seed_runtime_data

seed_runtime_data()

INPUT_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "results"
REPORT_DIR = DATA_DIR / "reports"
PROCESSED_DIR = INPUT_DIR / "processed"
CONVERTED_DIR = INPUT_DIR / "converted"

def resolve_model_path(filename: str) -> Path:
    key = Path(filename).stem
    candidates = [
        DATA_DIR / "retrain" / key / "live_weight" / filename,
        DATA_DIR / "models" / filename,
        ROOT / "models" / filename,
        Path(__file__).resolve().parent / "models" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return ROOT / "models" / filename

SPEED_LIMIT_MODEL = resolve_model_path("speed_limit_sign.pt")
SPEED_ADVISORY_MODEL = resolve_model_path("speed_advisory_sign.pt")
BIKE_LANE_MODEL = resolve_model_path("bike_lane.pt")

SETTINGS_FILE = DATA_DIR / "detection_settings.json"

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

SPEED_LIMIT_SIGN_CONF = 0.60
SPEED_ADVISORY_SIGN_CONF = 0.60
BIKE_LANE_CONF = 0.60


# =========================
# Video and file settings
# =========================

VIDEO_SIZE = (1280, 720)
SKIP_FRAMES = 2
YOLO_IMGSZ = 640

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".insv"}


# =========================
# Labels
# =========================

SPEED_LIMIT_LABELS = {
    "speed_limit_sign",
}

SPEED_ADVISORY_LABELS = {
    "speed_advisory_sign",
    "curve_left",
    "curve_right",
    "speed_bump",
    "winding_road",
}

BIKE_LANE_LABELS = {
    "bike_lane",
}

SIGN_LABELS = SPEED_LIMIT_LABELS | SPEED_ADVISORY_LABELS | BIKE_LANE_LABELS

SPEED_NUMBER_LABELS = SPEED_LIMIT_LABELS | SPEED_ADVISORY_LABELS

VALID_SPEEDS = {
    10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 100, 110,
}

SPEED_LABEL_TEXT = {
    "speed_limit_sign": "Speed limit",
    "speed_advisory_sign": "Advisory",
    "curve_left": "Curve left",
    "curve_right": "Curve right",
    "speed_bump": "Speed bump",
    "winding_road": "Winding road",
}

# for each id keep track of the speed votes, so later choose the most voted speed
speed_votes = {} # {(class, id), (speed_i: count_i, speed_j: count_j, ...)}
tesseract_missing_warned = False


# =========================
# Colors
# =========================
# OpenCV uses BGR color order.

COLOR_MAP = {
    "speed_limit_sign": (0, 255, 0), # green
    "speed_advisory_sign": (255, 0, 0), # blue
    "curve_left": (255, 0, 0), # blue
    "curve_right": (255, 128, 0), # light blue
    "speed_bump": (180, 0, 180), # purple
    "winding_road": (0, 140, 255), # orange
    "bike_lane": (0, 0, 255),  # red
}


# =========================
# Model configuration
# =========================

MODEL_CONFIGS = [
    {
        "name": "speed_limit_sign",
        "path": SPEED_LIMIT_MODEL,
        "conf": SPEED_LIMIT_SIGN_CONF,
        "force_label": "speed_limit_sign",
        "allowed_labels": None,
        "class_conf": None,
        "alpha": 0.45,
    },
    {
        "name": "speed_advisory_sign",
        "path": SPEED_ADVISORY_MODEL,
        "conf": SPEED_ADVISORY_SIGN_CONF,
        "force_label": None,
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
        "speed_value",
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

    return {normalize_label_name(label): conf for label, conf in conf_dict.items()}


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
    lines = text if isinstance(text, (list, tuple)) else [text]
    font = cv2.FONT_HERSHEY_SIMPLEX
    line_height = max(
        cv2.getTextSize(line, font, font_scale, 2)[0][1] for line in lines
    ) + 8
    y = max(line_height * len(lines), y)

    for index, line in enumerate(lines):
        baseline = y - (len(lines) - 1 - index) * line_height
        cv2.putText(frame, line, (x, baseline), font, font_scale, (0, 0, 0), 4)
        cv2.putText(frame, line, (x, baseline), font, font_scale, color, 2)


def display_label_for(result, class_id, force_display_label):
    original_label = get_label_name(result, class_id)
    if force_display_label is not None:
        display_label = normalize_label_name(force_display_label)
    else:
        display_label = original_label
    return original_label, display_label


def keep_sign(original_label, display_label, conf, allowed_labels, class_conf):
    if display_label not in SIGN_LABELS:
        return False
    if allowed_labels is not None and original_label not in allowed_labels:
        return False
    if not should_keep_detection(original_label, conf, class_conf):
        return False
    return True


def reset_speed_readings():
    """Drop OCR votes so track ids from the previous file are not reused."""
    speed_votes.clear()


def parse_speed_digits(text):
    """
    Pull a plausible speed out of OCR text.

    Prefer a 3-digit value (100, 110), then a 2-digit value, scanning
    left to right so a leading speed wins over extra digits.
    """
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) < 2:
        return None

    for length in (3, 2):
        for start in range(0, len(digits) - length + 1):
            value = int(digits[start:start + length])
            if value in VALID_SPEEDS:
                return str(value)
    return None


def ocr_image(image, psm="7"):
    global tesseract_missing_warned

    tesseract = shutil.which("tesseract")
    if not tesseract:
        if not tesseract_missing_warned:
            print("Tesseract OCR is not installed, so speed numbers cannot be read.")
            tesseract_missing_warned = True
        return ""

    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        return ""

    try:
        result = subprocess.run(
            [
                tesseract,
                "stdin",
                "stdout",
                "--psm",
                str(psm),
                "-c",
                "tessedit_char_whitelist=0123456789",
            ],
            input=encoded.tobytes(),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        print(f"Speed OCR failed: {exc}")
        return ""

    return result.stdout.decode("utf-8", errors="ignore")


def speed_crop_variants(frame, x1, y1, x2, y2):
    """
    Takes the cropped picture of the speed number sign, and makes a 4 variants of it:
    - Tight crop: 1. black and white, 2. colour
    - Loose crop: 3. black and white, 4.colour
    sends each variant to ocr_image(), if ocr_image() returns a valid speed, adds it to the speed_votes dictionary
    """
    height, width = frame.shape[:2]
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    variants = []

    for inset in (0.18, 0.05):
        left = max(0, int(x1 + box_w * inset))
        top = max(0, int(y1 + box_h * inset))
        right = min(width, int(x2 - box_w * inset))
        bottom = min(height, int(y2 - box_h * inset))
        if right - left < 8 or bottom - top < 8:
            continue

        crop = frame[top:bottom, left:right]
        scale = max(3.0, 160.0 / max(crop.shape[0], 1))
        enlarged = cv2.resize(
            crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if float(np.mean(binary)) < 127:
            binary = cv2.bitwise_not(binary)
        variants.append(binary)
        variants.append(enlarged)

    return variants


def read_speed_once(frame, x1, y1, x2, y2):
    for image in speed_crop_variants(frame, x1, y1, x2, y2):
        speed = parse_speed_digits(ocr_image(image))
        if speed:
            return speed
    return None


def yellow_bands(mask, thresh=0.2, min_height=10):
    """
    Used to find the yellow plate with the speed number sign, so it can sends to ocr_image()
    """
    row = (mask > 0).mean(axis=1)
    bands = []
    start = None
    for index, on in enumerate(row > thresh):
        if on and start is None:
            start = index
        elif not on and start is not None:
            if index - start >= min_height:
                bands.append((start, index))
            start = None
    if start is not None and len(row) - start >= min_height:
        bands.append((start, len(row)))
    return bands, row


def plate_digit_image(crop):
    """
    takes the number sign plate, crop so only top 70% of the plate is left (bottom has no numbers)
    enlarge the crop at least 4x of the original size, so its at least 140 pixels tall
    add a border of 28 pixels all around
    return the enlarged image
    """
    if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
        return None
    digits = crop[: max(8, int(crop.shape[0] * 0.70)), :]
    scale = max(4.0, 140.0 / max(digits.shape[0], 1))
    enlarged = cv2.resize(
        digits, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
    )
    return cv2.copyMakeBorder(enlarged, 28, 28, 28, 28, cv2.BORDER_REPLICATE)


def ocr_plate(image):
    for psm in ("8", "13"):
        speed = parse_speed_digits(ocr_image(image, psm))
        if speed:
            return speed
    return None


def read_advisory_speed(frame, x1, y1, x2, y2):
    """
    Takes the frame with the feature box around the sign, and the box coordinates
    Finds the yellow plate under the sign by extending the bottom of the feature box by 105% of the box height
    Crops the frame to the feature box
    Sends the frame to yellow_bands(), to find the yellow pixels in the frame
    The areas with lowest pixel are cut out as most likely the numbers
    Sends the plate to plate_digit_image()
    Sends the plate to ocr_image()
    Returns the speed number if found, otherwise None
    """
    height, width = frame.shape[:2]
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    left = max(0, int(x1 - box_w * 0.35))
    right = min(width, int(x2 + box_w * 0.35))
    top = min(height - 1, int(y2 - box_h * 0.12))
    bottom = min(height, int(y2 + box_h * 1.05))
    region = frame[top:bottom, left:right]
    if region.size == 0:
        return None

    mask = cv2.inRange(
        cv2.cvtColor(region, cv2.COLOR_BGR2HSV),
        (15, 80, 80),
        (40, 255, 255),
    )
    bands, row = yellow_bands(mask)
    if len(bands) == 1 and (bands[0][1] - bands[0][0]) > region.shape[0] * 0.55:
        start, end = bands[0]
        mid_start = start + int((end - start) * 0.15)
        mid_end = start + int((end - start) * 0.55)
        if mid_end > mid_start:
            cut = mid_start + int(np.argmin(row[mid_start:mid_end]))
            lower_bands, _ = yellow_bands(mask[cut:])
            if lower_bands:
                bands = [(cut + a, cut + b) for a, b in lower_bands]

    candidates = []
    region_h, region_w = region.shape[:2]
    if bands:
        band_top, band_bottom = bands[-1]
        columns = np.where(mask[band_top:band_bottom].any(axis=0))[0]
        if len(columns):
            col_left = max(0, int(columns[0]) - 3)
            col_right = min(region_w, int(columns[-1]) + 4)
            candidates.append(region[band_top:band_bottom, col_left:col_right])

    under_top = min(height - 1, int(y2 + box_h * 0.02))
    under_bottom = min(height, int(y2 + box_h * 0.85))
    if under_bottom - under_top >= 8:
        candidates.append(frame[under_top:under_bottom, max(0, x1):min(width, x2)])

    for crop in candidates:
        image = plate_digit_image(crop)
        if image is None:
            continue
        speed = ocr_plate(image)
        if speed:
            return speed
    return None


def speed_vote_key(display_label, track_id):
    if track_id is None:
        return None
    return (display_label, int(track_id))


def best_speed_vote(key):
    votes = speed_votes.get(key)
    if not votes:
        return None
    speed, _count = votes.most_common(1)[0]
    return speed


def speed_vote_locked(key):
    """
    Returns True once the most common speed has been read at least twice and makes up at least 60% of the reads, 
    so the sign no longer needs to be read (not sent to ocr_image()).
    """
    votes = speed_votes.get(key)
    if not votes:
        return False
    _speed, count = votes.most_common(1)[0]
    total = sum(votes.values())
    return count >= 2 and count >= total * 0.6


def read_speed_number(frame, x1, y1, x2, y2, display_label, track_id=None):
    """
    takes the frame, the box coordinates, the display label, and the track id
    checks if the display label is a speed number label
    checks if the box coordinates are valid
    checks if the speed vote is locked
    reads the speed number from the frame
    returns the speed number if found, otherwise None
    """
    if display_label not in SPEED_NUMBER_LABELS:
        return None

    x1 = max(0, int(x1))
    y1 = max(0, int(y1))
    x2 = min(frame.shape[1], int(x2))
    y2 = min(frame.shape[0], int(y2))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None

    key = speed_vote_key(display_label, track_id)
    if key is not None and speed_vote_locked(key):
        return best_speed_vote(key)

    speed = None
    if display_label in SPEED_ADVISORY_LABELS:
        speed = read_advisory_speed(frame, x1, y1, x2, y2)
    if not speed:
        speed = read_speed_once(frame, x1, y1, x2, y2)
    if key is None:
        return speed

    if speed:
        speed_votes.setdefault(key, Counter())[speed] += 1
        pretty = SPEED_LABEL_TEXT.get(display_label, display_label)
        print(f"Read {pretty.lower()}: {speed}")
    return best_speed_vote(key)


def speed_for_track(display_label, track_id):
    return best_speed_vote(speed_vote_key(display_label, track_id))


def overlay_text(display_label, conf, speed):
    """
    Signs with a speed number use two lines:
        60 speed limit sign
        confidence score: 0.82
    Other detections stay on one line.
    """
    if display_label in SPEED_ADVISORY_LABELS:
        sign_name = SPEED_LABEL_TEXT.get(display_label, display_label.replace("_", " "))
        title = f"{speed} km/h {sign_name}" if speed else sign_name
        return [title, f"confidence score: {conf:.2f}"]
    if display_label in SPEED_NUMBER_LABELS:
        sign_name = display_label.replace("_", " ")
        title = f"{speed} {sign_name}" if speed else sign_name
        return [title, f"confidence score: {conf:.2f}"]
    return f"{display_label} {conf:.2f}"


def track_ids_for(boxes):
    if boxes is None or getattr(boxes, "id", None) is None:
        return None
    return boxes.id.cpu().numpy().astype(int)


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
    ocr_frame=None,
    require_track_id=False,
):
    output = frame.copy()
    overlay = frame.copy()
    counts = {}
    # Read digits from the clean frame, not from boxes already drawn on it.
    source = frame if ocr_frame is None else ocr_frame

    h, w = frame.shape[:2]

    boxes = result.boxes
    masks = result.masks

    if boxes is None:
        return output, counts

    allowed_labels = normalize_label_set(allowed_labels)
    class_conf = normalize_conf_dict(class_conf)

    class_ids = boxes.cls.cpu().numpy().astype(int)
    confs = boxes.conf.cpu().numpy()
    track_ids = track_ids_for(boxes)

    # =========================
    # Draw segmentation masks
    # =========================

    if masks is not None:
        mask_data = masks.data.cpu().numpy()

        for i, mask_raw in enumerate(mask_data):
            conf = float(confs[i])
            original_label, display_label = display_label_for(
                result, class_ids[i], force_display_label
            )

            if not keep_sign(
                original_label, display_label, conf, allowed_labels, class_conf
            ):
                continue

            if require_track_id and (track_ids is None or i >= len(track_ids)):
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
                cv2.drawContours(overlay, contours, -1, color, 3)

            x1, y1, x2, y2 = map(int, boxes.xyxy[i].tolist())
            track_id = None if track_ids is None else int(track_ids[i])
            speed = read_speed_number(
                source, x1, y1, x2, y2, display_label, track_id
            )

            put_label(
                overlay,
                overlay_text(display_label, conf, speed),
                x1,
                y1 - 6,
                color,
                font_scale,
            )

    # =========================
    # Draw boxes only
    # =========================

    else:
        for i, b in enumerate(boxes):
            class_id = int(b.cls[0])
            conf = float(b.conf[0])
            original_label, display_label = display_label_for(
                result, class_id, force_display_label
            )

            if not keep_sign(
                original_label, display_label, conf, allowed_labels, class_conf
            ):
                continue

            if require_track_id and (track_ids is None or i >= len(track_ids)):
                continue

            counts[display_label] = counts.get(display_label, 0) + 1

            color = get_color(display_label)
            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
            track_id = None if track_ids is None else int(track_ids[i])
            speed = read_speed_number(
                source, x1, y1, x2, y2, display_label, track_id
            )

            if draw_boxes:
                cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

            put_label(
                overlay,
                overlay_text(display_label, conf, speed),
                x1,
                y1 - 6,
                color,
                font_scale,
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
        model_path = resolve_model_path(f"{model_name}.pt")

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
        effective_config["font_scale"] = float(model_setting.get("font_scale", 0.55))

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

        loaded_models.append(
            {
                "config": effective_config,
                "model": model,
            }
        )

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
            imgsz=YOLO_IMGSZ,
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
            ocr_frame=frame,
        )

        total_counts = merge_counts(total_counts, counts)

    return result_frame, total_counts


def process_image(file_path, loaded_models):
    """
    Process one image file.
    """
    reset_speed_readings()
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

    return min(gps_points, key=lambda p: abs((p["time"] - target_time).total_seconds()))


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

        convert_mov_to_mp4(str(file_path), str(clean_path))

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

        convert_mov_to_mp4(str(file_path), str(clean_path))

        print(f"MOV converted for processing: {clean_path}")
        return clean_path

    except Exception as e:
        print(f"MOV conversion failed. Trying original MOV. Reason: {e}")
        return file_path


def get_video_output_path(output_stem):
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR / f"detected_{output_stem}.mp4"


def box_iou(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    overlap_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    overlap_h = max(0, min(ay2, by2) - max(ay1, by1))
    overlap = overlap_w * overlap_h
    if overlap <= 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return overlap / (area_a + area_b - overlap)


def same_sign_box(box, other):
    """When two boxes are the same sign and overlap by at least 5%, its the same sign"""
    if box["label"] != other["label"]:
        return False
    return box_iou(box["xyxy"], other["xyxy"]) >= 0.05


def sign_records_from_result(result, config, source_frame):
    boxes = result.boxes
    if boxes is None:
        return []

    track_ids = track_ids_for(boxes)
    class_ids = boxes.cls.cpu().numpy().astype(int)
    confs = boxes.conf.cpu().numpy()
    allowed = normalize_label_set(config["allowed_labels"])
    class_conf = normalize_conf_dict(config["class_conf"])
    records = []

    for index, class_id in enumerate(class_ids):
        conf = float(confs[index])
        original_label, display_label = display_label_for(
            result, class_id, config["force_label"]
        )
        if not keep_sign(
            original_label, display_label, conf, allowed, class_conf
        ):
            continue

        track_id = None if track_ids is None else int(track_ids[index])
        x1, y1, x2, y2 = map(int, boxes.xyxy[index].tolist())
        read_speed_number(
            source_frame, x1, y1, x2, y2, display_label, track_id
        )
        records.append(
            {
                "label": display_label,
                "track_id": track_id,
                "xyxy": (x1, y1, x2, y2),
                "conf": conf,
                "font_scale": config.get("font_scale", 0.55),
            }
        )
    return records


def frames_to_draw(samples, fps):
    drawable = {}
    first_box = {}
    kept_keys = set()

    for frame_index in sorted(samples):
        for box in samples[frame_index]:
            if box["track_id"] is None:
                continue
            key = (box["label"], box["track_id"])
            kept_keys.add(key)
            drawable.setdefault(frame_index, []).append(box)
            if key not in first_box:
                first_box[key] = (frame_index, box)

    lookback = max(1, int(fps * 8))
    for key, (start, anchor) in first_box.items():
        label = key[0]
        previous_frames = [
            frame_index
            for frame_index in sorted(samples)
            if start - lookback <= frame_index < start
        ]
        current = anchor
        for frame_index in reversed(previous_frames):
            match = None
            for box in samples[frame_index]:
                if box["label"] != label:
                    continue
                if box["track_id"] not in (None, key[1]):
                    continue
                if same_sign_box(box, current):
                    match = box
                    break
            if match is None:
                break
            linked = dict(match)
            linked["track_id"] = key[1]
            already = drawable.get(frame_index, [])
            if not any(item["xyxy"] == linked["xyxy"] for item in already):
                drawable.setdefault(frame_index, []).append(linked)
            current = match

    return drawable, kept_keys


def final_confidence_by_track(samples):
    """Last confidence for each tracked sign. Later frames replace earlier ones."""
    final_conf = {}
    for frame_index in sorted(samples):
        for box in samples[frame_index]:
            if box["track_id"] is None:
                continue
            final_conf[(box["label"], box["track_id"])] = box["conf"]
    return final_conf


def apply_final_track_labels(drawable, final_conf):
    """
    Paint every frame of a kept track with that track's final speed reading
    and final confidence, so the video does not show scores that are still changing.
    """
    for boxes in drawable.values():
        for box in boxes:
            key = (box["label"], box["track_id"])
            if key in final_conf:
                box["conf"] = final_conf[key]
            voted = speed_for_track(box["label"], box["track_id"])
            if voted:
                box["speed"] = voted


def draw_sign_records(frame, records):
    """Draw the kept sign boxes for one frame."""
    output = frame.copy()
    for box in records:
        speed = box.get("speed") or speed_for_track(box["label"], box["track_id"])
        x1, y1, x2, y2 = box["xyxy"]
        color = get_color(box["label"])
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        put_label(
            output,
            overlay_text(box["label"], box["conf"], speed),
            x1,
            y1 - 6,
            color,
            box["font_scale"],
        )
    return output


def process_video(
    file_path, loaded_models, gps_points=None, source_file_path=None, output_stem=None
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

    reset_speed_readings()

    # label -> set of unique integer track IDs seen so far
    seen_ids = {}

    # Stores the LATEST frame data for each unique detected object.
    # Overwritten on every frame so the final entry holds the last
    # position and GPS reading for that object.
    last_seen_data = {}
    samples = {}

    frame_count = 0

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        frame = cv2.resize(frame, VIDEO_SIZE)

        if frame_count % SKIP_FRAMES == 0:
            gps_point, frame_time_sec = get_gps_for_frame(
                frame_index=frame_count, fps=fps, gps_points=gps_points
            )

            if frame_time_sec is None:
                frame_time_sec = frame_count / fps

            frame_records = []
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
                    imgsz=YOLO_IMGSZ,
                    save=False,
                    verbose=False,
                )

                if not track_results:
                    continue

                result = track_results[0]
                records = sign_records_from_result(result, config, frame)
                frame_records.extend(records)

                for box in records:
                    if box["track_id"] is None:
                        continue

                    display_label = box["label"]
                    track_id = box["track_id"]
                    if display_label not in seen_ids:
                        seen_ids[display_label] = set()
                    seen_ids[display_label].add(track_id)

                    x1, y1, x2, y2 = box["xyxy"]
                    # Always overwrite with the current frame's data.
                    # On first detection this creates the entry.
                    # On every subsequent detection this updates it with
                    # fresher GPS so the final entry holds the last frame.
                    last_seen_data[(display_label, track_id)] = {
                        "snapshot": frame.copy(),
                        "row": {
                            "source_file": source_file_path.name,
                            "processed_file": file_path.name,
                            "object_id": f"{display_label}_{track_id}",
                            "class_name": display_label,
                            "last_frame_time_sec": round(frame_time_sec, 3),
                            "camera_latitude": (
                                gps_point["latitude"] if gps_point else ""
                            ),
                            "camera_longitude": (
                                gps_point["longitude"] if gps_point else ""
                            ),
                            "camera_elevation": (
                                gps_point["elevation"] if gps_point else ""
                            ),
                            "camera_speed": gps_point["speed"] if gps_point else "",
                            "camera_angle": gps_point["track"] if gps_point else "",
                            "confidence": round(box["conf"], 4),
                            "side_of_frame": frame_side(x1, x2, VIDEO_SIZE[0]),
                            "speed_value": speed_for_track(display_label, track_id) or "",
                        },
                    }

            samples[frame_count] = frame_records

        frame_count += 1

        if frame_count % 30 == 0:
            print(f"Frames processed: {frame_count}")

    total_frames = frame_count
    drawable, kept_keys = frames_to_draw(samples, fps)
    final_conf = final_confidence_by_track(samples)
    apply_final_track_labels(drawable, final_conf)
    for key, conf in final_conf.items():
        if key in last_seen_data:
            last_seen_data[key]["row"]["confidence"] = round(conf, 4)
    cap.release()

    cap = cv2.VideoCapture(str(file_path))
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        VIDEO_SIZE,
    )
    if not cap.isOpened() or not writer.isOpened():
        cap.release()
        writer.release()
        print(f"Cannot create output video: {output_path}")
        return False

    frame_count = 0
    last_result_frame = None

    while frame_count < total_frames:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.resize(frame, VIDEO_SIZE)
        if frame_count % SKIP_FRAMES == 0 or last_result_frame is None:
            last_result_frame = draw_sign_records(
                frame, drawable.get(frame_count, [])
            )

        writer.write(last_result_frame)
        frame_count += 1

    cap.release()
    writer.release()

    snapshot_dir = REPORT_DIR / output_stem / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for old_photo in snapshot_dir.glob("*.jpg"):
        old_photo.unlink()

    detail_rows = []
    for label, tid in sorted(kept_keys, key=lambda key: (key[0], key[1])):
        data = last_seen_data.get((label, tid))
        if data is None:
            continue
        snap_path = snapshot_dir / f"{label}_id{tid}_last.jpg"
        cv2.imwrite(str(snap_path), data["snapshot"])
        detail_rows.append(data["row"])

    total_counts = {label: len(ids) for label, ids in seen_ids.items()}

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
            output_stem=output_stem,
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
        f
        for f in INPUT_DIR.iterdir()
        if f.is_file()
        and (f.suffix.lower() in IMAGE_EXTS or f.suffix.lower() in VIDEO_EXTS)
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
                output_stem=file_path.stem,
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

        run_detection(input_path=input_path, gpx_path=gpx_path, move_original=False)

    else:
        process_all_uploads()


if __name__ == "__main__":
    main()

# References: this script has been written with the help of AI (chatgpt, Claude, Grok)