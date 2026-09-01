from PySide6.QtWidgets import (
    QApplication, QPushButton, QFileDialog, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QDialog, QTextEdit, QMessageBox,
    QProgressBar, QSlider
)
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QStandardPaths
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

import sys
import os
import shutil
import platform
from detection_settings import show_detection_settings

# =========================
# Basic paths
# =========================

# When frozen by PyInstaller, sys._MEIPASS is the read-only bundle directory.
# All read-only assets (images, models) live there.
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Writable user data lives outside the bundle so it survives updates.
DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "RoadSight")

UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
RESULT_FOLDER = os.path.join(DATA_DIR, "results")
REPORT_FOLDER = os.path.join(DATA_DIR, "reports")
INPUT_FOLDER = os.path.join(DATA_DIR, "testing resource")

os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)


# =========================
# Detection thread
# =========================

class DetectionThread(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, input_path, gpx_path=None):
        super().__init__()
        self.input_path = input_path
        self.gpx_path = gpx_path

    def run(self):
        try:
            import detect as _detect
            _detect.run_detection(
                input_path=self.input_path,
                gpx_path=self.gpx_path,
                move_original=False,
            )
            self.finished.emit("Detection completed. Results saved in results folder.")
        except Exception as e:
            self.error.emit(str(e))


def run_detection(input_path, gpx_path=None):
    global thread

    processing_label.setText("Processing...")
    progress_bar.setValue(30)
    QApplication.processEvents()

    thread = DetectionThread(input_path, gpx_path)
    thread.finished.connect(detection_finished)
    thread.error.connect(detection_failed)
    thread.start()


def detection_finished(message):
    progress_bar.setValue(100)
    processing_label.setText("")
    QMessageBox.information(window, "Detection Complete", message)
    progress_bar.setValue(0)


def detection_failed(error_message):
    progress_bar.setValue(0)
    processing_label.setText("")
    QMessageBox.warning(window, "Detection Failed", error_message)


# =========================
# File upload helpers
# =========================

def copy_to_uploads(file_path):
    """
    Copy selected file into uploads folder.

    If the selected file is already inside uploads, do not copy again.
    """
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    dest_path = os.path.join(UPLOAD_FOLDER, os.path.basename(file_path))

    if os.path.abspath(file_path) != os.path.abspath(dest_path):
        shutil.copy2(file_path, dest_path)
        return dest_path, "copied"

    return dest_path, "already_exists"


def upload_image():
    start_dir = os.path.abspath(INPUT_FOLDER)

    file_path, _ = QFileDialog.getOpenFileName(
        window,
        "Select Image",
        start_dir,
        "Images (*.jpg *.png *.jpeg *.bmp *.webp)"
    )

    if file_path:
        dest_path, status = copy_to_uploads(file_path)

        if status == "copied":
            QMessageBox.information(window, "Uploaded", f"Image uploaded to:\n{dest_path}")
        else:
            QMessageBox.information(window, "Uploaded", "Image already in uploads folder.")

        run_detection(dest_path)

