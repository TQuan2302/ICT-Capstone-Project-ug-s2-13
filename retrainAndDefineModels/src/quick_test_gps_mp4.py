from pathlib import Path
from datetime import timedelta

from gps_from_mov import extract_mov_gps_points
from detect import load_models, process_video


ROOT = Path(__file__).resolve().parent

# Original full MOV, only used for GPS extraction
FULL_MOV_PATH = Path("/mnt/c/Users/Irene/Downloads/FILE230923-151719-001998F.MOV")

# Short MP4, used for fast detection test
SHORT_MP4_PATH = ROOT / "uploads" / "test_30sec.mp4"

# If your short MP4 starts from the beginning of the MOV, keep this as 0.
# If your short MP4 starts 2 minutes into the MOV, use 120.
START_OFFSET_SECONDS = 0

# How long your test clip is
CLIP_LENGTH_SECONDS = 30


def make_gps_points_for_clip(full_gps_points, start_offset_seconds, clip_length_seconds):
    if not full_gps_points:
        return []

    original_start_time = full_gps_points[0]["time"]
    clip_start_time = original_start_time + timedelta(seconds=start_offset_seconds)
    clip_end_time = clip_start_time + timedelta(seconds=clip_length_seconds)

    clip_gps_points = []

    # Add one artificial starting point so detect.py treats the clip as starting exactly here.
    closest_start_point = min(
        full_gps_points,
        key=lambda p: abs((p["time"] - clip_start_time).total_seconds())
    ).copy()

    closest_start_point["time"] = clip_start_time
    clip_gps_points.append(closest_start_point)

    for point in full_gps_points:
        if clip_start_time <= point["time"] <= clip_end_time:
            clip_gps_points.append(point)

    return clip_gps_points


def main():
    if not FULL_MOV_PATH.exists():
        raise FileNotFoundError(f"Full MOV not found: {FULL_MOV_PATH}")

    if not SHORT_MP4_PATH.exists():
        raise FileNotFoundError(f"Short MP4 not found: {SHORT_MP4_PATH}")

    print("Extracting GPS from original MOV...")
    full_gps_points = extract_mov_gps_points(FULL_MOV_PATH)
    print(f"Full GPS points loaded: {len(full_gps_points)}")

    gps_points_for_clip = make_gps_points_for_clip(
        full_gps_points=full_gps_points,
        start_offset_seconds=START_OFFSET_SECONDS,
        clip_length_seconds=CLIP_LENGTH_SECONDS
    )

    print(f"GPS points for short clip: {len(gps_points_for_clip)}")

    if not gps_points_for_clip:
        raise ValueError("No GPS points available for this short clip.")

    print("Loading models...")
    loaded_models = load_models()

    print("Running short MP4 detection with GPS...")
    process_video(
        file_path=SHORT_MP4_PATH,
        loaded_models=loaded_models,
        gps_points=gps_points_for_clip,
        source_file_path=FULL_MOV_PATH,
        output_stem="quick_gps_test_30sec"
    )

    print("Done.")


if __name__ == "__main__":
    main()