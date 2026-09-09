from urllib.parse import urlparse

from .base import MediaAdapter
from .ytdlp_video import YtDlpVideoAdapter
from ..models import DownloadOptions, DownloadResult, MediaBundle, Provider


class TikTokAdapter(MediaAdapter):
    provider = Provider.TIKTOK
    _HOSTS = ("tiktok.com", "tiktokv.com")
    _SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}

    def __init__(self, options_factory):
        self._video_adapter = YtDlpVideoAdapter(
            provider=self.provider,
            supported_hosts=self._HOSTS,
            options_factory=options_factory,
            display_name="TikTok",
        )

    @classmethod
    def _is_video_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"}:
            return False
        if host in cls._SHORT_HOSTS:
            return bool(parsed.path.strip("/"))
        if not any(host == supported or host.endswith(f".{supported}") for supported in cls._HOSTS):
            return False

        parts = [part.lower() for part in parsed.path.split("/") if part]
        if len(parts) >= 3 and parts[0].startswith("@") and parts[1] == "video":
            return True
        if len(parts) >= 2 and parts[0] in {"t", "v"}:
            return True
        if len(parts) >= 2 and parts[0] == "embed":
            return True
        if len(parts) >= 3 and parts[0] == "share" and parts[1] == "video":
            return True
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
