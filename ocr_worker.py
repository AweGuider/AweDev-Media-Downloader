import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher
from pathlib import Path


PROTOCOL_VERSION = 1
COMPONENT_VERSION = "1.0.0"
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".m4v", ".mkv", ".mov", ".mp4"}


def create_engine():
    from rapidocr import RapidOCR

    return RapidOCR(params={"Global.log_level": "error"})


def normalize_lines(lines) -> tuple[str, ...]:
    normalized = []
    for line in lines or ():
        text = " ".join(str(line).split())
        if text:
            normalized.append(text)
    return tuple(normalized)


def recognize_image(engine, image_path: Path) -> tuple[str, ...]:
    result = engine(str(image_path))
    return normalize_lines(getattr(result, "txts", None))


def format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def materially_different(previous: str, current: str) -> bool:
    if not previous:
        return True
    return SequenceMatcher(None, previous.casefold(), current.casefold()).ratio() < 0.9


def sidecar_path(media_path: Path) -> Path:
    return media_path.with_suffix(".ocr.txt")


def write_sidecar(path: Path, text: str) -> Path | None:
    text = text.strip()
    if not text:
        return None
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(text + "\n", encoding="utf-8", newline="")
    os.replace(temporary_path, path)
    return path


def process_image(engine, media_path: Path) -> Path | None:
    return write_sidecar(sidecar_path(media_path), "\n".join(recognize_image(engine, media_path)))


def process_video(engine, media_path: Path, sample_fps: float, max_frames: int) -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to extract frames for OCR")

    with tempfile.TemporaryDirectory(prefix="awedev-ocr-frames-") as temp_directory:
        frame_pattern = Path(temp_directory) / "frame-%06d.jpg"
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel", "error",
                "-i", str(media_path),
                "-vf", f"fps={sample_fps:g}",
                "-frames:v", str(max_frames),
                "-q:v", "2",
                str(frame_pattern),
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg could not extract video frames")

        entries = []
        previous_text = ""
        for index, frame_path in enumerate(sorted(Path(temp_directory).glob("frame-*.jpg"))):
            lines = recognize_image(engine, frame_path)
            current_text = "\n".join(lines)
            if not current_text or not materially_different(previous_text, current_text):
                continue
            timestamp = index / sample_fps
            entries.append(f"[{format_timestamp(timestamp)}]\n{current_text}")
            previous_text = current_text

    return write_sidecar(sidecar_path(media_path), "\n\n".join(entries))


def process_request(request: dict) -> dict:
    if request.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Unsupported OCR protocol version")

    sample_fps = float(request.get("sample_fps") or 1.0)
    max_frames = int(request.get("max_frames") or 300)
    if sample_fps <= 0 or sample_fps > 10:
        raise ValueError("sample_fps must be greater than 0 and no more than 10")
    if max_frames <= 0 or max_frames > 300:
        raise ValueError("max_frames must be between 1 and 300")

    files = [Path(path) for path in request.get("files") or []]
    engine = create_engine()
    outputs = []
    for media_path in files:
        if not media_path.is_file():
            continue
        suffix = media_path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            output = process_image(engine, media_path)
        elif suffix in VIDEO_EXTENSIONS:
            output = process_video(engine, media_path, sample_fps, max_frames)
        else:
            continue
        if output:
            outputs.append(str(output))
    return {"ok": True, "outputs": outputs}


def self_test() -> int:
    try:
        create_engine()
        print(json.dumps({
            "ok": True,
            "component_version": COMPONENT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
        }))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


def run_request(request_path: Path) -> int:
    response_path = None
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        response_path = Path(request["response_path"])
        response = process_request(request)
    except Exception as error:
        response = {"ok": False, "error": str(error)}

    if response_path is not None:
        response_path.write_text(json.dumps(response), encoding="utf-8")
    if response.get("ok"):
        return 0
    print(response["error"], file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.request:
        return run_request(args.request)
    parser.error("either --self-test or --request is required")


if __name__ == "__main__":
    raise SystemExit(main())
