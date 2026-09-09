import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from media_downloader import AdapterRegistry, MediaBundle, MediaType, Provider, UnsupportedUrlError
from media_downloader.adapters.facebook import FacebookAdapter
from media_downloader.adapters.ytdlp_video import YtDlpVideoAdapter
from media_downloader.adapters.instagram import InstagramAdapter
from media_downloader.adapters.tiktok import TikTokAdapter
from media_downloader.files import sanitize_filename, unique_destination_path


class OptionsFactory:
    def __call__(self, overrides=None):
        return dict(overrides or {})


class FakeInstagramLoader:
    def __init__(self):
        self.context = object()
        self.downloaded_urls = []

    def download_pic(self, filename, url, _mtime):
        self.downloaded_urls.append(url)
        suffix = ".mp4" if url.endswith(".mp4") else ".jpg"
        Path(f"{filename}{suffix}").write_bytes(b"test media")


class MediaCoreTests(unittest.TestCase):
    def setUp(self):
        self.youtube = YtDlpVideoAdapter(
            Provider.YOUTUBE,
            ("youtube.com", "youtu.be", "youtube-nocookie.com"),
            OptionsFactory(),
            "YouTube",
        )

    def test_adapter_matches_supported_subdomains_only(self):
        self.assertTrue(self.youtube.supports("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(self.youtube.supports("https://youtu.be/abc"))
        self.assertFalse(self.youtube.supports("https://youtube.com.example.org/watch?v=abc"))
        self.assertFalse(self.youtube.supports("not-a-url"))

    def test_registry_resolves_or_rejects_url(self):
        instagram = InstagramAdapter(OptionsFactory())
        registry = AdapterRegistry([self.youtube, instagram])
        self.assertEqual(registry.providers, (Provider.YOUTUBE, Provider.INSTAGRAM))
        self.assertIs(registry.resolve("https://music.youtube.com/watch?v=abc"), self.youtube)
        self.assertIs(registry.resolve("https://www.instagram.com/reel/example/"), instagram)
        self.assertIs(registry.resolve("https://www.instagram.com/p/example/"), instagram)
        with self.assertRaises(UnsupportedUrlError):
            registry.resolve("https://www.instagram.com/stories/example/123/")

    def test_instagram_adapter_claims_reels_and_posts(self):
        instagram = InstagramAdapter(OptionsFactory())
        self.assertTrue(instagram.supports("https://www.instagram.com/reel/ABC123/"))
        self.assertTrue(instagram.supports("https://instagram.com/user/reels/ABC123/?share=1"))
        self.assertTrue(instagram.supports("https://www.instagram.com/p/ABC123/"))
        self.assertFalse(instagram.supports("https://www.instagram.com/reels/audio/123/"))
        self.assertFalse(instagram.supports("https://example.com/reel/ABC123/"))

    def test_instagram_carousel_inspection_and_download(self):
        fake_loader = FakeInstagramLoader()
        fake_post = SimpleNamespace(
            typename="GraphSidecar",
            owner_username="creator",
            date_utc=datetime(2026, 9, 8),
            get_sidecar_nodes=lambda: (
                SimpleNamespace(
                    is_video=False,
                    display_url="https://cdn.example/first.jpg",
                    video_url=None,
                ),
                SimpleNamespace(
                    is_video=True,
                    display_url="https://cdn.example/second.jpg",
                    video_url="https://cdn.example/second.mp4",
                ),
            ),
        )
        instagram = InstagramAdapter(
            OptionsFactory(),
            loader_factory=lambda: fake_loader,
            post_factory=lambda _context, _shortcode: fake_post,
        )

        bundle = instagram.inspect("https://www.instagram.com/p/ABC123/")

        self.assertEqual(bundle.media_type, MediaType.MIXED)
        self.assertEqual(len(bundle.items), 2)
        self.assertEqual(bundle.creator, "creator")
        self.assertEqual(bundle.upload_date, "20260908")
        with tempfile.TemporaryDirectory() as temp_directory:
            result = instagram.download(
                bundle,
                options=SimpleNamespace(
                    output_directory=Path(temp_directory),
                    audio_only=False,
                    preserve_upload_date=False,
                    cleanup_enabled=True,
                ),
                cancel_event=threading.Event(),
            )
            self.assertEqual([path.suffix for path in result.files], [".jpg", ".mp4"])
            self.assertTrue(all(path.exists() for path in result.files))

        self.assertEqual(
            fake_loader.downloaded_urls,
            ["https://cdn.example/first.jpg", "https://cdn.example/second.mp4"],
        )

    def test_duplicate_provider_registration_is_rejected(self):
        registry = AdapterRegistry([self.youtube])
        with self.assertRaises(ValueError):
            registry.register(self.youtube)

    def test_facebook_adapter_claims_only_known_video_urls(self):
        facebook = FacebookAdapter(OptionsFactory())
        supported_urls = (
            "https://www.facebook.com/reel/123456789/",
            "https://www.facebook.com/watch/?v=123456789",
            "https://www.facebook.com/creator/videos/123456789/",
            "https://www.facebook.com/share/v/abc123/",
            "https://fb.watch/abc123/",
        )
        for url in supported_urls:
            with self.subTest(url=url):
                self.assertTrue(facebook.supports(url))

        unsupported_urls = (
            "https://www.facebook.com/creator/posts/123456789/",
            "https://www.facebook.com/photo/?fbid=123456789",
            "https://example.com/reel/123456789/",
        )
        for url in unsupported_urls:
            with self.subTest(url=url):
                self.assertFalse(facebook.supports(url))

    def test_tiktok_adapter_claims_only_video_urls(self):
        tiktok = TikTokAdapter(OptionsFactory())
        supported_urls = (
            "https://www.tiktok.com/@creator/video/123456789",
            "https://vm.tiktok.com/ZMexample/",
            "https://vt.tiktok.com/ZSexample/",
            "https://www.tiktok.com/t/ZMexample/",
            "https://www.tiktok.com/embed/123456789",
            "https://www.tiktok.com/share/video/123456789",
            "https://www.tiktokv.com/share/video/123456789/",
        )
        for url in supported_urls:
            with self.subTest(url=url):
                self.assertTrue(tiktok.supports(url))

        unsupported_urls = (
            "https://www.tiktok.com/@creator/photo/123456789",
            "https://www.tiktok.com/@creator",
            "https://example.com/@creator/video/123456789",
        )
        for url in unsupported_urls:
            with self.subTest(url=url):
                self.assertFalse(tiktok.supports(url))

    def test_tiktok_adapter_normalizes_ytdlp_metadata(self):
        class FakeYoutubeDL:
            def __init__(self, _options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def extract_info(self, _url, download=False):
                if download:
                    raise AssertionError("Metadata inspection unexpectedly downloaded media")
                return {
                    "id": "123456789",
                    "title": "Test TikTok",
                    "uploader": "creator",
                    "upload_date": "20260909",
                    "duration": 12,
                    "formats": [{"height": 720}],
                }

        tiktok = TikTokAdapter(OptionsFactory())
        with patch("media_downloader.adapters.ytdlp_video.yt_dlp.YoutubeDL", FakeYoutubeDL):
            bundle = tiktok.inspect("https://www.tiktok.com/@creator/video/123456789")

        self.assertEqual(bundle.provider, Provider.TIKTOK)
        self.assertEqual(bundle.title, "Test TikTok")
        self.assertEqual(bundle.creator, "creator")
        self.assertEqual(bundle.items[0].resolutions, ("720p",))
        self.assertTrue(bundle.capabilities.audio_extraction)

    def test_media_bundle_type_defaults_to_video(self):
        bundle = MediaBundle(provider=Provider.YOUTUBE, source_url="https://youtu.be/a", title="A")
        self.assertEqual(bundle.media_type, MediaType.VIDEO)

    def test_windows_filename_sanitization_and_unique_destination(self):
        self.assertEqual(sanitize_filename('A <video>: "test".'), "A _video__ _test_")
        with tempfile.TemporaryDirectory() as temp_directory:
            directory = Path(temp_directory)
            (directory / "video.mp4").touch()
            self.assertEqual(unique_destination_path(directory, "video.mp4").name, "video (1).mp4")


if __name__ == "__main__":
    unittest.main()
