from dataclasses import dataclass

from .models import Provider


@dataclass(frozen=True)
class ModeDefinition:
    key: str
    provider: Provider
    label: str
    required_checks: tuple[str, ...]
    partial_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModeHealth:
    definition: ModeDefinition
    status: str
    detail: str


MODE_DEFINITIONS = (
    ModeDefinition(
        "youtube_video_audio",
        Provider.YOUTUBE,
        "Videos and audio",
        ("YouTube adapter", "yt-dlp"),
        ("yt-dlp-ejs", "JS runtime", "ffmpeg", "ffprobe", "YouTube network"),
    ),
    ModeDefinition(
        "instagram_reels",
        Provider.INSTAGRAM,
        "Reels",
        ("Instagram adapter", "yt-dlp"),
        ("ffmpeg", "ffprobe"),
    ),
    ModeDefinition(
        "instagram_posts",
        Provider.INSTAGRAM,
        "Posts and carousels",
        ("Instagram adapter", "Instaloader"),
    ),
    ModeDefinition(
        "facebook_videos",
        Provider.FACEBOOK,
        "Videos and Reels",
        ("Facebook adapter", "yt-dlp"),
        ("ffmpeg", "ffprobe"),
    ),
    ModeDefinition(
        "tiktok_videos",
        Provider.TIKTOK,
        "Videos",
        ("TikTok adapter", "yt-dlp", "curl-cffi"),
        ("ffmpeg", "ffprobe"),
    ),
)

UNSUPPORTED_MODES = (
    (Provider.INSTAGRAM, "Stories", "Requires login; not supported"),
    (Provider.FACEBOOK, "Posts and photos", "Not supported"),
    (Provider.TIKTOK, "Photo posts", "Not supported"),
)

PROVIDER_LABELS = {
    Provider.YOUTUBE: "YouTube",
    Provider.INSTAGRAM: "Instagram",
    Provider.FACEBOOK: "Facebook",
    Provider.TIKTOK: "TikTok",
}

PROVIDER_SUMMARIES = {
    Provider.YOUTUBE: "Video + audio",
    Provider.INSTAGRAM: "Reels + posts",
    Provider.FACEBOOK: "Videos + Reels",
    Provider.TIKTOK: "Videos",
}


def assess_mode_health(diagnostics) -> tuple[ModeHealth, ...]:
    checks = {result["label"]: result for result in diagnostics}
    results = []
    for definition in MODE_DEFINITIONS:
        unavailable = _check_issues(definition.required_checks, checks, failure_only=True)
        if unavailable:
            results.append(ModeHealth(definition, "fail", "; ".join(unavailable)))
            continue

        limitations = _check_issues(definition.required_checks, checks)
        limitations.extend(_check_issues(definition.partial_checks, checks))
        if limitations:
            results.append(ModeHealth(definition, "warn", "; ".join(limitations)))
        else:
            results.append(ModeHealth(definition, "pass", "Ready"))
    return tuple(results)


def provider_health(provider: Provider, mode_health) -> str:
    statuses = [mode.status for mode in mode_health if mode.definition.provider == provider]
    if not statuses or all(status == "fail" for status in statuses):
        return "fail"
    if any(status != "pass" for status in statuses):
        return "warn"
    return "pass"


def _check_issues(check_names, checks, failure_only=False):
    issues = []
    for check_name in check_names:
        result = checks.get(check_name)
        if not result:
            issues.append(f"{check_name}: check unavailable")
        elif result["status"] == "fail" or (not failure_only and result["status"] == "warn"):
            issues.append(f"{check_name}: {result['detail']}")
    return issues