def get_video_sidebar_locations():
    locations = []

    home = os.path.expanduser("~")
    if os.path.exists(home):
        locations.append(QUrl.fromLocalFile(home))

    # Windows normal Python
    if platform.system() == "Windows":
        for drive in ["C:/", "D:/", "E:/"]:
            if os.path.exists(drive):
                locations.append(QUrl.fromLocalFile(drive))

    # WSL / Linux access to Windows drives
    for drive in ["/mnt/c", "/mnt/d", "/mnt/e"]:
        if os.path.exists(drive):
            locations.append(QUrl.fromLocalFile(drive))

    # macOS common folders
    for folder in [
        os.path.expanduser("~/Movies"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Desktop"),
    ]:
        if os.path.exists(folder):
            locations.append(QUrl.fromLocalFile(folder))

    return locations

def upload_video():
    dialog = QFileDialog(window)
    dialog.setWindowTitle("Select Video")
    dialog.setFileMode(QFileDialog.ExistingFile)

    dialog.setNameFilter(
        "Videos (*.mp4 *.MP4 *.avi *.AVI *.mov *.MOV *.mkv *.MKV *.insv *.INSV);;All Files (*)"
    )

    start_dir = os.path.expanduser("~")
    dialog.setDirectory(start_dir)

    dialog.setSidebarUrls(get_video_sidebar_locations())

    if dialog.exec():
        file_path = dialog.selectedFiles()[0]

        suffix = os.path.splitext(file_path)[1].lower()

        gpx_path = None

        if suffix in [".mp4", ".avi", ".mkv", ".insv"]:
            gpx_path = ask_for_gpx_file(window, file_path)

        dest_path, status = copy_to_uploads(file_path)

        copied_gpx_path = None
        if gpx_path:
            copied_gpx_path, _ = copy_to_uploads(gpx_path)

        if status == "copied":
            QMessageBox.information(window, "Uploaded", f"Video uploaded to:\n{dest_path}")
        else:
            QMessageBox.information(window, "Uploaded", "Video already in uploads folder.")

        run_detection(dest_path, copied_gpx_path)

def ask_for_gpx_file(parent, video_path):
    """
    Ask user whether they have a matching GPX file.

    Used mainly for Insta360 MP4/INSV exports.
    """
    suffix = os.path.splitext(video_path)[1].lower()

    if suffix == ".mov":
        # MOV already has automatic GPS extraction.
        return None

    reply = QMessageBox.question(
        parent,
        "GPX File",
        "Do you have a matching GPX file for this video?\n\n"
        "Choose Yes for Insta360 exported MP4/INSV if you want latitude and longitude in the CSV.\n"
        "Choose No to run detection without GPS.",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes if suffix == ".insv" else QMessageBox.No
    )

    if reply == QMessageBox.No:
        return None

    gpx_path, _ = QFileDialog.getOpenFileName(
        parent,
        "Select Matching GPX File",
        os.path.dirname(video_path),
        "GPX Files (*.gpx *.GPX);;All Files (*)"
    )

    if not gpx_path:
        return None

    return gpx_path

# =========================
# Preview settings
# =========================

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".insv")
TEXT_EXTENSIONS = (".txt", ".csv", ".json", ".log")


