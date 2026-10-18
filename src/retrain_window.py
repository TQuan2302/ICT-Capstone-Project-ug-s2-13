from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from train import (
    all_model_counts,
    discard_new_weights,
    get_paths,
    keep_new_weights as install_weights,
    retrain_compare,
)

RETRAIN_WINDOW_STYLE = """
QDialog {
    background: #f0f4f9;
}
QPushButton {
    background: white;
    color: #1a1a1a;
    border: 1px solid #ccc;
    border-radius: 8px;
    font-size: 13px;
    padding: 6px 14px;
}
QPushButton:hover {
    background: #e8eef7;
    border-color: #4a90d9;
}
QPushButton:disabled {
    color: #999;
    background: #f5f5f5;
}
QPushButton#train_btn {
    background: #4a90d9;
    color: white;
    border-color: #357abd;
    font-weight: bold;
}
QPushButton#train_btn:hover {
    background: #357abd;
}
QPushButton#train_btn:disabled {
    color: #999;
    background: #f5f5f5;
    border-color: #ccc;
}
QPushButton#keep_btn {
    background: #2e8b57;
    color: white;
    border-color: #246b43;
    font-weight: bold;
}
QPushButton#discard_btn {
    background: #c0392b;
    color: white;
    border-color: #922b21;
    font-weight: bold;
}
"""

models_panel_colors = {
    "bike_lane": ("#ffebee", "#ef9a9a", "#b71c1c"),
    "speed_limit_sign": ("#e8f5e9", "#a5d6a7", "#1b5e20"),
    "speed_advisory_sign": ("#e3f2fd", "#90caf9", "#0d47a1"),
}
models_panel_order = ("bike_lane", "speed_limit_sign", "speed_advisory_sign")

def check_retrain_ready(info: dict) -> tuple[bool, str]:
    min_feedback_needed = info.get("min_feedback", 10)
    if info["feedback"] < min_feedback_needed:
        return False, f"Insufficient feedback. Minimum required feedback images: {min_feedback_needed}"
    if info["val"] < 1:
        return False, "Needs labelled validation images before it can retrain."
    return True, "Model is ready to retrain."

