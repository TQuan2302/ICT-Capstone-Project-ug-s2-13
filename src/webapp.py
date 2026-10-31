import sys
import os
import re
import shutil
import subprocess
import queue
import threading
import time
import asyncio
from typing import List, Optional
import pandas as pd
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, status, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from json import loads

import combined_map
import geo_mapping

from detection_settings import show_detection_settings
from roadsight_paths import (
    seed_runtime_data,
    install_shutdown_sync,
    sync_runtime_data_back,
)

# =========================
# Basic paths
# =========================

# When frozen by PyInstaller, sys._MEIPASS is the read-only bundle directory.
# All read-only assets (images, models) live there.
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = str(seed_runtime_data())
install_shutdown_sync()

VIDEO_QUEUE_DIR = os.path.join(DATA_DIR, "queue")
VIDEO_ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
DETECTION_RESULT_DIR = os.path.join(DATA_DIR, "results")

os.makedirs(VIDEO_QUEUE_DIR, exist_ok=True)
os.makedirs(VIDEO_ARCHIVE_DIR, exist_ok=True)
os.makedirs(DETECTION_RESULT_DIR, exist_ok=True)

UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
RESULT_FOLDER = os.path.join(DATA_DIR, "results")
REPORT_FOLDER = os.path.join(DATA_DIR, "reports")
INPUT_FOLDER = os.path.join(DATA_DIR, "testing resource")

os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

""" Functions to handle directory polling and processing queue management """
""" Callback function when files are created in the queue directory """
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".insv")
TEXT_EXTENSIONS = (".txt", ".csv", ".json", ".log")
RESULT_EXTENSIONS = (".mp4", ".png", ".jpg", ".jpeg", ".webp")
MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}
UPLOAD_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS

class QueueListener(PatternMatchingEventHandler):
    def __init__(self, extensions):
        patterns = [f"*{ext}" for ext in extensions]

        super().__init__(
            patterns=patterns, ignore_directories=True, case_sensitive=False
        )

    def on_created(self, event):
        if not event.is_directory:
            print(f"file created: {event.src_path}")
            print(f"adding file to queue")


""" Listener function to poll a directory and execute a callback when operations are detected """


def start_file_listener(watched_directory, watched_extensions):
    event_handler = QueueListener(watched_extensions)
    observer = Observer()

    observer.schedule(
        event_handler=event_handler, path=watched_directory, recursive=False
    )

    print(f"Watching directory for new files: {watched_directory}")

    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping Directory Listener")
        observer.stop()

    observer.join()


# =========================
# The web-interface
# =========================

app = FastAPI()

def get_filename(filename: str) -> str:
    name = Path(str(filename or "")).name
    return name


def save_upload_to_folder(uploaded_file: UploadFile, folder: str) -> str:
    filename = get_filename(uploaded_file.filename)
    upload_save_folder_path = Path(folder) / filename
    try:
        with upload_save_folder_path.open("wb") as buffer:
            shutil.copyfileobj(uploaded_file.file, buffer)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file to uploads folder: {exc}",
        ) from exc
    return filename

