"""
detection_settings.py  –  RoadSight Detection Control Panel
============================================================
A PySide6 dialog that lets the user:
  • Enable / disable individual CV models before running detection
  • Adjust mask / overlay opacity (alpha) per model with a live slider
  • Adjust label text size (font scale) per model with a live slider

Settings are written to  <BASE_DIR>/detection_settings.json
detect.py reads that file at startup and overrides MODEL_CONFIGS accordingly.

Usage (standalone test):
    python detection_settings.py

Usage (integrated – call from app.py):
    from detection_settings import show_detection_settings
    show_detection_settings(parent=window)
"""

import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "RoadSight")
os.makedirs(_DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(_DATA_DIR, "detection_settings.json")

# ---------------------------------------------------------------------------
# Model metadata
# Must stay in sync with MODEL_CONFIGS in detect.py
#
# default_font_scale maps to OpenCV's fontScale argument in cv2.putText().
# The original put_label() in detect.py hardcodes 0.55.
# Slider range: 0.20 (tiny) -> 1.50 (large), stored as float in JSON.
# ---------------------------------------------------------------------------

DEFAULT_FONT_SCALE = 0.55   # matches the hardcoded value in detect.py

MODEL_META = [
    {
        "name": "footpath",
        "label": "Footpath",
        "description": "Sidewalk / footpath segmentation",
        "color": "#00ff00",
        "default_alpha": 0.40,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": True,
    },
    {
        "name": "road_evidence",
        "label": "Road Evidence",
        "description": "Crosswalk markings · Lane markings · Stop lines",
        "color": "#ff0000",
        "default_alpha": 0.50,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": True,
    },
    {
        "name": "trunk",
        "label": "Tree Trunks",
        "description": "Tree trunk detection",
        "color": "#ffa500",
        "default_alpha": 0.45,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": True,
    },
    {
        "name": "pole",
        "label": "Poles",
        "description": "Street / utility pole detection",
        "color": "#ff00ff",
        "default_alpha": 0.45,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": True,
    },
    {
        "name": "traffic_light",
        "label": "Traffic Lights",
        "description": "Traffic light bounding-box detection",
        "color": "#ffff00",
        "default_alpha": 0.45,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": False,
    },
    {
        "name": "road_barrier",
        "label": "Road Barriers",
        "description": "Road barrier / fence detection",
        "color": "#0080ff",
        "default_alpha": 0.45,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": True,
    },
    {
        "name": "bike_lane",
        "label": "Bike Lanes",
        "description": "Dedicated bicycle lane segmentation",
        "color": "#8000ff",
        "default_alpha": 0.45,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": True,
    },
    {
        "name": "traffic_sign",
        "label": "Traffic Signs",
        "description": "Speed limits · Stop signs · Warnings · Parking etc.",
        "color": "#ff8000",
        "default_alpha": 0.45,
        "default_font_scale": DEFAULT_FONT_SCALE,
        "has_mask": False,
    },
]

# Slider integer range for font scale:
#   slider value 20  -> font_scale 0.20  (tiny)
#   slider value 55  -> font_scale 0.55  (default)
#   slider value 150 -> font_scale 1.50  (large)
FONT_SCALE_SLIDER_MIN = 20
FONT_SCALE_SLIDER_MAX = 150
FONT_SCALE_SLIDER_DEFAULT = int(round(DEFAULT_FONT_SCALE * 100))  # 55


# ---------------------------------------------------------------------------
# Settings I/O
# ---------------------------------------------------------------------------

def load_settings() -> dict:
    """
    Return persisted settings dict.
    Falls back to defaults if file is missing / corrupt.
    """
    defaults = {
        m["name"]: {
            "enabled": True,
            "alpha": m["default_alpha"],
            "font_scale": m["default_font_scale"],
        }
        for m in MODEL_META
    }

    if not os.path.exists(SETTINGS_FILE):
        return defaults

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)

        # Merge: keep defaults for any model or key not yet in the file
        for name, vals in defaults.items():
            if name not in saved:
                saved[name] = vals
            else:
                saved[name].setdefault("enabled", True)
                saved[name].setdefault("alpha", vals["alpha"])
                saved[name].setdefault("font_scale", vals["font_scale"])

        return saved

    except Exception:
        return defaults


