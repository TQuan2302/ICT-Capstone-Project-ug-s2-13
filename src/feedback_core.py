"""
Controls the feedback logic for the webapp, allowing users to screenshot
missing objects in the detection videos.

User is able to pause video, draw a box around missing objects, then
select the objects class and then save. The image will be saved and a 
YOLO .txt label file will contain the location of the drawn box.

<data folder>/retrain/<model>/feedback/images/<name>.jpg
<data folder>/retrain/<model>/feedback/labels/<name>.txt

"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from roadsight_paths import DATA_DIR
from train import MODEL_META, get_paths

# Location of uploads and results
UPLOAD_FOLDER = Path(DATA_DIR) / "uploads"
RESULT_FOLDER = Path(DATA_DIR) / "results"

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".insv")
RESULT_PREFIX = "detected_"

# Lookup table for models and classes from MODEL_META
FEEDBACK_MODELS = {meta["name"]: meta for meta in MODEL_META}
FEEDBACK_CLASS_NAMES = [
    class_name for meta in MODEL_META for class_name in meta["class_names"]
]
# Find which model a class belongs to
FEEDBACK_CLASS_TO_MODEL = {
    class_name: meta["name"]
    for meta in MODEL_META
    for class_name in meta["class_names"]
}

JPEG_QUALITY = 95

# Checks that the file being passed is just a file and not a path
def safe_stem(stem: str) -> str:
    stem = str(stem or "")
    if not stem or Path(stem).name != stem or stem in {".", ".."} or stem.startswith("."):
        raise ValueError("Invalid file name.")
    return stem


def find_clean_source(stem: str):
    """
    Find the file to take a clean frame from, for the upload called <stem>.
    Returns (path, is_clean) or (None, False).

    YOLO requires a clean image to retrain the model.
    Having boxes drawn on the training image will negatively impact the training.
    To find a clean file it first checks converted folder, uploads folder, and finally
    the results folder as a last resort.

    Order:
      1. uploads/converted/<stem>_clean.mp4 
      2. uploads/<stem>.<image or video extension>
      3. results/detected_<stem>.<ext>        
    """
    stem = safe_stem(stem)

    converted = UPLOAD_FOLDER / "converted" / f"{stem}_clean.mp4"
    if converted.is_file():
        return converted, True

    allowed = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS
    if UPLOAD_FOLDER.is_dir():
        for path in sorted(UPLOAD_FOLDER.iterdir()):
            if path.is_file() and path.stem == stem and path.suffix.lower() in allowed:
                return path, True

    if RESULT_FOLDER.is_dir():
        for ext in (".mp4", ".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            candidate = RESULT_FOLDER / f"{RESULT_PREFIX}{stem}{ext}"
            if candidate.is_file():
                return candidate, False

    return None, False

# Reads an image files bytes, decodes into BGR array that can be read by OpenCV
def read_image(path: Path):
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except OSError:
        return None

# Opens a video, jumps to the current video position and grabs a BGR array of that frame
def read_video_frame(path: Path, position_ms: int):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(int(position_ms or 0), 0))
        ok, frame = cap.read()
    finally:
        cap.release()
    return frame if ok else None

# Finds the file with said name and reads one frame from it if a video
# or just returns the image. Will grab a boxed image if it can't read
# a clean file.
def load_frame(stem: str, position_ms: int | None = None):
    path, is_clean = find_clean_source(stem)
    if path is None:
        return None, False

    def read(p: Path):
        if p.suffix.lower() in IMAGE_EXTENSIONS:
            return read_image(p)
        return read_video_frame(p, position_ms or 0)

    frame = read(path)
    if frame is not None:
        return frame, is_clean

    if is_clean:
        # The upload could not be read it will fall back to the boxed result
        for ext in (".mp4", ".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            fallback = RESULT_FOLDER / f"{RESULT_PREFIX}{safe_stem(stem)}{ext}"
            if fallback.is_file():
                frame = read(fallback)
                if frame is not None:
                    return frame, False

    return None, False

# Turns the frame back in a JPEG
def encode_jpeg(frame_bgr) -> bytes:
    ok, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise OSError("Could not encode the frame as a JPEG.")
    return buffer.tobytes()

# Takes the location of the box drawn (top corner and bottom corner),
# saves it in a way YOLO can read it. It stores the drawn box as where
# its centre is located as a fraction of the image width/height and then
# how wide/tall it is.
def box_to_yolo(x_min, y_min, x_max, y_max, img_w, img_h):
    x_center = ((x_min + x_max) / 2) / img_w
    y_center = ((y_min + y_max) / 2) / img_h
    width = (x_max - x_min) / img_w
    height = (y_max - y_min) / img_h
    return x_center, y_center, width, height

# Takes the clean frame, list of labelled boxes, source name, and the video position
def save_feedback_sample(frame_bgr, labelled_boxes, source_name, position_ms=None):
    # Creating file name
    img_h, img_w = frame_bgr.shape[:2]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{safe_stem(source_name)}"
    if position_ms is None:
        file_stem = f"{stem}_{timestamp}"
    else:
        total_seconds = max(int(position_ms), 0) // 1000
        frame_time = f"{total_seconds // 60:02d}m{total_seconds % 60:02d}s"
        file_stem = f"{stem}_{frame_time}_{timestamp}"

    # Turns each drawn box into a label line for specific model
    lines_by_model: dict[str, list[str]] = {}
    for x_min, y_min, x_max, y_max, class_name in labelled_boxes:
        if class_name not in FEEDBACK_CLASS_TO_MODEL:
            raise ValueError(f"Unknown class: {class_name}")

        x_min = min(max(round(x_min), 0), img_w)
        x_max = min(max(round(x_max), 0), img_w)
        y_min = min(max(round(y_min), 0), img_h)
        y_max = min(max(round(y_max), 0), img_h)
        if x_max <= x_min or y_max <= y_min:
            continue

        model_name = FEEDBACK_CLASS_TO_MODEL[class_name]
        class_id = FEEDBACK_MODELS[model_name]["class_names"].index(class_name)
        xc, yc, w, h = box_to_yolo(x_min, y_min, x_max, y_max, img_w, img_h)
        lines_by_model.setdefault(model_name, []).append(
            f"{class_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}"
        )

    if not lines_by_model:
        raise ValueError("No valid boxes to save.")

    jpeg_bytes = encode_jpeg(frame_bgr)
    # Writes the files to predefined feedback files
    saved = []
    try:
        for model_name, lines in lines_by_model.items():
            paths = get_paths(model_name)
            paths["feedback_images"].mkdir(parents=True, exist_ok=True)
            paths["feedback_labels"].mkdir(parents=True, exist_ok=True)

            image_path = paths["feedback_images"] / f"{file_stem}.jpg"
            label_path = paths["feedback_labels"] / f"{file_stem}.txt"

            saved.append((model_name, str(image_path), str(label_path)))

            with open(image_path, "wb") as f:
                f.write(jpeg_bytes)

            with open(label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
    except OSError:
        for _, image_path, label_path in saved:
            for path in (image_path, label_path):
                if os.path.exists(path):
                    os.remove(path)
        raise

    return saved


# References: this script has been written with the help of AI (chatgpt, Claude, Grok)