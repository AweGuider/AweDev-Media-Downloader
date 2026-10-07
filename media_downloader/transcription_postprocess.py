from dataclasses import dataclass
from pathlib import Path

from .transcript_text import subtitle_to_transcript, transcript_path


TRANSCRIPTION_MEDIA_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".opus", ".wav", ".webm",
}


@dataclass(frozen=True)
class TranscriptionResult:
    outputs: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    consumed_sources: tuple[Path, ...] = ()


def _matching_source(media_path: Path, sources: list[Path]) -> Path | None:
    prefix = f"{media_path.stem}."
    return next((source for source in sources if source.name.startswith(prefix)), None)


def create_transcripts(component, downloaded_files, source_files=(), cancel_event=None) -> TranscriptionResult:
    media_files = [
        Path(path).resolve()
        for path in downloaded_files
        if Path(path).suffix.lower() in TRANSCRIPTION_MEDIA_EXTENSIONS
    ]
    available_sources = [Path(path).resolve() for path in source_files]
    outputs = []
    warnings = []
    consumed_sources = []
    local_media = []

    for media_path in media_files:
        source = _matching_source(media_path, available_sources)
        if source:
            consumed_sources.append(source)
            try:
                output = subtitle_to_transcript(source, transcript_path(media_path))
            except OSError as error:
                warnings.append(f"{media_path.name}: could not read source captions ({error})")
                output = None
            if output:
                outputs.append(output)
                continue
        local_media.append(str(media_path))

    if local_media:
        response = component.run_request(
            {"files": local_media},
            cancel_event=cancel_event,
        )
        outputs.extend(Path(path) for path in response.get("outputs") or [])
        warnings.extend(str(warning) for warning in response.get("warnings") or [])

    return TranscriptionResult(
        outputs=tuple(outputs),
        warnings=tuple(warnings),
        consumed_sources=tuple(consumed_sources),
    )
