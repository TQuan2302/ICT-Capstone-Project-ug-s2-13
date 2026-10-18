import os
import shutil
import subprocess


def ensure_folder(path):
    if path:
        os.makedirs(path, exist_ok=True)


def _get_ffmpeg_path():
    # Prefer the ffmpeg binary bundled with imageio_ffmpeg so the app works
    # without a system ffmpeg install (important when running frozen).
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def convert_mov_to_mp4(input_path, output_path):
    """
    Convert MOV into a clean MP4 file.

    The original MOV is still used for GPS extraction.
    The converted MP4 is only used for OpenCV/YOLO processing.
    """
    ffmpeg_path = _get_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg was not found. Please install FFmpeg and make sure it is in PATH.")

    ensure_folder(os.path.dirname(output_path))

    cmd = [
        ffmpeg_path,
        "-y",
        "-i", input_path,

        # Keep normal metadata if possible.
        "-map_metadata", "0",

        # Make it easy for OpenCV/Qt to read.
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",

        "-c:a", "aac",
        "-movflags", "+faststart",

        output_path
    ]

    subprocess.run(cmd, check=True)
    return output_path