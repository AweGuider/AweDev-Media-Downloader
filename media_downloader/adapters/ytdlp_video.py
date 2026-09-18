import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from .base import MediaAdapter, ProgressHook
from ..errors import DownloadCancelled
from ..files import finalize_downloads, media_output_stem, move_downloads, write_description_sidecar
from ..models import (
    DownloadCapabilities,
    DownloadOptions,
    DownloadResult,
    MediaBundle,
    MediaItem,
    MediaType,
    Provider,
)


def _host_matches(hostname: str, supported_hosts: tuple[str, ...]) -> bool:
    hostname = hostname.lower().rstrip(".")
    return any(hostname == host or hostname.endswith(f".{host}") for host in supported_hosts)


def _resolution_sort_key(value: str) -> int:
    try:
        return int(value.removesuffix("p"))
    except ValueError:
        return 0


def _extract_resolutions(info: dict) -> tuple[str, ...]:
    resolutions = {
        f"{int(media_format['height'])}p"
        for media_format in info.get("formats") or []
        if media_format.get("height")
    }
    return tuple(sorted(resolutions, key=_resolution_sort_key, reverse=True))


def _best_thumbnail_url(info: dict) -> str | None:
    thumbnails = [
        thumbnail for thumbnail in info.get("thumbnails") or []
        if isinstance(thumbnail, dict) and thumbnail.get("url")
    ]
    if thumbnails:
        return max(
            thumbnails,
            key=lambda thumbnail: (
                int(thumbnail.get("width") or 0) * int(thumbnail.get("height") or 0),
                int(thumbnail.get("width") or 0),
            ),
        )["url"]
    return info.get("thumbnail")


def _video_format_for_resolution(resolution: str) -> str:
    if resolution == "Highest Available":
        return "bestvideo*+bestaudio/best"
    height = _resolution_sort_key(resolution) or 1080
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"


class YtDlpVideoAdapter(MediaAdapter):
    def __init__(self, provider: Provider, supported_hosts, options_factory, display_name: str):
        self.provider = provider
        self.display_name = display_name
        self._supported_hosts = tuple(supported_hosts)
        self._options_factory = options_factory

    def supports(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and _host_matches(parsed.hostname or "", self._supported_hosts)

    def inspect(self, url: str) -> MediaBundle:
        with yt_dlp.YoutubeDL(self._options_factory({"noplaylist": True})) as ydl:
            info = ydl.extract_info(url, download=False)

        entries = [entry for entry in info.get("entries") or [] if entry]
        item_infos = entries or [info]
        items = tuple(self._media_item(item_info, info) for item_info in item_infos)
        resolutions = {resolution for item in items for resolution in item.resolutions}
        title = info.get("title") or items[0].title or f"{self.display_name} video"
        return MediaBundle(
            provider=self.provider,
            source_url=url,
            title=title,
            description=info.get("description") or next(
                (item_info.get("description") for item_info in item_infos if item_info.get("description")),
                None,
            ),
            creator=info.get("channel") or info.get("uploader") or "",
            upload_date=info.get("upload_date") or items[0].upload_date,
            duration=info.get("duration") if info.get("duration") is not None else items[0].duration,
            thumbnail_url=_best_thumbnail_url(info) or items[0].thumbnail_url,
            live_status="is_live" if info.get("is_live") else info.get("live_status"),
            items=items,
            capabilities=DownloadCapabilities(
                audio_extraction=True,
                quality_selection=bool(resolutions),
                multi_item=len(items) > 1,
            ),
        )

    def _media_item(self, info: dict, parent: dict) -> MediaItem:
        title = info.get("title") or parent.get("title") or f"{self.display_name} video"
        return MediaItem(
            media_id=str(info.get("id") or parent.get("id") or "video"),
            media_type=MediaType.VIDEO,
            title=title,
            upload_date=info.get("upload_date") or parent.get("upload_date"),
            duration=info.get("duration"),
            thumbnail_url=_best_thumbnail_url(info),
            resolutions=_extract_resolutions(info),
        )

    def download(
        self,
        bundle: MediaBundle,
        options: DownloadOptions,
        cancel_event,
        progress_hook: ProgressHook | None = None,
    ) -> DownloadResult:
        staging_directory = Path(tempfile.mkdtemp(prefix="awedev-media-"))
        media_id = bundle.items[0].media_id if bundle.items else None
        title = media_output_stem(bundle.title, media_id)
        output_title = title.replace("%", "%%")
        output_template = str(staging_directory / f"{output_title}.%(ext)s")

        def progress(info):
            if cancel_event.is_set():
                raise DownloadCancelled("Download cancelled")
            if progress_hook:
                progress_hook(info)

        common_options = {
            "outtmpl": output_template,
            "noplaylist": True,
            "fragment_retries": 10,
            "concurrent_fragments": 5,
            "progress_hooks": [progress],
        }
        if options.audio_only:
            download_options = {
                **common_options,
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": options.audio_format,
                    "preferredquality": "192",
                }],
            }
        else:
            download_options = {
                **common_options,
                "format": _video_format_for_resolution(options.resolution),
                "merge_output_format": "mp4",
                "postprocessor_args": ["-c:a", "aac", "-b:a", "192k", "-c:v", "copy"],
            }

        try:
            if cancel_event.is_set():
                raise DownloadCancelled("Download cancelled")
            with yt_dlp.YoutubeDL(self._options_factory(download_options)) as ydl:
                ydl.download([bundle.source_url])
            write_description_sidecar(staging_directory, title, bundle.description)
            group_name = title if options.group_multi_item and len(bundle.items) > 1 else None
            files = move_downloads(staging_directory, options.output_directory, group_name)
            finalize_downloads(files, bundle.upload_date, options.preserve_upload_date)
            return DownloadResult(files=files)
        finally:
            if options.cleanup_enabled:
                shutil.rmtree(staging_directory, ignore_errors=True)