def get_ffmpeg_path() -> str:
    """
    Prefer the ffmpeg binary bundled with imageio_ffmpeg so the webapp works
    without a system ffmpeg install (important when running frozen).
    """
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def get_video_codec_name(path: Path) -> str:
    ffmpeg_result = subprocess.run(
        [get_ffmpeg_path(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Video:\s+(\w+)", ffmpeg_result.stderr)
    return match.group(1).lower() if match else ""


convert_browser_format_lock = threading.Lock()


def ensure_browser_mp4(path: Path) -> Path:
    """
    OpenCV saves the detected video as MPEG-4, which the browser cannot play. 
    This function converts the video to H.264 instead.
    The OpenCV video is replaced with the converted video.
    """
    if get_video_codec_name(path) == "h264":
        return path

    with convert_browser_format_lock:
        converted_path = path.with_name(f"{path.stem}.browser.mp4")
        subprocess.run(
            [
                get_ffmpeg_path(),
                "-y",
                "-i",
                str(path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(converted_path),
            ],
            check=True,
        )
        converted_path.replace(path)
    return path


def get_detected_video_path(file_name: str) -> Path:
    """Takes the upload filename, and finds the corresponding detected video file path."""
    stem = Path(get_filename(file_name)).stem
    result_folder_path = Path(RESULT_FOLDER)
    for ext in RESULT_EXTENSIONS:
        candidate = result_folder_path / f"detected_{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def get_report_folder(file_name: str) -> Path:
    """Takes the upload filename, and finds the corresponding report folder path that containscsv files"""
    return Path(REPORT_FOLDER) / Path(get_filename(file_name)).stem


def detection_stem(file_name: str) -> str:
    stem = Path(get_filename(file_name)).stem
    if not stem or stem in {".", ".."} or stem.startswith("."):
        raise HTTPException(status_code=404, detail="Detection not found")
    return stem


def delete_detection_files(stem: str) -> bool:
    """Remove one detection's result file and its map report."""
    removed = False
    result = get_detected_video_path(stem)
    if result is not None and result.is_file():
        result.unlink()
        removed = True

    browser_copy = Path(RESULT_FOLDER) / f"detected_{stem}.browser.mp4"
    if browser_copy.is_file():
        browser_copy.unlink()

    reports_root = Path(REPORT_FOLDER).resolve()
    report_dir = (reports_root / stem).resolve()
    if reports_root in report_dir.parents and report_dir.is_dir():
        shutil.rmtree(report_dir)
        removed = True

    cache_file = Path(REPORT_FOLDER) / ".map_cache" / f"{stem}.json"
    if cache_file.is_file():
        cache_file.unlink()

    if removed:
        combined = Path(REPORT_FOLDER) / "all_detections_map.html"
        if combined.is_file():
            combined.unlink()
    return removed


def read_csv_records(path: Path):
    """
    Reads the csv file:
    first list: each row as a dictionary
    second list: the column names as a list
    A missing or empty file returns two empty lists.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return [], []

    data = pd.read_csv(path)
    rows = loads(data.to_json(orient="records"))
    return rows, [str(column) for column in data.columns]


# ensure only one detection is running at a time
detection_queue_lock = threading.Lock()
detection_status = {}
detection_queue = queue.Queue()

def enqueue_detection(filename: str, gpx_filename: Optional[str] = None):
    gpx_path = os.path.join(UPLOAD_FOLDER, gpx_filename) if gpx_filename else None
    with detection_queue_lock:
        detection_status[filename] = "queued"
    detection_queue.put((filename, gpx_path))


def run_detection_worker():
    run_detection = None

    while True:
        filename, gpx_path = detection_queue.get()
        with detection_queue_lock:
            detection_status[filename] = "processing"
        try:
            if run_detection is None:
                from detect import run_detection as detect_run
                run_detection = detect_run
            run_detection(
                os.path.join(UPLOAD_FOLDER, filename),
                gpx_path=gpx_path,
                move_original=False,
            )
            result = get_detected_video_path(filename)
            if result is not None and result.suffix.lower() == ".mp4":
                ensure_browser_mp4(result)
            with detection_queue_lock:
                detection_status[filename] = "done"
        except Exception as exc:
            print(f"Error: Could not run detection for {filename}: {exc}")
            with detection_queue_lock:
                detection_status[filename] = "failed"
        finally:
            detection_queue.task_done()

# start the detection worker
threading.Thread(target=run_detection_worker, daemon=True).start()

def get_detection_status_for(filename: str) -> str:
    with detection_queue_lock:
        if filename in detection_status:
            return detection_status[filename]
    if get_detected_video_path(filename):
        return "done"
    return "queued"


# =========================
# Routes for interaction between the back and front-ends
# =========================


@app.post("/upload/video")
async def upload_video(
    file: UploadFile = File(...),
    gpx: Optional[UploadFile] = File(None),
):
    filename = save_upload_to_folder(file, UPLOAD_FOLDER)
    gpx_filename = save_upload_to_folder(gpx, UPLOAD_FOLDER) if gpx else None
    enqueue_detection(filename, gpx_filename)
    await file.close()
    if gpx:
        await gpx.close()
    return {
        "info": "Success: saved video file",
        "filename": filename,
        "status": "queued",
    }


@app.get("/uploads")
async def get_uploads_list():
    uploads_folder = Path(UPLOAD_FOLDER)
    file_info_list = []
    for path in uploads_folder.iterdir():
        if not path.is_file() or path.suffix.lower() not in UPLOAD_EXTENSIONS:
            continue
        file_info_list.append(
            {
                "filename": path.name,
                "stem": path.stem,
                "date": datetime.fromtimestamp(path.stat().st_mtime).strftime(
                    "%d/%m/%Y %H:%M"
                ),
                "size": path.stat().st_size,
                "mtime": path.stat().st_mtime,
                "status": get_detection_status_for(path.name),
            }
        )
    file_info_list.sort(key=lambda item: item["mtime"], reverse=True)
    # remove mtime from the file info list, only needed for sorting, info has readable date and time
    for file_info in file_info_list:
        file_info.pop("mtime", None)
    return file_info_list


# =========================
# Endpoints for listings of detections
# =========================


# returns a JSON list of the folders inside the reports directory
@app.get("/detections-list")
async def get_detections_list():
    report_folder = Path(REPORT_FOLDER)
    dir_info_list = []

    for directory in report_folder.iterdir():
        if not directory.is_dir():
            continue
        dir_info_list.append(
            {
                "name": directory.name,
                "date": datetime.fromtimestamp(directory.stat().st_mtime).strftime(
                    "%d/%m/%Y %H:%M"
                ),
                "mtime": directory.stat().st_mtime,
            }
        )

    dir_info_list.sort(key=lambda item: item["mtime"], reverse=True)
    for item in dir_info_list:
        item.pop("mtime", None)
    return dir_info_list


@app.get("/detections/{file_name}/csv/{which}")
async def download_detection_csv(file_name: str, which: str):
    csv_file_names = {
        "report": "detection_report.csv",
        "details": "detection_details_with_gps.csv",
    }
    if which not in csv_file_names:
        raise HTTPException(status_code=404, detail="CSV not found")

    csv_path = get_report_folder(file_name) / csv_file_names[which]
    if not csv_path.is_file():
        raise HTTPException(status_code=404, detail="CSV not found")

    stem = Path(get_filename(file_name)).stem
    return FileResponse(
        csv_path,
        media_type="text/csv",
        filename=f"{stem}_{csv_file_names[which]}",
    )


def get_upload_with_stem(stem: str):
    upload_folder = Path(UPLOAD_FOLDER)
    if not upload_folder.is_dir():
        return None
    for path in upload_folder.iterdir():  
        if path.is_file() and path.stem == stem and path.suffix.lower() in UPLOAD_EXTENSIONS:
            return path
    return None


@app.delete("/detections/{file_name}")
def delete_detection(file_name: str):
    stem = detection_stem(file_name)
    if not delete_detection_files(stem):
        raise HTTPException(status_code=404, detail="Detection not found")
    return {"deleted": stem}


@app.get("/detections/{file_name}")
async def get_detections(file_name: str):
    stem = Path(get_filename(file_name)).stem
    report_folder = get_report_folder(file_name)
    result = get_detected_video_path(file_name)
    if not report_folder.is_dir() and result is None and get_upload_with_stem(file_name) is None:
        raise HTTPException(status_code=404, detail="Error: Could not find results.")

    report = report_folder / "detection_report.csv"
    details = report_folder / "detection_details_with_gps.csv"
    report_rows, report_columns = read_csv_records(report)
    detail_rows, detail_columns = read_csv_records(details)
    encoded = quote(stem, safe="")

    # url has the type video or image, and the modified so if same file is uploaded again, the browser shows the new file.
    media = None
    if result is not None:
        kind = "video" if result.suffix.lower() == ".mp4" else "image"
        media = {
            "kind": kind,
            "url": f"/preview-stream/{encoded}?v={int(result.stat().st_mtime)}",
        }

    return {
        "name": stem,
        "report": report_rows,
        "details": detail_rows,
        "report_columns": report_columns,
        "detail_columns": detail_columns,
        "media": media,
        "csv": {
            "report": f"/detections/{encoded}/csv/report" if report.is_file() else None,
            "details": f"/detections/{encoded}/csv/details" if details.is_file() else None,
        },
    }


# =========================
# Retrain loop
# =========================


RETRAIN_MODELS = ("bike_lane", "speed_limit_sign", "speed_advisory_sign")
retrain_lock = threading.Lock()
retrain_state = {
    "running": False,
    "model": None,
    "logs": [],
    "error": None,
    "result": None,
}


def check_ready_to_retrain(info: dict):
    """ Check if the model has min feedback and validation images before it can retrain. """
    min_feedback_required = info.get("min_feedback", 10)
    if info["feedback"] < min_feedback_required:
        return False, f"Insufficient feedback: Needs at least {min_feedback_required} labelled feedback images."
    if info["val"] < 1:
        return False, "Insufficient validation: Needs at least 1 labelled validation image."
    return True, None


def known_model(model_name: str) -> str:
    """ Check if the model is a known model. """
    model_name = get_filename(model_name)
    if model_name not in RETRAIN_MODELS:
        raise HTTPException(status_code=404, detail="Error:Unknown model")
    return model_name


def retrain_job(model_name: str, epochs: int):
    """
    Run the retrain job for the given model and epochs.
    """
    from train import retrain_compare

    def progress(message: str):
        with retrain_lock:
            retrain_state["logs"].append(message)

    try:
        result = retrain_compare(model_name, epochs=epochs, progress_callback=progress)
        with retrain_lock:
            retrain_state["result"] = result
            retrain_state["logs"].append(result["headline"])
            retrain_state["error"] = None
    except Exception as exc:
        with retrain_lock:
            retrain_state["error"] = str(exc)
            retrain_state["logs"].append(f"Training failed. {exc}")
    finally:
        with retrain_lock:
            retrain_state["running"] = False


@app.get("/retrain/models")
async def retrain_models():
    """
    Return a list of models that are ready to retrain.
    The list is sorted by the model name: 0: bike_lane, 1: speed_limit_sign, 2: speed_advisory_sign
    """
    from train import all_model_counts

    models = []
    for info in all_model_counts():
        ready, reason = check_ready_to_retrain(info)
        info["ready"] = ready
        info["reason"] = reason
        models.append(info)
    order = {name: index for index, name in enumerate(RETRAIN_MODELS)}
    models.sort(key=lambda item: order.get(item["key"], 99))
    return models


def display_folder(path: Path) -> None:
    """ 
    It creates the folder if needed,
    then opens it in Finder or Explorer depending on the platform.
    Used to open feedback folders.
    """
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        command = ["open", str(path)]
    elif sys.platform == "win32":
        command = ["explorer", str(path)]
    else:
        command = ["xdg-open", str(path)]
    subprocess.Popen(command)


@app.post("/retrain/{model_name}/open-feedback")
async def open_feedback_folder(model_name: str):
    from train import get_paths

    key = known_model(model_name)
    paths = get_paths(key)

    feedback = paths["feedback_images"].parent
    display_folder(feedback)
    return {"opened": str(feedback)}


@app.post("/retrain/keep")
async def keep_retrain():
    with retrain_lock:
        result = retrain_state["result"]
        if result is None:
            raise HTTPException(status_code=400, detail="Error: No training result to keep")
        if retrain_state["running"]:
            raise HTTPException(status_code=409, detail="Error: Training in progress")

    from train import keep_new_weights

    live = keep_new_weights(result["key"], Path(result["new_weights"]))
    with retrain_lock:
        retrain_state["result"] = None
        retrain_state["logs"].append(f"Kept new weights: {live}")
    return {"kept": result["key"], "weights": str(live)}


@app.post("/retrain/discard")
async def discard_retrain():
    with retrain_lock:
        result = retrain_state["result"]
        if result is None:
            raise HTTPException(status_code=400, detail="Error: No training result to keep")
        if retrain_state["running"]:
            raise HTTPException(status_code=409, detail="Error: Training in progress")

    from train import discard_new_weights

    discard_new_weights(result["key"])
    with retrain_lock:
        retrain_state["result"] = None
        retrain_state["logs"].append("Discarded the new weights. The live model is unchanged.")
    return {"discarded": result["key"]}


@app.post("/retrain/{model_name}")
async def start_retrain(model_name: str, epochs: int = 10):
    key = known_model(model_name)
    if epochs < 1 or epochs > 200:
        raise HTTPException(status_code=400, detail="Error: Epochs must be between 1 and 200")

    from train import all_model_counts

    info = next(item for item in all_model_counts() if item["key"] == key)
    ready, reason = check_ready_to_retrain(info)
    if not ready:
        raise HTTPException(status_code=400, detail=reason)

    with retrain_lock:
        if retrain_state["running"]:
            raise HTTPException(status_code=409, detail="Error: A model is already training")
        if retrain_state["result"] is not None:
            raise HTTPException(
                status_code=409,
                detail="Keep or discard the current training result first",
            )
        retrain_state["running"] = True
        retrain_state["model"] = key
        retrain_state["error"] = None
        retrain_state["logs"] = [f"Training starting for {key}."]

    threading.Thread(target=retrain_job, args=(key, epochs), daemon=True).start()
    return {"started": key, "epochs": epochs}


@app.get("/retrain/status")
async def retrain_status():
    with retrain_lock:
        return {
            "running": retrain_state["running"],
            "model": retrain_state["model"],
            "logs": list(retrain_state["logs"]),
            "error": retrain_state["error"],
            "result": retrain_state["result"],
        }


# =========================
# Endpoints for viewing detection videos
# =========================


@app.get("/preview-stream/{file_name}")
async def stream_video(file_name: str):
    result_path = get_detected_video_path(file_name)
    if result_path is None:
        raise HTTPException(status_code=404, detail="Error: Detected file not found")

    if result_path.suffix.lower() == ".mp4":
        try:
            result_path = await asyncio.to_thread(ensure_browser_mp4, result_path)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error: Could not display the detected video: {exc}",
            ) from exc

    # FileResponse handles Range headers (206 Partial Content) automatically
    return FileResponse(
        result_path,
        media_type=MEDIA_TYPES.get(result_path.suffix.lower(), "application/octet-stream"),
        filename=result_path.name,
        content_disposition_type="inline",
    )


# =========================
# Endpoints for detection maps
# =========================


@app.get("/map-list")
def get_map_list():
    target = Path(REPORT_FOLDER)
    if not target.is_dir():
        return []

    dir_info_list = []
    for directory in target.iterdir():
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        if not (directory / "detection_details_with_gps.csv").is_file():
            continue
        dir_info_list.append(
            {
                "name": directory.name,
                "date": datetime.fromtimestamp(directory.stat().st_mtime).strftime(
                    "%d/%m/%Y %H:%M"
                ),
            }
        )
    dir_info_list.sort(key=lambda item: item["name"].lower())
    return dir_info_list


@app.get("/map/all")
def show_all_maps():
    os.makedirs(REPORT_FOLDER, exist_ok=True)
    output_html = os.path.join(REPORT_FOLDER, "all_detections_map.html")
    try:
        map_path = combined_map.build_map_from_reports(REPORT_FOLDER, output_html)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(map_path, media_type="text/html")


@app.get("/map/{file_name}")
def show_one_map(file_name: str):
    reports_root = Path(REPORT_FOLDER).resolve()
    report_dir = (reports_root / file_name).resolve()
    if report_dir != reports_root and reports_root not in report_dir.parents:
        raise HTTPException(status_code=404, detail="Report not found")

    csv_file = report_dir / "detection_details_with_gps.csv"
    if not csv_file.is_file():
        raise HTTPException(status_code=404, detail="Report not found")

    output_html = report_dir / "detection_map.html"
    try:
        map_path = geo_mapping.build_map_from_csv(csv_file, output_html)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(map_path, media_type="text/html")


# =========================
# Static file hosting for the web-based interface
# =========================


app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "dist"), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


# References: this script has been written with the help of AI (chatgpt, Claude, Grok)