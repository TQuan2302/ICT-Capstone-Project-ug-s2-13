# This file contains the paths to the data folders and the functions to manage them.
# It first finds a writable data folder:
# 1. Mac: ~/Library/Application Support/RoadSight
#    Windows: %APPDATA%\RoadSight
# 2. <project>/data
# 3. ~/Documents/RoadSight

from __future__ import annotations

import atexit
import os
import shutil
import sys
from pathlib import Path

MODEL_FILES = (
    "speed_limit_sign.pt",
    "speed_advisory_sign.pt",
    "bike_lane.pt",
)

MODEL_NAMES = (
    "speed_limit_sign",
    "speed_advisory_sign",
    "bike_lane",
)

RUNTIME_PAIRS = (
    ("train/images", "old_data/images"),
    ("train/labels", "old_data/labels"),
    ("val/images", "val/images"),
    ("val/labels", "val/labels"),
)

SHUTDOWN_PAIRS = (
    ("train/images", "old_data/images"),
    ("train/labels", "old_data/labels"),
)

seeded = False
syncing_back = False
atexit_hooked = False
qt_hooked = False

def writable_root() -> Path:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        for parent in exe.parents:
            if parent.name.endswith(".app"):
                return parent.parent
        return exe.parent

    here = Path(__file__).resolve().parent
    if here.name == "src":
        return here.parent
    return here

def read_only_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return writable_root()

def check_writable(folder: Path) -> bool:
    probe = folder / ".write_probe"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ok")
    except OSError:
        return False
    try:
        probe.unlink()
    except OSError:
        pass
    return True

def documents_data_dir() -> Path:
    return Path.home() / "Documents" / "RoadSight"

def project_data_dir() -> Path:
    return writable_root() / "data"

def app_support_data_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "RoadSight"
        return Path.home() / "AppData" / "Roaming" / "RoadSight"
    return Path.home() / "Library" / "Application Support" / "RoadSight"

def tree_writable(root: Path) -> bool:
    return all(
        check_writable(root / name)
        for name in ("", "uploads", "results", "reports")
    )

def resolve_data_dir() -> Path:
    for candidate in (app_support_data_dir(), project_data_dir(), documents_data_dir()):
        if tree_writable(candidate):
            return candidate

    raise OSError(
        f"Can not write to {project_data_dir()} or {app_support_data_dir()}."
    )

DATA_DIR = resolve_data_dir()

def copy_file(src: Path, dest: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        src_stat = src.stat()
        dest_stat = dest.stat()
        if dest_stat.st_mtime > src_stat.st_mtime:
            return False
        if dest_stat.st_size == src_stat.st_size and dest_stat.st_mtime >= src_stat.st_mtime:
            return False
    shutil.copy2(src, dest)
    return True
  
def iterate_files(folder: Path):
    if not folder.exists():
        return
    for path in folder.rglob("*"):
        if path.is_file() and not path.name.startswith(".") and path.name != ".DS_Store":
            yield path

def copy_files(src_dir: Path, dest_dir: Path, copy_file=copy_file) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        return 0
    copied = 0
    for src in iterate_files(src_dir):
        dest = dest_dir / src.relative_to(src_dir)
        if copy_file(src, dest):
            copied += 1
    return copied

def has_files(folder: Path) -> bool:
    if not folder.exists():
        return False
    return any(path.is_file() and not path.name.startswith(".") for path in folder.rglob("*"))

def get_roots() -> list[Path]:
    roots: list[Path] = []
    for path in (writable_root(), read_only_root()):
        if path not in roots:
            roots.append(path)
    return roots

def setup_runtime_folders() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "models").mkdir(parents=True, exist_ok=True)
    for key in MODEL_NAMES:
        root = DATA_DIR / "retrain" / key
        for rel in (
            "live_weight",
            "old_data/images",
            "old_data/labels",
            "val/images",
            "val/labels",
            "feedback/images",
            "feedback/labels",
        ):
            (root / rel).mkdir(parents=True, exist_ok=True)

def get_newest_weight(*candidates: Path) -> Path | None:
    existing = [path for path in candidates if path.exists() and path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: (path.stat().st_mtime, path.stat().st_size))

def seed_runtime_data() -> Path:
    global seeded
    if seeded:
        return DATA_DIR

    setup_runtime_folders()
    models_dest = DATA_DIR / "models"
    copied_weights = 0
    copied_dataset = 0

    for source in get_roots():
        models_src = source / "models"
        for name in MODEL_FILES:
            src = models_src / name
            if copy_file(src, models_dest / name):
                copied_weights += 1

    for key in MODEL_NAMES:
        weight_name = f"{key}.pt"
        live_dest = DATA_DIR / "retrain" / key / "live_weight" / weight_name
        docs_model = models_dest / weight_name
        newest = get_newest_weight(
            docs_model,
            *[source / "models" / weight_name for source in get_roots()],
            live_dest,
        )
        if newest is not None:
            if copy_file(newest, live_dest):
                copied_weights += 1
            if copy_file(newest, docs_model):
                copied_weights += 1

        for project_rel, docs_rel in RUNTIME_PAIRS:
            for source in get_roots():
                copied_dataset += copy_files(
                    source / "dataset" / key / project_rel,
                    DATA_DIR / "retrain" / key / docs_rel,
                )

    print(f"RoadSight data folder: {DATA_DIR}")
    print(
        "Copied from project as needed: "
        f"{copied_weights} weight file(s), "
        f"{copied_dataset} dataset file(s)."
    )
    seeded = True
    return DATA_DIR

def sync_runtime_data_back() -> None:
    """
    On close: if Documents data changed, upload it into the project folder:
    live weights -> models/, old_data -> dataset/<model>/train.
    val and feedback stay in Documents.
    """
    global syncing_back
    if syncing_back:
        return
    syncing_back = True
    try:
        dest_root = writable_root()
        if not check_writable(dest_root):
            print(f"Could not write dataset/weights back to {dest_root}")
            return
        if dest_root.resolve() == DATA_DIR.resolve():
            return

        models_dest = dest_root / "models"
        dataset_dest = dest_root / "dataset"
        copied_weights = 0
        copied_dataset = 0

        for key in MODEL_NAMES:
            weight_name = f"{key}.pt"
            newest = get_newest_weight(
                DATA_DIR / "retrain" / key / "live_weight" / weight_name,
                DATA_DIR / "models" / weight_name,
            )
            if newest is not None and copy_file(newest, models_dest / weight_name):
                copied_weights += 1

            docs_root = DATA_DIR / "retrain" / key
            for project_rel, docs_rel in SHUTDOWN_PAIRS:
                src = docs_root / docs_rel
                if not has_files(src):
                    continue
                copied_dataset += copy_files(
                    src,
                    dataset_dest / key / project_rel,
                )

        print(
            f"Uploaded from Documents to project {dest_root}: "
            f"{copied_weights} live weight(s), {copied_dataset} dataset file(s)."
        )
    except Exception as exc:
        print(f"Could not write dataset/weights back to the project folder: {exc}")
    finally:
        syncing_back = False


def install_shutdown_sync() -> None:
    """Call once at import (atexit) and again after QApplication exists."""
    global atexit_hooked, qt_hooked
    if not atexit_hooked:
        atexit.register(sync_runtime_data_back)
        atexit_hooked = True
    if qt_hooked:
        return
    try:
        from PySide6.QtCore import QCoreApplication

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(sync_runtime_data_back)
            qt_hooked = True
    except Exception:
        pass


# References: this script has been written with the help of AI (chatgpt, Claude, Grok)