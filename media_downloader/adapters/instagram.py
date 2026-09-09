from urllib.parse import urlparse

from .base import MediaAdapter
from .ytdlp_video import YtDlpVideoAdapter
from ..models import DownloadOptions, DownloadResult, MediaBundle, Provider


class InstagramAdapter(MediaAdapter):
    provider = Provider.INSTAGRAM
    _HOSTS = {"instagram.com", "www.instagram.com"}

    def __init__(self, options_factory):
        self._video_adapter = YtDlpVideoAdapter(
            provider=self.provider,
            supported_hosts=self._HOSTS,
            options_factory=options_factory,
            display_name="Instagram",
        )

    @staticmethod
    def _is_reel_path(path: str) -> bool:
        parts = [part for part in path.split("/") if part]
        return len(parts) >= 2 and parts[-2] in {"reel", "reels"}

    def supports(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.scheme in {"http", "https"}
            and (parsed.hostname or "").lower() in self._HOSTS
            and self._is_reel_path(parsed.path)
        )

    def inspect(self, url: str) -> MediaBundle:
        return self._video_adapter.inspect(url)

    def download(
        self,
        bundle: MediaBundle,
        options: DownloadOptions,
        cancel_event,
        progress_hook=None,
    ) -> DownloadResult:
        return self._video_adapter.download(bundle, options, cancel_event, progress_hook)