def show_image_preview(file_path, title="Image Preview", parent=None):
    dialog = QDialog(parent or window)
    dialog.setWindowTitle(title)
    dialog.resize(900, 650)

    layout = QVBoxLayout()

    image_label = QLabel()
    image_label.setAlignment(Qt.AlignCenter)

    pixmap = QPixmap(file_path)

    if pixmap.isNull():
        QMessageBox.warning(window, "Error", "Could not load image preview.")
        return

    image_label.setPixmap(
        pixmap.scaled(850, 550, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    )

    layout.addWidget(image_label)

    close_btn = QPushButton("Close")
    close_btn.setFixedSize(100, 40)
    close_btn.setStyleSheet(
        "QPushButton {background-color:white;color:black;border-radius:8px;}"
        "QPushButton:hover{background-color:#f0f0f0}"
    )
    close_btn.clicked.connect(dialog.close)

    layout.addWidget(close_btn, alignment=Qt.AlignCenter)

    dialog.setLayout(layout)
    dialog.exec()


def show_text_preview(file_path, title="File Preview", parent=None):
    dialog = QDialog(parent or window)
    dialog.setWindowTitle(title)
    dialog.resize(900, 650)

    layout = QVBoxLayout()

    text_box = QTextEdit()
    text_box.setReadOnly(True)
    text_box.setStyleSheet("background-color: white; color: black;")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text_box.setText(f.read())
    except Exception as e:
        text_box.setText(f"Could not open file:\n{file_path}\n\n{e}")

    layout.addWidget(text_box)

    close_btn = QPushButton("Close")
    close_btn.setFixedSize(100, 40)
    close_btn.setStyleSheet(
        "QPushButton {background-color:white;color:black;border-radius:8px;}"
        "QPushButton:hover{background-color:#f0f0f0}"
    )
    close_btn.clicked.connect(dialog.close)

    layout.addWidget(close_btn, alignment=Qt.AlignCenter)

    dialog.setLayout(layout)
    dialog.exec()


def show_video_preview(file_path, title="Video Preview", parent=None):
    dialog = QDialog(parent or window)
    dialog.setWindowTitle(title)
    dialog.resize(900, 650) # Initialise dialogue size

    layout = QVBoxLayout()

    # Video widget - automatically resize video screen size when window size changes 
    video_widget = QVideoWidget()
    layout.addWidget(video_widget)

    # =========================
    # Seek slider
    # =========================

    # Creating the video slider 
    seek_slider = QSlider(Qt.Horizontal)

    # Initialise range to 0 since video duration is unknown initially
    seek_slider.setRange(0, 0)

    # Slider design style 
    seek_slider.setStyleSheet("""
        QSlider::groove:horizontal { 
            height: 6px;
            background: #cccccc;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: white;
            border: 1px solid #999;
            width: 14px;
            height: 14px;
            margin: -4px 0;
            border-radius: 7px;
        }
        QSlider::sub-page:horizontal {
            background: #4a90d9;
            border-radius: 3px;
        }
    """)

    layout.addWidget(seek_slider)

    # =========================
    # Time label
    # =========================

    # current_time / total time of video, initialises to 0
    time_label = QLabel("0:00 / 0:00")
    time_label.setAlignment(Qt.AlignCenter) 
    time_label.setStyleSheet("color: black; font-size: 12px;")
    layout.addWidget(time_label)

    # Stretch video_widget
    layout.setStretchFactor(video_widget, 1)

    # =========================
    # Control buttons
    # =========================

    controls = QHBoxLayout()

    play_btn = QPushButton("Play")
    pause_btn = QPushButton("Pause")
    close_btn = QPushButton("Close")

    for btn in [play_btn, pause_btn, close_btn]:
        btn.setFixedSize(100, 40)
        btn.setStyleSheet(
            "QPushButton {background-color:white;color:black;border-radius:8px;}"
            "QPushButton:hover{background-color:#f0f0f0}"
        )

    controls.addWidget(play_btn)
    controls.addWidget(pause_btn)
    controls.addWidget(close_btn)
    controls.setAlignment(Qt.AlignCenter)

    layout.addLayout(controls)

    # =========================
    # Media player setup
    # =========================

    player = QMediaPlayer(dialog)
    audio_output = QAudioOutput(dialog)

    player.setAudioOutput(audio_output) # connect output sound to speakers
    player.setVideoOutput(video_widget) # connect video to video widget 

    # Loads selected video file
    player.setSource(QUrl.fromLocalFile(os.path.abspath(file_path)))

    # Keep references alive.
    dialog.player = player
    dialog.audio_output = audio_output

    # =========================
    # Helper function
    # =========================

    # Converts time in milliseconds to 00:00 format
    def ms_to_str(ms):
        if ms < 0:
            return "0:00"

        total_seconds = ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        return f"{minutes}:{seconds:02d}"

    # =========================
    # Slider update logic
    # =========================

    # Check if user is dragging the slider (Default = false)
    is_seeking = [False]

    # Normal playback: Change slider position & video progress as video progresses
    def on_position_changed(position):
        # Update slider position once released 
        if not is_seeking[0]:
            seek_slider.setValue(position)

        # Update displayed time: current / remaining time
        duration = player.duration()
        time_label.setText(f"{ms_to_str(position)} / {ms_to_str(duration)}")

    # Set video time range once duration is known
    def on_duration_changed(duration):
        seek_slider.setRange(0, duration)

    # When slider is pressed change is_seek to true
    def on_slider_pressed():
        is_seeking[0] = True

    # When slider is released, change video progress and result is_seeking to false
    def on_slider_released():
        player.setPosition(seek_slider.value())
        is_seeking[0] = False

    # When slider position changes, update duration and time_label
    def on_slider_moved(position):
        duration = player.duration()
        time_label.setText(f"{ms_to_str(position)} / {ms_to_str(duration)}")

    # =========================
    # Signal connections
    # =========================

    # When playing a video normally
    player.positionChanged.connect(on_position_changed) # Video progressing normally, automatically change slider position & current time
    player.durationChanged.connect(on_duration_changed) # Set slider range

    # When slider is pressed -> released = moved / dragged, call functions respectively
    seek_slider.sliderPressed.connect(on_slider_pressed) # Set is_seeking = true
    seek_slider.sliderReleased.connect(on_slider_released) # Change slider position & is_seeking = false
    seek_slider.sliderMoved.connect(on_slider_moved) # Update current_time / total_time

    # When clicked on play, pause, close buttons
    play_btn.clicked.connect(player.play)
    pause_btn.clicked.connect(player.pause)
    close_btn.clicked.connect(dialog.close)

    dialog.setLayout(layout)

    # Autoplays video when preview opens
    player.play()
    dialog.exec()

# Format report output and colour code each detected element

def show_csv_preview(file_path, title="Report Preview", parent=None):
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea

    # Create & initialise report dialogue window 
    dialog = QDialog(parent or window)
    dialog.setWindowTitle(title)
    dialog.resize(1000, 700)

    layout = QVBoxLayout()

    # ── File name label ───────────────────────────────────────
    name_label = QLabel(os.path.basename(file_path))
    name_label.setFont(QFont("Arial", 11, QFont.Bold))
    name_label.setAlignment(Qt.AlignCenter)
    name_label.setStyleSheet("color: black; padding: 6px;")
    layout.addWidget(name_label)

    # ── Table ─────────────────────────────────────────────────
    
    # Create table widget 
    table = QTableWidget()

    # Table design style (Header colour, alternating row colours, highlighted row colours, font sizes)
    table.setStyleSheet("""
        QTableWidget {
            background-color: white;
            color: black;
            gridline-color: #dddddd;
            font-size: 12px;
        }
        QHeaderView::section {
            background-color: #4a90d9;
            color: white;
            font-weight: bold;
            padding: 6px;
            border: none;
        }
        QTableWidget::item {
            padding: 4px;
            color: black;
            background-color: white;
        }
        QTableWidget::item:alternate {
            background-color: #f5f8ff;
            color: black;
        }
        QTableWidget::item:selected {
            background-color: #4a90d9;
            color: white;
        }
        QTableWidget::item:alternate:selected {
            background-color: #4a90d9;
            color: white;
        }
    """)

    table.setAlternatingRowColors(True)

    table.setEditTriggers(QTableWidget.NoEditTriggers)

    # Column resize to fix texts
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)

    # ── Read CSV first, then build everything else ────────────
    headers = []
    data = []

    try:
        import csv
        with open(file_path, "r", encoding="utf-8") as f:
            # Read generated CSV content & convert to list of rows
            reader = csv.reader(f)
            rows = list(reader)

        if rows:
            # Separate headers & data
            headers = rows[0]
            data = rows[1:]

            # Set table dimensions according to the number of header & data 
            table.setColumnCount(len(headers))
            table.setRowCount(len(data))
            # Set header names
            table.setHorizontalHeaderLabels(headers)

            # Fill table cells
            for row_idx, row in enumerate(data):
                for col_idx, value in enumerate(row):
                    item = QTableWidgetItem(value.strip())
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(row_idx, col_idx, item)

    # When no CSV found / error opening CSV
    except Exception as e:
        table.setRowCount(1)
        table.setColumnCount(1)
        table.setItem(0, 0, QTableWidgetItem(f"Could not read file: {e}"))

    # Add table widget
    layout.addWidget(table)

    # ── Pills — one per detected class ───────────────────────
    try:
        # Arrays of different detected elements & their count 
        class_col = next(i for i, h in enumerate(headers) if h.lower() == "class")
        count_col = next(i for i, h in enumerate(headers) if h.lower() == "count")

        # Calculate total for each detected element
        class_totals = {}
        for r in data:
            if len(r) > max(class_col, count_col):
                label = r[class_col].strip().lower()
                try:
                    count = int(r[count_col].strip())
                except ValueError:
                    count = 0
                class_totals[label] = class_totals.get(label, 0) + count

        # Colour code total count for each element
        pill_colors = {
            "traffic_light":     ("#e8f5e9", "#2e7d32"),
            "road_barrier":      ("#fff3e0", "#e65100"),
            "trunk":             ("#fce4ec", "#880e4f"),
            "pole":              ("#f3e5f5", "#6a1b9a"),
            "footpath":          ("#e3f2fd", "#0d47a1"),
            "bike_lane":         ("#e8eaf6", "#283593"),
            "crosswalk_marking": ("#e0f7fa", "#006064"),
            "lane_marking":      ("#fff9c4", "#f57f17"),
            "stop_line":         ("#fbe9e7", "#bf360c"),
        }
        # Default grey for all road signs, as there are 24 classes
        default_pill = ("#f5f5f5", "#333333")

        # Position total count at the bottom of CSV report
        pills_widget = QWidget()
        pills_layout = QHBoxLayout(pills_widget)
        pills_layout.setAlignment(Qt.AlignCenter)
        pills_layout.setSpacing(8)
        pills_layout.setContentsMargins(8, 4, 8, 4)

        # Loop through all total counts and sort them
        for label, count in sorted(class_totals.items()):
            bg, fg = pill_colors.get(label, default_pill) # Get set colours for each class
            pill = QLabel(f"{label.replace('_', ' ')}: {count}") # Create label (element: count)
            pill.setAlignment(Qt.AlignCenter) # centre text

            # Style total count text
            pill.setStyleSheet(f"""
                background-color: {bg};
                color: {fg};
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: bold;
            """)
            pills_layout.addWidget(pill) # Add wifget to layout

        # Create scroll slider when number of class exceed page width
        scroll = QScrollArea()
        scroll.setWidget(pills_widget)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(48)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(scroll)

    # Error handling
    except Exception:
        pass

    # ── Buttons ───────────────────────────────────────────────
    btn_row = QHBoxLayout()

    # Export button design style & size
    export_btn = QPushButton("Export CSV")
    export_btn.setFixedSize(120, 40)
    export_btn.setStyleSheet(
        "QPushButton {background-color:#4a90d9;color:white;border-radius:8px;}"
        "QPushButton:hover{background-color:#357abd}"
    )

    # Close button design style & size
    close_btn = QPushButton("Close")
    close_btn.setFixedSize(100, 40)
    close_btn.setStyleSheet(
        "QPushButton {background-color:white;color:black;border-radius:8px;}"
        "QPushButton:hover{background-color:#f0f0f0}"
    )

    def export_csv():
        # user-selected file path
        save_path, _ = QFileDialog.getSaveFileName(
            dialog, "Export CSV", os.path.basename(file_path), "CSV Files (*.csv)"
        )
        if save_path:
            shutil.copy(file_path, save_path) # Copy CSV to user-specified filepath
            QMessageBox.information(dialog, "Exported", f"Saved to:\n{save_path}")

    # Call export / close functions when buttons clicked
    export_btn.clicked.connect(export_csv)
    close_btn.clicked.connect(dialog.close)

    # Add button widgets & align position
    btn_row.addWidget(export_btn)
    btn_row.addWidget(close_btn)
    btn_row.setAlignment(Qt.AlignCenter)
    layout.addLayout(btn_row)

    dialog.setLayout(layout)
    dialog.exec()


