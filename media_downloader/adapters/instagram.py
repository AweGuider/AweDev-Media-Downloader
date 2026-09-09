import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import instaloader

from .base import MediaAdapter
from .ytdlp_video import YtDlpVideoAdapter
from ..errors import DownloadCancelled
from ..files import finalize_downloads, move_downloads, sanitize_filename
from ..models import (
    DownloadCapabilities,
    DownloadOptions,
    DownloadResult,
    MediaBundle,
    MediaItem,
    MediaType,
    Provider,
)


class InstagramAdapter(MediaAdapter):
    provider = Provider.INSTAGRAM
    _HOSTS = {"instagram.com", "www.instagram.com"}

    def __init__(self, options_factory, loader_factory=None, post_factory=None):
        self._video_adapter = YtDlpVideoAdapter(
            provider=self.provider,
            supported_hosts=self._HOSTS,
            options_factory=options_factory,
            display_name="Instagram",
        )
        self._loader_factory = loader_factory or self._create_loader
        self._post_factory = post_factory or instaloader.Post.from_shortcode

    @staticmethod
    def _create_loader():
        return instaloader.Instaloader(
            quiet=True,
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            save_metadata=False,
            post_metadata_txt_pattern="",
            request_timeout=30,
        )

    @staticmethod
    def _is_reel_path(path: str) -> bool:
        parts = [part for part in path.split("/") if part]
        return len(parts) >= 2 and parts[-2] in {"reel", "reels"} and parts[-1] != "audio"

    @staticmethod
    def _post_shortcode(path: str) -> str | None:
        parts = [part for part in path.split("/") if part]
        try:
            post_index = parts.index("p")
            return parts[post_index + 1]
        except (ValueError, IndexError):
            return None

    def supports(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme in {"http", "https"}
            and (parsed.hostname or "").lower() in self._HOSTS
            and bool(self._is_reel_path(parsed.path) or self._post_shortcode(parsed.path))
        )

    def inspect(self, url: str) -> MediaBundle:
        parsed = urlparse(url)
        if self._is_reel_path(parsed.path):
            return self._video_adapter.inspect(url)

        shortcode, _, post = self._load_post(parsed.path)
        item_media = self._post_media(post)
        if not item_media:
            raise ValueError("Instagram did not return any downloadable media")
        upload_date = post.date_utc.strftime("%Y%m%d")
        creator = post.owner_username
        title = f"Instagram post by {creator} [{shortcode}]"
        items = tuple(
            MediaItem(
                media_id=f"{shortcode}-{index}",
                media_type=media_type,
                title=f"{title} {index}",
                upload_date=upload_date,
                thumbnail_url=thumbnail_url,
            )
            for index, (media_type, _, thumbnail_url) in enumerate(item_media, start=1)
        )
        return MediaBundle(
            provider=self.provider,
            source_url=url,
            title=title,
            creator=creator,
            upload_date=upload_date,
            thumbnail_url=_first_thumbnail(item_media),
            items=items,
            capabilities=DownloadCapabilities(multi_item=len(items) > 1),
        )

    def _load_post(self, path: str):
        shortcode = self._post_shortcode(path)
        if not shortcode:
            raise ValueError("This Instagram post URL is not supported")
        loader = self._loader_factory()
        return shortcode, loader, self._post_factory(loader.context, shortcode)

    @staticmethod
    def _post_media(post):
        if post.typename == "GraphSidecar":
            return [
                (
                    MediaType.VIDEO if node.is_video else MediaType.IMAGE,
                    node.video_url if node.is_video else node.display_url,
                    node.display_url,
                )
                for node in post.get_sidecar_nodes()
            ]
        if post.typename == "GraphVideo":
            return [(MediaType.VIDEO, post.video_url, post.url)]
        if post.typename == "GraphImage":
            return [(MediaType.IMAGE, post.url, post.url)]
        raise ValueError(f"Unsupported Instagram post type: {post.typename}")

    def download(
        self,
        bundle: MediaBundle,
        options: DownloadOptions,
        cancel_event,
        progress_hook=None,
    ) -> DownloadResult:
        parsed = urlparse(bundle.source_url)
        if self._is_reel_path(parsed.path):
            return self._video_adapter.download(bundle, options, cancel_event, progress_hook)
        if options.audio_only:
            raise ValueError("Audio-only mode is not available for Instagram posts")

        shortcode, loader, post = self._load_post(parsed.path)
        item_media = self._post_media(post)
        if not item_media:
            raise ValueError("Instagram did not return any downloadable media")
        staging_directory = Path(tempfile.mkdtemp(prefix="awedev-instagram-"))
        base_name = sanitize_filename(f"Instagram post by {post.owner_username} [{shortcode}]")
        try:
            for index, (_, media_url, _) in enumerate(item_media, start=1):
                if cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled")
                if not media_url:
                    raise ValueError(f"Instagram did not return media item {index}")
                if progress_hook:
                    progress_hook({
                        "status": "downloading",
                        "_percent_str": f"{index / len(item_media) * 100:.1f}%",
                        "_speed_str": "N/A",
                        "_eta_str": "N/A",
                    })
                suffix = f" {index:02d}" if len(item_media) > 1 else ""
                loader.download_pic(
                    str(staging_directory / f"{base_name}{suffix}"),
                    media_url,
                    post.date_utc,
                )

            files = move_downloads(staging_directory, options.output_directory)
            finalize_downloads(files, bundle.upload_date, options.preserve_upload_date)
            return DownloadResult(files=files)
        finally:
            if options.cleanup_enabled:
                shutil.rmtree(staging_directory, ignore_errors=True)


def _first_thumbnail(item_media):
    return item_media[0][2] if item_media else None
