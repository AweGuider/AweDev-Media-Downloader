from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Provider(str, Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"


class MediaType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    MIXED = "mixed"


@dataclass(frozen=True)
class DownloadCapabilities:
    audio_extraction: bool = False
    quality_selection: bool = False
    multi_item: bool = False


@dataclass(frozen=True)
class MediaItem:
    media_id: str
    media_type: MediaType
    title: str
    upload_date: str | None = None
    duration: float | int | None = None
    thumbnail_url: str | None = None
    resolutions: tuple[str, ...] = ()


@dataclass(frozen=True)
class MediaBundle:
    provider: Provider
    source_url: str
    title: str
    creator: str = ""
    upload_date: str | None = None
    duration: float | int | None = None
    thumbnail_url: str | None = None
    live_status: str | None = None
    items: tuple[MediaItem, ...] = ()
    capabilities: DownloadCapabilities = field(default_factory=DownloadCapabilities)
    description: str | None = None

    @property
    def media_type(self):
        media_types = {item.media_type for item in self.items}
        if len(media_types) == 1:
            return next(iter(media_types))
        if media_types:
            return MediaType.MIXED
        return MediaType.VIDEO


@dataclass(frozen=True)
class DownloadOptions:
    output_directory: Path
    resolution: str = "Highest Available"
    audio_only: bool = False
    audio_format: str = "mp3"
    cleanup_enabled: bool = True
    preserve_upload_date: bool = True


@dataclass(frozen=True)
class DownloadResult:
    files: tuple[Path, ...]