def browse_folder(folder_path, title, file_filter="All Files (*)"):
    os.makedirs(folder_path, exist_ok=True)

    dialog = QFileDialog(window, title, folder_path, file_filter)
    dialog.setFileMode(QFileDialog.ExistingFile)
    dialog.setViewMode(QFileDialog.Detail)

    if dialog.exec():
        selected_file = dialog.selectedFiles()[0]
        lower_path    = selected_file.lower()
        current_dir   = os.path.dirname(selected_file)  # remember where we are

        if lower_path.endswith(IMAGE_EXTENSIONS):
            show_image_preview(selected_file, title, parent=dialog)
        elif lower_path.endswith(VIDEO_EXTENSIONS):
            show_video_preview(selected_file, title, parent=dialog)
        elif lower_path.endswith(".csv"):
            show_csv_preview(selected_file, title, parent=dialog)
        elif lower_path.endswith(TEXT_EXTENSIONS):
            show_text_preview(selected_file, title, parent=dialog)
        else:
            QMessageBox.information(
                window,
                "Selected File",
                f"Preview is not supported for this file type yet.\n\n{selected_file}"
            )

        # Reopen from the same directory the user was browsing, not the root folder
        browse_folder(current_dir, title, file_filter)

def view_uploads():
    browse_folder(UPLOAD_FOLDER, "View Uploads")


