from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from roadsight_paths import (
    DATA_DIR,
    seed_runtime_data,
    sync_runtime_data_back,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".insv"}

BASE_WEIGHTS = "yolov8n.pt"
MIN_FEEDBACK = 10
RETRAIN_ROOT = DATA_DIR / "retrain"
APP_MODELS_DIR = DATA_DIR / "models"

MODEL_META = [
    {
        "name": "speed_limit_sign",
        "label": "Speed limit sign",
        "weights": "speed_limit_sign.pt",
        "class_names": ["speed_limit_sign"],
    },
    {
        "name": "speed_advisory_sign",
        "label": "Speed advisory",
        "weights": "speed_advisory_sign.pt",
        "class_names": ["curve_left", "curve_right", "speed_bump", "winding_road"],
    },
    {
        "name": "bike_lane",
        "label": "Bike lane",
        "weights": "bike_lane.pt",
        "class_names": ["bike_lane"],
    },
]

def get_paths(key: str) -> dict[str, Path]:
    root = RETRAIN_ROOT / key
    return {
        "root": root,
        "live_dir": root / "live_weight",
        "feedback_images": root / "feedback" / "images",
        "feedback_labels": root / "feedback" / "labels",
        "old_images": root / "old_data" / "images",
        "old_labels": root / "old_data" / "labels",
        "val_images": root / "val" / "images",
        "val_labels": root / "val" / "labels",
        "split": root / "yolo_split",
        "candidate": root / "candidate.pt",
    }


def spec_for(name: str) -> dict:
    for spec in MODEL_META:
        if spec["name"] == name:
            return spec
    raise KeyError(f"Unknown model: {name}")


def ensure_retrain_folders() -> Path:
    seed_runtime_data()
    APP_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    RETRAIN_ROOT.mkdir(parents=True, exist_ok=True)
    for spec in MODEL_META:
        p = get_paths(spec["name"])
        for name, path in p.items():
            # candidate.pt is a weights file, not a folder.
            if name == "candidate":
                continue
            path.mkdir(parents=True, exist_ok=True)
    return RETRAIN_ROOT


def pick_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "0"
    except Exception:
        pass
    return "cpu"