def save_settings(settings: dict) -> None:
    """Write settings dict to JSON file."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


# ---------------------------------------------------------------------------
# Colour swatch widget
# ---------------------------------------------------------------------------

class ColorSwatch(QWidget):
    """Small filled rounded rectangle showing the model's overlay colour."""

    def __init__(self, hex_color: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self._color = QColor(hex_color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#555555"), 1))
        p.setBrush(QBrush(self._color))
        p.drawRoundedRect(2, 2, 18, 18, 4, 4)


# ---------------------------------------------------------------------------
# Shared slider styles
# ---------------------------------------------------------------------------

SLIDER_STYLE = """
QSlider::groove:horizontal {
    height: 5px;
    background: #cccccc;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: white;
    border: 1px solid #888;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #4a90d9;
    border-radius: 3px;
}
QSlider::groove:horizontal:disabled {
    background: #e0e0e0;
}
QSlider::handle:horizontal:disabled {
    background: #cccccc;
    border-color: #bbb;
}
"""

FONT_SLIDER_STYLE = """
QSlider::groove:horizontal {
    height: 5px;
    background: #cccccc;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: white;
    border: 1px solid #888;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #e07b39;
    border-radius: 3px;
}
QSlider::groove:horizontal:disabled {
    background: #e0e0e0;
}
QSlider::handle:horizontal:disabled {
    background: #cccccc;
    border-color: #bbb;
}
"""

CHECKBOX_STYLE = """
QCheckBox {
    font-size: 13px;
    font-weight: bold;
    color: #1a1a1a;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid #aaa;
    background: white;
}
QCheckBox::indicator:checked {
    background: #4a90d9;
    border-color: #357abd;
    image: none;
}
"""


# ---------------------------------------------------------------------------
# Per-model row widget
# ---------------------------------------------------------------------------

class ModelRow(QFrame):
    """One card in the control panel for a single model."""

    def __init__(self, meta: dict, settings: dict, parent=None):
        super().__init__(parent)
        self.meta = meta
        self.name = meta["name"]

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: white; border-radius: 10px; border: 1px solid #dde3ed; }"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 12)
        outer.setSpacing(7)

        model_settings = settings.get(self.name, {})

        # ── Row 1: swatch + checkbox + description ────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        self.swatch = ColorSwatch(meta["color"])
        top.addWidget(self.swatch)

        self.checkbox = QCheckBox(meta["label"])
        self.checkbox.setStyleSheet(CHECKBOX_STYLE)
        self.checkbox.setChecked(model_settings.get("enabled", True))
        top.addWidget(self.checkbox)

        top.addStretch()

        desc = QLabel(meta["description"])
        desc.setStyleSheet("color: #666; font-size: 11px; border: none;")
        desc.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(desc)

        outer.addLayout(top)

        # ── Row 2: Opacity slider (blue track) ────────────────────────────
        saved_alpha = model_settings.get("alpha", meta["default_alpha"])

        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(10)

        lbl_opacity = QLabel("Opacity:")
        lbl_opacity.setStyleSheet("color: #4a90d9; font-size: 11px; font-weight: bold; border: none;")
        lbl_opacity.setFixedWidth(64)
        opacity_row.addWidget(lbl_opacity)

        self.alpha_slider = QSlider(Qt.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(int(round(saved_alpha * 100)))
        self.alpha_slider.setStyleSheet(SLIDER_STYLE)
        self.alpha_slider.setFixedHeight(22)
        opacity_row.addWidget(self.alpha_slider, stretch=1)

        self.alpha_label = QLabel(f"{int(round(saved_alpha * 100))}%")
        self.alpha_label.setFixedWidth(38)
        self.alpha_label.setStyleSheet("color: #333; font-size: 11px; border: none;")
        self.alpha_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        opacity_row.addWidget(self.alpha_label)

        outer.addLayout(opacity_row)

        # ── Row 3: Text size slider (orange track) ────────────────────────
        saved_font_scale = model_settings.get("font_scale", meta["default_font_scale"])

        text_row = QHBoxLayout()
        text_row.setSpacing(10)

        lbl_text = QLabel("Text size:")
        lbl_text.setStyleSheet("color: #e07b39; font-size: 11px; font-weight: bold; border: none;")
        lbl_text.setFixedWidth(64)
        text_row.addWidget(lbl_text)

        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(FONT_SCALE_SLIDER_MIN, FONT_SCALE_SLIDER_MAX)
        self.font_slider.setValue(int(round(saved_font_scale * 100)))
        self.font_slider.setStyleSheet(FONT_SLIDER_STYLE)
        self.font_slider.setFixedHeight(22)
        text_row.addWidget(self.font_slider, stretch=1)

        # Live "Aa" preview — font size scales with the slider value
        self.font_preview = QLabel()
        self.font_preview.setFixedWidth(38)
        self.font_preview.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.font_preview.setStyleSheet("border: none; color: #333;")
        text_row.addWidget(self.font_preview)

        outer.addLayout(text_row)

        # ── Row 4: tick labels under text-size slider ─────────────────────
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(74, 0, 48, 0)   # align under the slider track
        legend_row.setSpacing(0)

        for txt, align in [("Tiny", Qt.AlignLeft), ("Default", Qt.AlignHCenter), ("Large", Qt.AlignRight)]:
            lbl = QLabel(txt)
            lbl.setStyleSheet("color: #bbb; font-size: 9px; border: none;")
            lbl.setAlignment(align)
            legend_row.addWidget(lbl, stretch=1)

        outer.addLayout(legend_row)

        # ── Connections ───────────────────────────────────────────────────
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)
        self.font_slider.valueChanged.connect(self._on_font_changed)
        self.checkbox.stateChanged.connect(self._on_toggle)

        # Initialise preview and enabled state
        self._update_font_preview(self.font_slider.value())
        self._set_enabled_ui(self.checkbox.isChecked())

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_alpha_changed(self, value: int):
        self.alpha_label.setText(f"{value}%")

    def _on_font_changed(self, value: int):
        self._update_font_preview(value)

    def _on_toggle(self, state):
        self._set_enabled_ui(bool(state))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_font_preview(self, slider_value: int):
        """
        Render 'Aa' at a Qt point size proportional to the chosen
        OpenCV font scale so the user gets instant visual feedback.
        Mapping: pt = clamp(slider_value * 0.18, 7, 22)
        """
        pt = max(7, min(22, int(round(slider_value * 0.18))))
        self.font_preview.setFont(QFont("Arial", pt, QFont.Bold))
        self.font_preview.setText("Aa")

    def _set_enabled_ui(self, enabled: bool):
        for widget in (
            self.alpha_slider, self.alpha_label,
            self.font_slider, self.font_preview,
        ):
            widget.setEnabled(enabled)

        self.setStyleSheet(
            f"QFrame {{ background: {'white' if enabled else '#f5f5f5'}; "
            f"border-radius: 10px; border: 1px solid #dde3ed; }}"
        )

    # ------------------------------------------------------------------

    def get_values(self) -> dict:
        return {
            "enabled": self.checkbox.isChecked(),
            "alpha": self.alpha_slider.value() / 100.0,
            "font_scale": self.font_slider.value() / 100.0,
        }


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

DIALOG_STYLE = """
QDialog {
    background: #f0f4f9;
}
QPushButton {
    background: white;
    color: #1a1a1a;
    border: 1px solid #ccc;
    border-radius: 8px;
    font-size: 13px;
    padding: 6px 18px;
}
QPushButton:hover {
    background: #e8eef7;
    border-color: #4a90d9;
}
QPushButton#apply_btn {
    background: #4a90d9;
    color: white;
    border-color: #357abd;
    font-weight: bold;
}
QPushButton#apply_btn:hover {
    background: #357abd;
}
"""


class DetectionSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detection Settings")
        self.setMinimumWidth(580)
        self.setStyleSheet(DIALOG_STYLE)

        self._settings = load_settings()
        self._rows: list[ModelRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────
        header = QLabel("Detection Control Panel")
        header.setFont(QFont("Arial", 16, QFont.Bold))
        header.setStyleSheet("color: #1a1a1a;")
        root.addWidget(header)

        sub = QLabel(
            "Choose which models to run, adjust overlay opacity, and set label text size.\n"
            "Settings are saved and applied on the next detection run."
        )
        sub.setStyleSheet("color: #555; font-size: 12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ccc;")
        root.addWidget(sep)

        # ── Quick actions ─────────────────────────────────────────────────
        quick = QHBoxLayout()
        quick.setSpacing(8)

        enable_all_btn = QPushButton("Enable All")
        enable_all_btn.setFixedHeight(32)
        enable_all_btn.clicked.connect(lambda: self._set_all_enabled(True))
        quick.addWidget(enable_all_btn)

        disable_all_btn = QPushButton("Disable All")
        disable_all_btn.setFixedHeight(32)
        disable_all_btn.clicked.connect(lambda: self._set_all_enabled(False))
        quick.addWidget(disable_all_btn)

        reset_btn = QPushButton("Reset Defaults")
        reset_btn.setFixedHeight(32)
        reset_btn.clicked.connect(self._reset_defaults)
        quick.addWidget(reset_btn)

        quick.addStretch()
        root.addLayout(quick)

        # ── Colour legend for sliders ─────────────────────────────────────
        legend = QHBoxLayout()
        legend.setSpacing(16)
        for color, label_text in [("#4a90d9", "■  Opacity"), ("#e07b39", "■  Text size")]:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            legend.addWidget(lbl)
        legend.addStretch()
        root.addLayout(legend)

        # ── Scrollable model list ─────────────────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; }")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 6, 0)
        scroll_layout.setSpacing(8)

        for meta in MODEL_META:
            row = ModelRow(meta, self._settings)
            self._rows.append(row)
            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        root.addWidget(scroll_area, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #ccc;")
        root.addWidget(sep2)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply & Save")
        apply_btn.setObjectName("apply_btn")
        apply_btn.setFixedSize(130, 36)
        apply_btn.clicked.connect(self._apply)
        footer.addWidget(apply_btn)

        root.addLayout(footer)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_all_enabled(self, state: bool):
        for row in self._rows:
            row.checkbox.setChecked(state)

    def _reset_defaults(self):
        for row in self._rows:
            row.checkbox.setChecked(True)
            row.alpha_slider.setValue(int(round(row.meta["default_alpha"] * 100)))
            row.font_slider.setValue(FONT_SCALE_SLIDER_DEFAULT)

    def _apply(self):
        new_settings = {row.name: row.get_values() for row in self._rows}
        save_settings(new_settings)
        self.accept()


# ---------------------------------------------------------------------------
# Public helper for app.py
# ---------------------------------------------------------------------------

def show_detection_settings(parent=None) -> bool:
    """
    Open the dialog.
    Returns True if the user clicked 'Apply & Save', False if cancelled.
    """
    dlg = DetectionSettingsDialog(parent)
    return dlg.exec() == QDialog.Accepted


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = DetectionSettingsDialog()
    dlg.resize(600, 740)
    result = dlg.exec()
    print("Accepted:", result == QDialog.Accepted)
    if result == QDialog.Accepted:
        print("Saved settings:", json.dumps(load_settings(), indent=2))
    sys.exit(0)