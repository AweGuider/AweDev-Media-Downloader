from abc import ABC, abstractmethod
from collections.abc import Callable
from threading import Event

from ..models import DownloadOptions, DownloadResult, MediaBundle, Provider


ProgressHook = Callable[[dict], None]


class MediaAdapter(ABC):
    provider: Provider

    @abstractmethod
    def supports(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inspect(self, url: str) -> MediaBundle:
        raise NotImplementedError

    @abstractmethod
    def download(
        self,
        bundle: MediaBundle,
        options: DownloadOptions,
        cancel_event: Event,
        progress_hook: ProgressHook | None = None,
    ) -> DownloadResult:
        raise NotImplementedError
