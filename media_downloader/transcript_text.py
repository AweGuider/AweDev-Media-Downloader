import html
import os
import re
from pathlib import Path


TIMESTAMP_LINE = re.compile(
    r"^(?P<hours>\d{1,2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})[,.](?P<milliseconds>\d{3})\s+-->"
)
TAG = re.compile(r"<[^>]+>")


def format_timestamp(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def transcript_path(media_path: Path) -> Path:
    return media_path.with_suffix(".transcript.txt")


def write_transcript(path: Path, text: str) -> Path | None:
    text = text.strip()
    if not text:
        return None
    temporary_path = path.with_name(f"{path.name}.tmp")
    temporary_path.write_text(text + "\n", encoding="utf-8", newline="")
    os.replace(temporary_path, path)
    return path


def parse_subtitle_text(text: str) -> tuple[tuple[float, str], ...]:
    entries = []
    lines = text.replace("\ufeff", "").replace("\r\n", "\n").split("\n")
    index = 0
    previous_text = ""
    while index < len(lines):
        match = TIMESTAMP_LINE.match(lines[index].strip())
        if not match:
            index += 1
            continue

        start = (
            int(match.group("hours")) * 3600
            + int(match.group("minutes")) * 60
            + int(match.group("seconds"))
            + int(match.group("milliseconds")) / 1000
        )
        index += 1
        cue_lines = []
        while index < len(lines) and lines[index].strip():
            cleaned = html.unescape(TAG.sub("", lines[index])).strip()
            if cleaned:
                cue_lines.append(cleaned)
            index += 1
        cue_text = " ".join(" ".join(cue_lines).split())
        if cue_text and cue_text.casefold() != previous_text.casefold():
            entries.append((start, cue_text))
            previous_text = cue_text
    return tuple(entries)


def render_transcript(entries) -> str:
    return "\n".join(f"[{format_timestamp(start)}] {text}" for start, text in entries)


def subtitle_to_transcript(subtitle_path: Path, output_path: Path) -> Path | None:
    text = subtitle_path.read_text(encoding="utf-8-sig", errors="replace")
    return write_transcript(output_path, render_transcript(parse_subtitle_text(text)))