def view_results():
    browse_folder(RESULT_FOLDER, "View Results")


def view_reports():
    browse_folder(REPORT_FOLDER, "View Reports")


# =========================
# Clear folders
# =========================

def clear_folder(folder):
    os.makedirs(folder, exist_ok=True)

    for name in os.listdir(folder):
        file_path = os.path.join(folder, name)

        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.remove(file_path)

            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")


def clear_uploads():
    clear_folder(UPLOAD_FOLDER)
    QMessageBox.information(window, "Uploads Cleared", "All files in uploads folder have been deleted.")


def clear_results():
    clear_folder(RESULT_FOLDER)
    QMessageBox.information(window, "Results Cleared", "All files in results folder have been deleted.")


# =========================
# User guide
# =========================

def get_existing_userguide_file(primary_path, fallback_path):
    """
    Use userguide file if it exists.
    Otherwise use root-level fallback file.
    """
    if os.path.exists(primary_path):
        return primary_path

    if os.path.exists(fallback_path):
        return fallback_path

    return primary_path


def show_user_guide():
    dialog = QDialog(window)
    dialog.setWindowTitle("📖 User Guide")
    dialog.setGeometry(150, 150, 650, 500)

    layout = QVBoxLayout()

    img_path = get_existing_userguide_file(
        os.path.join(BASE_DIR, "userguide", "description.png"),
        os.path.join(BASE_DIR, "instruction.jpeg")
    )

    txt_path = os.path.join(BASE_DIR, "userguide", "guide.txt")

    btn_layout = QHBoxLayout()

    download_img_btn = QPushButton("Download Image")
    preview_img_btn = QPushButton("Preview Image")

    download_txt_btn = QPushButton("Download Guide")
    preview_txt_btn = QPushButton("Preview Guide")

    buttons = [
        download_img_btn,
        preview_img_btn,
        download_txt_btn,
        preview_txt_btn
    ]

    for btn in buttons:
        btn.setFixedSize(160, 40)
        btn.setStyleSheet(
            "QPushButton {background-color:white;color:black;border-radius:8px;}"
            "QPushButton:hover{background-color:#f0f0f0}"
        )

    btn_layout.addWidget(download_img_btn)
    btn_layout.addWidget(preview_img_btn)
    btn_layout.addWidget(download_txt_btn)
    btn_layout.addWidget(preview_txt_btn)
    btn_layout.setAlignment(Qt.AlignCenter)

    layout.addLayout(btn_layout)

    def download_file(source_file):
        if not os.path.exists(source_file):
            QMessageBox.warning(dialog, "Error", f"File not found:\n{source_file}")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            dialog,
            "Save File",
            os.path.basename(source_file)
        )

        if save_path:
            shutil.copy(source_file, save_path)
            QMessageBox.information(dialog, "Downloaded", f"Saved to:\n{save_path}")

    def preview_image(file_path):
        if not os.path.exists(file_path):
            QMessageBox.warning(dialog, "Error", "Image not found.")
            return

        preview = QDialog(dialog)
        preview.setWindowTitle("Image Preview")
        preview.resize(800, 600)

        layout_p = QVBoxLayout()

        label = QLabel()
        pixmap = QPixmap(file_path)

        if pixmap.isNull():
            QMessageBox.warning(dialog, "Error", "Could not load image.")
            return

        label.setPixmap(
            pixmap.scaled(750, 500, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        label.setAlignment(Qt.AlignCenter)

        layout_p.addWidget(label)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(preview.close)
        layout_p.addWidget(close_btn, alignment=Qt.AlignCenter)

        preview.setLayout(layout_p)
        preview.exec()

    def preview_text(file_path):
        if not os.path.exists(file_path):
            QMessageBox.warning(dialog, "Error", "File not found.")
            return

        preview = QDialog(dialog)
        preview.setWindowTitle("Guide Preview")
        preview.resize(800, 600)

        layout_p = QVBoxLayout()

        text_box = QTextEdit()
        text_box.setReadOnly(True)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text_box.setText(f.read())
        except Exception as e:
            text_box.setText(str(e))

        layout_p.addWidget(text_box)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(preview.close)
        layout_p.addWidget(close_btn, alignment=Qt.AlignCenter)

        preview.setLayout(layout_p)
        preview.exec()

    download_img_btn.clicked.connect(lambda: download_file(img_path))
    download_txt_btn.clicked.connect(lambda: download_file(txt_path))

    preview_img_btn.clicked.connect(lambda: preview_image(img_path))
    preview_txt_btn.clicked.connect(lambda: preview_text(txt_path))

    text = QTextEdit()
    text.setReadOnly(True)
    text.setFont(QFont("Arial", 12))
    text.setStyleSheet("background-color: white; color: black;")

    text.setText(
        "Welcome to RoadSight!\n\n"
        "RoadSight detects roadway elements including:\n"
        "- Footpaths\n"
        "- Road lanes\n"
        "- Crosswalk markings\n"
        "- Stop lines\n"
        "- Trunks\n"
        "- Poles\n"
        "- Traffic lights\n\n"

        "Instructions:\n"
        "1. Store system in a folder.\n"
        "2. First launch creates 'uploads', 'results', and 'reports'.\n"
        "3. Upload image (*.jpg, *.png, *.jpeg, *.bmp, *.webp).\n"
        "4. Upload video (*.mp4, *.avi, *.mov, *.mkv).\n"
        "5. Uploaded files are copied into the uploads folder.\n"
        "6. All detection is handled by detect.py.\n"
        "7. Results are saved into the results folder.\n"
        "8. Use View Results to preview detected images/videos.\n"
        "9. Use clear buttons to clean temporary files.\n"
    )

    layout.addWidget(text)

    close_btn = QPushButton("Close")
    close_btn.setFixedSize(100, 40)
    close_btn.setStyleSheet(
        "QPushButton {background-color: white;color:black;border-radius:8px;}"
        "QPushButton:hover{background-color:#f0f0f0}"
    )
    close_btn.clicked.connect(dialog.close)

    layout.addWidget(close_btn, alignment=Qt.AlignCenter)

    dialog.setLayout(layout)
    dialog.exec()


# =========================
# Application
# =========================

app = QApplication(sys.argv)


class MainWindow(QWidget):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        background.setGeometry(0, 0, self.width(), self.height())

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Exit",
            "Do you want to exit and clear all uploads and results?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            clear_folder(UPLOAD_FOLDER)
            clear_folder(RESULT_FOLDER)
            event.accept()
        else:
            event.accept()


window = MainWindow()
window.setWindowTitle("RoadSight Detection System")
window.setGeometry(100, 100, 700, 500)


# =========================
# Background
# =========================

background = QLabel(window)

background_path = os.path.join(BASE_DIR, "background.jpeg")
bg_pixmap = QPixmap(background_path)

background.setPixmap(bg_pixmap)
background.setScaledContents(True)
background.setGeometry(0, 0, 700, 500)
background.lower()


# =========================
# Layout
# =========================

main_layout = QVBoxLayout()

title = QLabel("Welcome to RoadSight")
title.setFont(QFont("Arial", 25, QFont.Bold))
title.setAlignment(Qt.AlignCenter)
title.setStyleSheet("color: white;")
main_layout.addWidget(title)

subtitle = QLabel(
    "Upload videos or images to extract road network information\n"
)
subtitle.setFont(QFont("Arial", 15))
subtitle.setAlignment(Qt.AlignCenter)
subtitle.setStyleSheet("color: white;")
subtitle.setWordWrap(True)
main_layout.addWidget(subtitle)


# =========================
# Progress bar
# =========================

progress_bar = QProgressBar()
progress_bar.setValue(0)
progress_bar.setFixedWidth(400)
progress_bar.setStyleSheet("background-color: white;")
main_layout.addWidget(progress_bar, alignment=Qt.AlignCenter)

processing_label = QLabel("")
processing_label.setFont(QFont("Arial", 12))
processing_label.setAlignment(Qt.AlignCenter)
processing_label.setStyleSheet("color: white;")
main_layout.addWidget(processing_label, alignment=Qt.AlignCenter)


# =========================
# Buttons
# =========================

img_btn = QPushButton("🖼 Image")
img_btn.setFixedSize(130, 40)
img_btn.clicked.connect(upload_image)

video_btn = QPushButton("🎥 Video")
video_btn.setFixedSize(130, 40)
video_btn.clicked.connect(upload_video)

settings_btn = QPushButton("⚙ Detection Settings")
settings_btn.setFixedSize(160, 40)
settings_btn.clicked.connect(lambda: show_detection_settings(parent=window))

guide_btn = QPushButton("📖 User Guide")
guide_btn.setFixedSize(130, 40)
guide_btn.clicked.connect(show_user_guide)

report_btn = QPushButton("📊 View Report")
report_btn.setFixedSize(130, 40)
report_btn.clicked.connect(view_reports)

view_upload_btn = QPushButton("📂 View Uploads")
view_upload_btn.setFixedSize(130, 40)
view_upload_btn.clicked.connect(view_uploads)

view_result_btn = QPushButton("📂 View Results")
view_result_btn.setFixedSize(130, 40)
view_result_btn.clicked.connect(view_results)

clear_upload_btn = QPushButton("🗑 Clear Uploads")
clear_upload_btn.setFixedSize(130, 40)
clear_upload_btn.clicked.connect(clear_uploads)

clear_result_btn = QPushButton("🗑 Clear Results")
clear_result_btn.setFixedSize(130, 40)
clear_result_btn.clicked.connect(clear_results)

button_style = (
    "QPushButton {background-color:white;color:black;border-radius:8px;}"
    "QPushButton:hover{background-color:#f0f0f0}"
)

for btn in [
    img_btn,
    video_btn,
    report_btn,
    guide_btn,
    view_upload_btn,
    view_result_btn,
    clear_upload_btn,
    clear_result_btn,
    settings_btn
]:
    btn.setStyleSheet(button_style)


# =========================
# Button rows
# =========================

row1 = QHBoxLayout()
row1.addWidget(img_btn)
row1.addWidget(video_btn)
row1.addWidget(settings_btn)
row1.addWidget(report_btn)
row1.addWidget(guide_btn)
row1.setAlignment(Qt.AlignCenter)

row2 = QHBoxLayout()
row2.addWidget(view_upload_btn)
row2.addWidget(view_result_btn)
row2.addWidget(clear_upload_btn)
row2.addWidget(clear_result_btn)
row2.setAlignment(Qt.AlignCenter)

main_layout.addLayout(row1)
main_layout.addLayout(row2)

footer = QLabel("© 2026 RoadSight | Group 26-1")
footer.setFont(QFont("Arial", 12))
footer.setAlignment(Qt.AlignCenter)
footer.setStyleSheet("color: white;")
main_layout.addWidget(footer)

window.setLayout(main_layout)
window.show()

sys.exit(app.exec())