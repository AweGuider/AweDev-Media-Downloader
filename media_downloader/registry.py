from .adapters.base import MediaAdapter
from .errors import UnsupportedUrlError


class AdapterRegistry:
    def __init__(self, adapters=()):
        self._adapters = list(adapters)

    def register(self, adapter: MediaAdapter):
        if any(existing.provider == adapter.provider for existing in self._adapters):
            raise ValueError(f"An adapter is already registered for {adapter.provider.value}")
        self._adapters.append(adapter)

    def resolve(self, url: str) -> MediaAdapter:
        for adapter in self._adapters:
            if adapter.supports(url):
                return adapter
        raise UnsupportedUrlError("This URL is not from a supported platform")
