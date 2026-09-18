from pathlib import Path

from .ocr_component import OcrComponentManager


OCR_MEDIA_EXTENSIONS = {
    ".bmp", ".gif", ".jpeg", ".jpg", ".m4v", ".mkv", ".mov", ".mp4", ".png", ".webp",
}


def extract_visible_text(
    component: OcrComponentManager,
    downloaded_files,
    cancel_event=None,
    sample_fps: float = 1.0,
    max_frames: int = 300,
) -> tuple[Path, ...]:
    media_files = [
        str(Path(path).resolve())
        for path in downloaded_files
        if Path(path).suffix.lower() in OCR_MEDIA_EXTENSIONS
    ]
    if not media_files:
        return ()

    response = component.run_request(
        {
            "files": media_files,
            "sample_fps": sample_fps,
            "max_frames": max_frames,
        },
        cancel_event=cancel_event,
    )
    return tuple(Path(path) for path in response.get("outputs") or [])