class RetrainThread(QThread):
    progress = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, model_name: str, epochs: int, parent=None):
        super().__init__(parent)
        self.model_name = model_name
        self.epochs = epochs

    def run(self):
        try:
            result = retrain_compare(
                self.model_name,
                epochs=self.epochs,
                progress_callback=self.progress.emit,
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

class ModelPanel(QFrame):
    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.model_name = info["key"]
        background, border, title = models_panel_colors.get(
            self.model_name, ("#ffffff", "#dde3ed", "#1a1a1a")
        )
        self.setStyleSheet(
            "QFrame {"
            f" background: {background};"
            " border-radius: 10px;"
            f" border: 1px solid {border};"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.title = QLabel(info["label"])
        self.title.setFont(QFont("Times New Roman", 13, QFont.Bold))
        self.title.setStyleSheet(f"color: {title}; background: transparent; border: none;")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        self.counts = QLabel()
        self.counts.setWordWrap(True)
        self.counts.setStyleSheet("color: #444; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(self.counts)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #555; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(self.hint, stretch=1)

        self.folder_btn = QPushButton("Open feedback folder")
        self.folder_btn.setFixedHeight(32)
        self.train_btn = QPushButton("Retrain")
        self.train_btn.setObjectName("train_btn")
        self.train_btn.setFixedHeight(32)
        layout.addWidget(self.folder_btn)
        layout.addWidget(self.train_btn)
        self.set_info(info)

    def set_info(self, info: dict) -> None:
        self.model_name = info["key"]
        classes = info.get("classes") or []
        class_line = ""
        if len(classes) > 1:
            pretty = ", ".join(name.replace("_", " ") for name in classes)
            class_line = f"\nClasses: {pretty}"
        self.counts.setText(
            f"Feedback: {info['feedback']}\n"
            f"Past data: {info['train']}"
            f"{class_line}"
        )
        ready, reason = check_retrain_ready(info)
        self.hint.setText(reason)
        self.train_btn.setEnabled(ready)

class RetrainWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Retrain Models")
        self.setMinimumSize(800, 800)
        self.setStyleSheet(RETRAIN_WINDOW_STYLE)
        self.thread: RetrainThread | None = None
        self.result: dict | None = None
        self.panels: dict[str, ModelPanel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QLabel("Retrain Models")
        header.setFont(QFont("Times New Roman", 16, QFont.Bold))
        root.addWidget(header)

        instructions = QLabel(
            " There needs to be alteast 10 images in the feedback folder to retrain the model."
            " The model will train on past data + feedback."
            " The old model and new model will be compared on the validation set."
            " If model performance improves, Keep replaces updates the model weights and moves feedback into past data."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #0a2f6b; font-size: 14px;")
        root.addWidget(instructions)

        epochs_row = QHBoxLayout()
        epochs_row.addWidget(QLabel("Epochs"))
        self.epochs = QSpinBox()
        self.epochs.setRange(1, 200)
        self.epochs.setValue(10)
        self.epochs.setFixedWidth(50)
        epochs_row.addWidget(self.epochs)
        epochs_instructions = QLabel(
            "The greater the number of epochs, the more the model learns, but higher epochs may lead to overfitting."
        )
        epochs_instructions.setStyleSheet("color: #c0392b; font-size: 12px;")
        epochs_row.addWidget(epochs_instructions)
        epochs_row.addStretch()
        root.addLayout(epochs_row)

        models_row = QHBoxLayout()
        models_row.setSpacing(12)
        models_counts_info = {info["key"]: info for info in all_model_counts()}
        for model_name in models_panel_order:
            model_data = models_counts_info.get(model_name)
            if model_data is None:
                continue
            panel = ModelPanel(model_data)
            panel.folder_btn.clicked.connect(
                lambda _=False, model_name=model_name: self.open_feedback_folder(model_name)
            )
            panel.train_btn.clicked.connect(
                lambda _=False, model_name=model_name: self.start_train(model_name)
            )
            self.panels[model_name] = panel
            models_row.addWidget(panel, stretch=1)
        root.addLayout(models_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        self.log.setPlaceholderText("Training logs will be displayed here.")
        root.addWidget(self.log, stretch=1)

        result_row = QHBoxLayout()
        result_row.addStretch()
        self.keep_btn = QPushButton("Keep")
        self.keep_btn.setObjectName("keep_btn")
        self.keep_btn.setFixedHeight(40)
        self.keep_btn.setEnabled(False)
        self.keep_btn.clicked.connect(self.keep_new_weights)
        self.discard_btn = QPushButton("Discard")
        self.discard_btn.setObjectName("discard_btn")
        self.discard_btn.setFixedHeight(40)
        self.discard_btn.setEnabled(False)
        self.discard_btn.clicked.connect(self.discard)
        result_row.addWidget(self.keep_btn)
        result_row.addWidget(self.discard_btn)
        root.addLayout(result_row)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedSize(100, 36)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def open_feedback_folder(self, model_name: str) -> None:
        feedback_folder = get_paths(model_name)["feedback_images"]
        feedback_folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(feedback_folder)))

    def lock_while_training(self, training: bool) -> None:
        self.epochs.setEnabled(not training)
        for panel in self.panels.values():
            panel.folder_btn.setEnabled(not training)
            if training:
                panel.train_btn.setEnabled(False)
        if not training:
            self.refresh_models_panel()

    def refresh_models_panel(self) -> None:
        for info in all_model_counts():
            panel = self.panels.get(info["key"])
            if panel is not None:
                panel.set_info(info)

    def append_log(self, log: str) -> None:
        self.log.append(log)

    def start_train(self, model_name: str) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.append_log("A model is already being trained.")
            return
        if self.result is not None:
            self.append_log("Keep or discard the current training result before starting another model.")
            return
        self.log.clear()
        self.keep_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.append_log(f"Training starting for model: {model_name}…")
        self.lock_while_training(True)
        self.thread = RetrainThread(model_name, self.epochs.value(), self)
        self.thread.progress.connect(self.append_log)
        self.thread.finished_ok.connect(self.on_done)
        self.thread.failed.connect(self.on_fail)
        self.thread.start()

    def on_done(self, result: dict) -> None:
        self.result = result
        old = result["old"]
        new = result["new"]
        self.append_log(result["headline"])
        self.append_log(f"Old mAP={old['map']:.4f}")
        self.append_log(f"New mAP={new['map']:.4f}")
        self.keep_btn.setEnabled(True)
        self.discard_btn.setEnabled(True)
        if result.get("suggested") == "keep":
            self.keep_btn.setDefault(True)
        else:
            self.discard_btn.setDefault(True)
        self.lock_while_training(False)
        for panel in self.panels.values():
            panel.train_btn.setEnabled(False)

    def on_fail(self, message: str) -> None:
        self.result = None
        self.append_log("Training failed.")
        self.append_log(message)
        self.lock_while_training(False)

    def keep_new_weights(self) -> None:
        if not self.result:
            return
        live = install_weights(self.result["key"], Path(self.result["new_weights"]))
        message = "The model has been updated successfully."
        self.append_log(f"{message}\n{live}")
        self.result = None
        self.keep_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.refresh_models_panel()

    def discard(self) -> None:
        if not self.result:
            return
        discard_new_weights(self.result["key"])
        message = "Model was not updated."
        self.append_log(message)
        self.result = None
        self.keep_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.refresh_models_panel()

    def closeEvent(self, event) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.append_log("Training is still running. Wait for it to finish before closing.")
            event.ignore()
            return
        if self.result is not None:
            self.append_log("Keep or discard the training result before closing.")
            event.ignore()
            return
        event.accept()

def show_retrain_window(parent=None) -> None:
    window = RetrainWindow(parent)
    window.exec()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    show_retrain_window()

# References: this script has been written with the help of AI (chatgpt, Claude, Grok)