def live_weights(key: str) -> Path | None:
    """Current model in retrain/<model>/live_weight/, e.g. bike_lane.pt."""
    folder = get_paths(key)["live_dir"]
    if not folder.exists():
        return None
    path = folder / spec_for(key)["weights"]
    if path.exists():
        return path
    pts = sorted(folder.glob("*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pts[0] if pts else None


def live_target(key: str) -> Path:
    found = live_weights(key)
    if found is not None:
        return found
    return get_paths(key)["live_dir"] / spec_for(key)["weights"]


def starting_weights(key: str) -> str:
    live = live_weights(key)
    if live is not None:
        return str(live)
    return BASE_WEIGHTS


def paired_count(images_dir: Path, labels_dir: Path) -> int:
    if not images_dir.exists():
        return 0
    n = 0
    for image in images_dir.iterdir():
        if image.is_file() and image.suffix.lower() in IMAGE_EXTS:
            if (labels_dir / f"{image.stem}.txt").exists():
                n += 1
    return n


def copy_pairs(images_dir: Path, labels_dir: Path, dest_img: Path, dest_lbl: Path) -> int:
    dest_img.mkdir(parents=True, exist_ok=True)
    dest_lbl.mkdir(parents=True, exist_ok=True)
    copied = 0
    if not images_dir.exists():
        return 0
    for image in images_dir.iterdir():
        if not image.is_file() or image.suffix.lower() not in IMAGE_EXTS:
            continue
        label = labels_dir / f"{image.stem}.txt"
        shutil.copy2(image, dest_img / image.name)
        dest_txt = dest_lbl / f"{image.stem}.txt"
        if label.exists():
            shutil.copy2(label, dest_txt)
        else:
            dest_txt.write_text("", encoding="utf-8")
        copied += 1
    return copied


def class_names_for(key: str) -> list[str]:
    """Returns the class names for a given model key."""
    return list(spec_for(key)["class_names"])


def label_class_ids(labels_dir: Path) -> set[int]:
    found: set[int] = set()
    if not labels_dir.exists():
        return found
    for path in labels_dir.glob("*.txt"):
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if not parts:
                continue
            try:
                found.add(int(float(parts[0])))
            except ValueError:
                continue
    return found


def write_data_yaml(split: Path, names: list[str]) -> Path:
    names_block = "\n".join(f"  {i}: {name}" for i, name in enumerate(names))
    yaml_path = split / "data.yaml"
    yaml_path.write_text(
        (
            f"path: {split.resolve()}\n"
            "train: images/train\n"
            "val: images/val\n"
            "\n"
            "names:\n"
            f"{names_block}\n"
        ),
        encoding="utf-8",
    )
    return yaml_path


def prepare_yaml(key: str) -> Path:
    """Train on feedback + old_data. Score on frozen val."""
    ensure_retrain_folders()
    p = get_paths(key)
    old_n = paired_count(p["old_images"], p["old_labels"])
    feedback_n = paired_count(p["feedback_images"], p["feedback_labels"])
    val_n = paired_count(p["val_images"], p["val_labels"])
    label = spec_for(key)["label"]
    if feedback_n < MIN_FEEDBACK:
        raise FileNotFoundError(
            f"Need at least {MIN_FEEDBACK} labelled feedback images for {label}. "
            f"Found {feedback_n} in:\n  {p['feedback_images']}"
        )
    if val_n < 1:
        raise FileNotFoundError(
            f"No labelled validation images for {label}.\n"
            f"Put pairs in:\n  {p['val_images']}\n  {p['val_labels']}"
        )

    split = p["split"]
    if split.exists():
        shutil.rmtree(split)
    dest = {
        "train_img": split / "images" / "train",
        "train_lbl": split / "labels" / "train",
        "val_img": split / "images" / "val",
        "val_lbl": split / "labels" / "val",
    }
    copied = 0
    copied += copy_pairs(p["old_images"], p["old_labels"], dest["train_img"], dest["train_lbl"])
    copied += copy_pairs(
        p["feedback_images"], p["feedback_labels"], dest["train_img"], dest["train_lbl"]
    )
    copy_pairs(p["val_images"], p["val_labels"], dest["val_img"], dest["val_lbl"])
    names = class_names_for(key)
    seen = set()
    for folder in (p["old_labels"], p["feedback_labels"], p["val_labels"]):
        seen.update(label_class_ids(folder))
    out_of_range = sorted(class_id for class_id in seen if class_id < 0 or class_id >= len(names))
    if out_of_range:
        raise ValueError(
            f"{label} labels use class ids {out_of_range}, "
            f"but this model only has {len(names)} classes: {names}."
        )
    named = ", ".join(f"{index}={name}" for index, name in enumerate(names))
    present = ", ".join(names[class_id] for class_id in sorted(seen)) or "none"
    print(f"  train images: {copied} (old_data={old_n}, feedback={feedback_n})")
    print(f"  val images:   {val_n}")
    print(f"  classes:      {named}")
    print(f"  labels seen:  {present}")
    return write_data_yaml(split, names)


def metrics_payload(metrics=None) -> dict:
    value = 0.0
    box = getattr(metrics, "box", None) if metrics is not None else None
    if box is not None:
        value = round(float(getattr(box, "map", 0) or 0), 4)
    return {"map": value}


def evaluate_weights(weights: Path, yaml_path: Path) -> dict:
    from ultralytics import YOLO

    with tempfile.TemporaryDirectory(prefix="roadsight-val-") as tmp:
        metrics = YOLO(str(weights)).val(
            data=str(yaml_path),
            split="val",
            plots=False,
            save=False,
            verbose=False,
            device=pick_device(),
            workers=0,
            project=tmp,
            name="val",
            exist_ok=True,
        )
    return metrics_payload(metrics)


def train_one(
    key: str,
    epochs: int,
    imgsz: int,
    batch: int,
    yaml_path: Path,
    base_weights: str,
) -> Path:
    from ultralytics import YOLO

    spec = spec_for(key)
    device = pick_device()
    candidate = get_paths(key)["candidate"]
    print(f"Training {spec['label']}")
    print(f"  data: {yaml_path}")
    print(f"  device: {device}")
    print(f"  start from: {base_weights}")

    model = YOLO(base_weights)
    with tempfile.TemporaryDirectory(prefix="roadsight-train-") as tmp:
        results = model.train(
            data=str(yaml_path),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            project=tmp,
            name="train",
            exist_ok=True,
            pretrained=True,
            patience=15,
            verbose=True,
            amp=False,
            workers=0,
        )
        best = Path(results.save_dir) / "weights" / "best.pt"
        last = Path(results.save_dir) / "weights" / "last.pt"
        chosen = best if best.exists() else last
        if not chosen.exists():
            raise FileNotFoundError(f"Training finished but no weights in {results.save_dir}")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        # Older runs created candidate.pt as a directory, which makes the copy fail.
        if candidate.is_dir():
            shutil.rmtree(candidate)
        shutil.copy2(chosen, candidate)
    return candidate


def move_feedback_to_old_data(key: str) -> int:
    """
    If a better model is kept, fold new feedback into old_data and clear feedback.

    A feedback file whose name is already in old_data is dropped.
    """
    p = get_paths(key)
    p["old_images"].mkdir(parents=True, exist_ok=True)
    p["old_labels"].mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    images_dir = p["feedback_images"]
    if not images_dir.exists():
        return 0
    for image in list(images_dir.iterdir()):
        if not image.is_file() or image.suffix.lower() not in IMAGE_EXTS:
            continue
        label = p["feedback_labels"] / f"{image.stem}.txt"
        dest_img = p["old_images"] / image.name
        if dest_img.exists():
            image.unlink()
            if label.exists():
                label.unlink()
            skipped += 1
            continue
        shutil.move(str(image), str(dest_img))
        dest_lbl = p["old_labels"] / f"{image.stem}.txt"
        if label.exists() and not dest_lbl.exists():
            shutil.move(str(label), str(dest_lbl))
        moved += 1
    for leftover in p["feedback_labels"].iterdir() if p["feedback_labels"].exists() else []:
        if leftover.is_file():
            leftover.unlink()
    if skipped:
        print(f"Skipped {skipped} feedback images already in old_data.")
    return moved


def update_live_weights(key: str, new_weights: Path) -> Path:
    target = live_target(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(new_weights, target)
    app_copy = APP_MODELS_DIR / spec_for(key)["weights"]
    app_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(new_weights, app_copy)
    return target


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def keep_new_weights(key: str, new_weights: Path) -> Path:
    live = update_live_weights(key, Path(new_weights))
    moved = move_feedback_to_old_data(key)
    candidate = get_paths(key)["candidate"]
    if candidate.exists() and candidate.resolve() != Path(live).resolve():
        remove_path(candidate)
    print(f"Kept new weights for {key}: {live}")
    print(f"Moved {moved} feedback images into old_data.")
    sync_runtime_data_back()
    return live


def discard_new_weights(key: str | None) -> None:
    if not key:
        return
    candidate = get_paths(key)["candidate"]
    remove_path(candidate)
    print(f"Discarded candidate weights for {key}. Live model and feedback unchanged.")


def all_model_counts() -> list[dict]:
    ensure_retrain_folders()
    models = []
    for spec in MODEL_META:
        key = spec["name"]
        p = get_paths(key)
        models.append(
            {
                "key": key,
                "label": spec["label"],
                "feedback": paired_count(p["feedback_images"], p["feedback_labels"]),
                "train": paired_count(p["old_images"], p["old_labels"]),
                "val": paired_count(p["val_images"], p["val_labels"]),
                "min_feedback": MIN_FEEDBACK,
                "has_live": live_weights(key) is not None,
                "classes": list(spec["class_names"]),
            }
        )
    return models


def retrain_compare(
    key: str,
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 8,
    progress_callback=None,
) -> dict:
    def note(message: str) -> None:
        print(message)
        if progress_callback:
            progress_callback(message)

    spec = spec_for(key)
    ensure_retrain_folders()
    note(f"Preparing dataset for {spec['label']}…")
    yaml_path = prepare_yaml(key)
    start = starting_weights(key)
    old_path = live_weights(key)
    note("Training… this can take a few minutes.")
    new_weights = train_one(key, epochs, imgsz, batch, yaml_path, start)
    note("Evaluating the new model on val…")
    new_metrics = evaluate_weights(new_weights, yaml_path)
    if old_path is None:
        old_metrics = metrics_payload()
        improved = True
        headline = (
            f"First trained {spec['label']} model is ready. "
            f"mAP={new_metrics['map']:.4f}. Keep it to install the weights."
        )
    else:
        note("Evaluating the current live model on val…")
        old_metrics = evaluate_weights(old_path, yaml_path)
        improved = new_metrics["map"] >= old_metrics["map"]
        if improved:
            headline = (
                f"Val improved for {spec['label']}: "
                f"mAP {old_metrics['map']:.4f} → {new_metrics['map']:.4f}. "
                "Keep to replace live weights, or discard to leave them unchanged."
            )
        else:
            headline = (
                f"Val did not improve for {spec['label']}: "
                f"live mAP {old_metrics['map']:.4f} vs new {new_metrics['map']:.4f}. "
                "Discard is safer unless you still want the new weights."
            )
    return {
        "key": key,
        "label": spec["label"],
        "new_weights": str(new_weights),
        "headline": headline,
        "suggested": "keep" if improved else "discard",
        "old": old_metrics,
        "new": new_metrics,
        "improved": improved,
    }


# References: this script has been written with the help of AI (chatgpt, Claude, Grok)