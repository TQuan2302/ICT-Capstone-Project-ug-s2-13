import sys
import os
import shutil
import platform
import time
import pandas as pd
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Header, UploadFile, status, HTTPException, Request
from fastapi.responses import FileResponse
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from io import BytesIO
from json import loads

import combined_map
import geo_mapping
from detection_settings import show_detection_settings
from roadsight_paths import (
    seed_runtime_data,
    install_shutdown_sync,
    sync_runtime_data_back,
)
from retrain_window import show_retrain_window

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

# =========================
# Routes for interaction between the back and front-ends
# =========================


@app.post("/upload/video")
async def create_new_upload(file: UploadFile):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file was uploaded or file name is missing",
        )

    filename = file.filename
    destination_path = os.path.join(VIDEO_QUEUE_DIR, filename)

    print(f"{destination_path}")

    try:
        with open(destination_path, "wb") as buffer:
            # copy the file using streaming to be more efficient for large videos
            shutil.copyfileobj(file.file, buffer)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to save file: {str(e)}",
        )
    finally:
        await file.close()

    return {
        "info": "Successfully saved file",
        "filename": filename,
        "content_type": file.content_type,
    }


# =========================
# Endpoints for listings of detections
# =========================

@app.get("/detections-list")
async def get_detections_list():
    target = Path(REPORT_FOLDER)

    dir_info_list = []
    sub_dirs = [dir for dir in target.iterdir() if dir.is_dir()]

    for dir in sub_dirs:
        dir_info = {}
        dir_info["name"] = dir.name
        dir_info["date"] = datetime.fromtimestamp(dir.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        dir_info_list.append(dir_info)

    return dir_info_list

@app.get("/detections/{file_name}")
async def get_detections(file_name: str):
    report_path = Path(REPORT_FOLDER) / str(file_name)

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    
    report = report_path / "detection_report.csv"
    details = report_path / "detection_details_with_gps.csv"

    detection_object = {}
    if report.exists():
        detection_object["report"] = loads(pd.read_csv(report).to_json(orient="records"))
    else:
        raise HTTPException(status_code=404, detail="Report not found")
    
    if details.exists():
        detection_object["details"] = loads(pd.read_csv(details).to_json(orient="records"))
    else:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return detection_object

# =========================
# Endpoints for viewing detection videos
# =========================
@app.get("/preview-stream/{file_name}")
async def stream_video(file_name: str, request: Request):
    video_path = Path(RESULT_FOLDER) / f"detected_{file_name}.mp4"

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    
    # FileResponse handles Range headers (206 Partial Content) automatically
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=video_path.name
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

app.frontend("/", directory="dist")


if __name__ == "__main__":
    start_file_listener(VIDEO_QUEUE_DIR, VIDEO_EXTENSIONS)
