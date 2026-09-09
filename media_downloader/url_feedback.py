from urllib.parse import urlparse

from .errors import UnsupportedUrlError
from .health import PROVIDER_LABELS
from .models import Provider


def provider_from_url(url: str) -> Provider | None:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if _host_matches(host, "youtube.com", "youtu.be", "youtube-nocookie.com"):
        return Provider.YOUTUBE
    if _host_matches(host, "instagram.com"):
        return Provider.INSTAGRAM
    if _host_matches(host, "facebook.com", "fb.watch"):
        return Provider.FACEBOOK
    if _host_matches(host, "tiktok.com", "tiktokv.com", "tt.site"):
        return Provider.TIKTOK
    return None


def unsupported_url_message(url: str) -> str:
    parsed = urlparse(url)
    provider = provider_from_url(url)
    path_parts = [part.lower() for part in parsed.path.split("/") if part]
    host = (parsed.hostname or "").lower().rstrip(".")

    if provider == Provider.INSTAGRAM:
        if path_parts and path_parts[0] == "stories":
            return "Instagram Stories require a logged-in session and are not supported in this release."
        return "This Instagram URL type is not supported. Paste a Reel or post/carousel URL."
    if provider == Provider.FACEBOOK:
        return "Facebook posts and photos are not supported. Paste a public video or Reel URL."
    if provider == Provider.TIKTOK:
        if host == "tt.site" or host.endswith(".tt.site"):
            return (
                "This tt.site share link is unsupported or expired. "
                "Paste a vm.tiktok.com link or a direct TikTok video URL."
            )
        if len(path_parts) >= 2 and path_parts[0].startswith("@") and path_parts[1] == "photo":
            return "TikTok photo posts are not supported. Paste a TikTok video URL."
        return "This TikTok URL type is not supported. Paste a public TikTok video URL."
    return "This URL is not from a supported platform or media type."


def user_facing_media_error(url: str, error: Exception) -> str:
    if isinstance(error, UnsupportedUrlError):
        return unsupported_url_message(url)

    message = str(error).strip() or error.__class__.__name__
    lowered = message.lower()
    provider = provider_from_url(url)
    provider_label = PROVIDER_LABELS.get(provider, "This platform")
    if any(marker in lowered for marker in ("login required", "need to log in", "cookies for the authentication")):
        return f"{provider_label} requires a logged-in session for this media. Private and login-gated media are not supported."
    if "ip address is blocked" in lowered:
        return f"{provider_label} blocked this network's request. Try again later or from a different network."
    if "unsupported url" in lowered:
        return unsupported_url_message(url)
    return message


def _host_matches(host: str, *supported_hosts: str) -> bool:
    return any(host == supported or host.endswith(f".{supported}") for supported in supported_hosts)
