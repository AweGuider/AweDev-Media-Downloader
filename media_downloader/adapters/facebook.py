from urllib.parse import parse_qs, urlparse

from .base import MediaAdapter
from .ytdlp_video import YtDlpVideoAdapter
from ..models import DownloadOptions, DownloadResult, MediaBundle, Provider


class FacebookAdapter(MediaAdapter):
    provider = Provider.FACEBOOK
    _HOSTS = ("facebook.com", "fb.watch")

    def __init__(self, options_factory):
        self._video_adapter = YtDlpVideoAdapter(
            provider=self.provider,
            supported_hosts=self._HOSTS,
            options_factory=options_factory,
            display_name="Facebook",
        )

    @staticmethod
    def _is_video_url(url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"}:
            return False
        if host == "fb.watch" or host.endswith(".fb.watch"):
            return bool(parsed.path.strip("/"))
        if host != "facebook.com" and not host.endswith(".facebook.com"):
            return False

        parts = [part.lower() for part in parsed.path.split("/") if part]
        if not parts:
            return False
        if parts[0] in {"reel", "reels"} and len(parts) >= 2:
            return True
        if len(parts) >= 3 and parts[0] == "share" and parts[1] in {"r", "v"}:
            return True
        if "videos" in parts and parts.index("videos") + 1 < len(parts):
            return True
        if parts[0] in {"watch", "video.php"}:
            return bool(parse_qs(parsed.query).get("v"))
        return False

    def supports(self, url: str) -> bool:
        return self._is_video_url(url)

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
