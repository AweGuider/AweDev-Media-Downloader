import ctypes
import os
import platform
import re
import shutil
from datetime import datetime
from pathlib import Path


def sanitize_filename(filename: str, fallback: str = "output") -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename).strip().rstrip(".")
    return sanitized[:180] or fallback


def unique_destination_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1

    while candidate.exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1

    return candidate


def move_downloads(staging_directory: Path, output_directory: Path) -> tuple[Path, ...]:
    output_directory.mkdir(parents=True, exist_ok=True)
    files = sorted(
        path for path in staging_directory.iterdir()
        if path.is_file() and path.suffix not in {".part", ".ytdl"}
    )
    if not files:
        raise FileNotFoundError("The downloader did not produce an output file")

    destinations = []
    for source in files:
        destination = unique_destination_path(output_directory, source.name)
        shutil.move(str(source), str(destination))
        destinations.append(destination)
    return tuple(destinations)


def upload_date_to_timestamp(upload_date: str | None) -> float | None:
    if not upload_date:
        return None
    try:
        return datetime.strptime(upload_date, "%Y%m%d").timestamp()
    except ValueError:
        return None


def preserve_date_created(path: Path, created_time: float):
    if platform.system() != "Windows":
        return

    handle = ctypes.windll.kernel32.CreateFileW(
        str(path), 256, 0, None, 3, 128, None,
    )
    if handle == -1:
        return

    try:
        windows_epoch = 11644473600
        timestamp = int((created_time + windows_epoch) * 10_000_000)
        file_time = ctypes.c_longlong(timestamp)
        ctypes.windll.kernel32.SetFileTime(
            handle,
            ctypes.byref(file_time),
            ctypes.byref(file_time),
            ctypes.byref(file_time),
        )
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def finalize_downloads(paths: tuple[Path, ...], upload_date: str | None, preserve_upload_date: bool):
    if not preserve_upload_date:
        return

    timestamp = upload_date_to_timestamp(upload_date)
    if timestamp is None:
        return

    for path in paths:
        os.utime(path, (timestamp, timestamp))
        preserve_date_created(path, timestamp)
