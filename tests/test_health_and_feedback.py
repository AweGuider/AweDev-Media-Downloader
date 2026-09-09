import unittest

from media_downloader import Provider, UnsupportedUrlError
from media_downloader.health import assess_mode_health, provider_health
from media_downloader.url_feedback import (
    provider_from_url,
    unsupported_url_message,
    user_facing_media_error,
)


def healthy_diagnostics():
    labels = (
        "YouTube adapter",
        "Instagram adapter",
        "Facebook adapter",
        "TikTok adapter",
        "yt-dlp",
        "yt-dlp-ejs",
        "Instaloader",
        "curl-cffi",
        "JS runtime",
        "ffmpeg",
        "ffprobe",
        "YouTube network",
    )
    return [{"status": "pass", "label": label, "detail": "available"} for label in labels]


class HealthTests(unittest.TestCase):
    def test_healthy_diagnostics_make_every_provider_ready(self):
        mode_health = assess_mode_health(healthy_diagnostics())
        self.assertTrue(all(mode.status == "pass" for mode in mode_health))
        for provider in Provider:
            with self.subTest(provider=provider):
                self.assertEqual(provider_health(provider, mode_health), "pass")

    def test_instaloader_failure_makes_instagram_partially_available(self):
        diagnostics = healthy_diagnostics()
        diagnostics = [
            {**result, "status": "fail", "detail": "missing"}
            if result["label"] == "Instaloader"
            else result
            for result in diagnostics
        ]
        mode_health = assess_mode_health(diagnostics)
        instagram_modes = {
            mode.definition.key: mode.status
            for mode in mode_health
            if mode.definition.provider == Provider.INSTAGRAM
        }
        self.assertEqual(instagram_modes["instagram_reels"], "pass")
        self.assertEqual(instagram_modes["instagram_posts"], "fail")
        self.assertEqual(provider_health(Provider.INSTAGRAM, mode_health), "warn")

    def test_missing_ffmpeg_marks_video_modes_limited_not_unavailable(self):
        diagnostics = healthy_diagnostics()
        diagnostics = [
            {**result, "status": "fail", "detail": "missing"}
            if result["label"] == "ffmpeg"
            else result
            for result in diagnostics
        ]
        mode_health = assess_mode_health(diagnostics)
        self.assertEqual(provider_health(Provider.YOUTUBE, mode_health), "warn")
        instagram_modes = {mode.definition.key: mode.status for mode in mode_health}
        self.assertEqual(instagram_modes["instagram_posts"], "pass")


class UrlFeedbackTests(unittest.TestCase):
    def test_known_provider_is_inferred_from_short_urls(self):
        self.assertEqual(provider_from_url("https://vm.tiktok.com/example/"), Provider.TIKTOK)
        self.assertEqual(provider_from_url("https://www.tt.site/t/example/"), Provider.TIKTOK)
        self.assertIsNone(provider_from_url("https://example.com/video/123"))

    def test_instagram_story_explains_authentication_boundary(self):
        url = "https://www.instagram.com/stories/creator/123456789"
        message = user_facing_media_error(url, UnsupportedUrlError("unsupported"))
        self.assertIn("require a logged-in session", message)
        self.assertIn("not supported", message)

    def test_tt_site_link_is_not_treated_as_downloadable_media(self):
        message = unsupported_url_message("https://www.tt.site/t/expired/")
        self.assertIn("unsupported or expired", message)
        self.assertIn("vm.tiktok.com", message)

    def test_unsupported_post_types_name_the_supported_alternative(self):
        facebook_message = unsupported_url_message("https://www.facebook.com/creator/posts/123")
        tiktok_message = unsupported_url_message("https://www.tiktok.com/@creator/photo/123")
        self.assertIn("public video or Reel", facebook_message)
        self.assertIn("photo posts are not supported", tiktok_message)

    def test_login_errors_are_rewritten_without_extractor_internals(self):
        message = user_facing_media_error(
            "https://www.facebook.com/reel/123",
            ValueError("You need to log in and provide cookies for the authentication"),
        )
        self.assertEqual(
            message,
            "Facebook requires a logged-in session for this media. Private and login-gated media are not supported.",
        )


if __name__ == "__main__":
    unittest.main()
