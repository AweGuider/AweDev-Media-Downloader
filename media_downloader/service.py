from .models import DownloadOptions, DownloadResult, MediaBundle
from .registry import AdapterRegistry


class MediaDownloadService:
    def __init__(self, registry: AdapterRegistry):
        self._registry = registry

    def inspect(self, url: str) -> MediaBundle:
        return self._registry.resolve(url).inspect(url)

    def download(self, bundle, options, cancel_event, progress_hook=None) -> DownloadResult:
        adapter = self._registry.resolve(bundle.source_url)
        if adapter.provider != bundle.provider:
            raise ValueError("The inspected media provider no longer matches the URL")
        return adapter.download(bundle, options, cancel_event, progress_hook)
