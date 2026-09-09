import tempfile
import unittest
from pathlib import Path

from media_downloader import AdapterRegistry, MediaBundle, MediaType, Provider, UnsupportedUrlError
from media_downloader.adapters.ytdlp_video import YtDlpVideoAdapter
from media_downloader.files import sanitize_filename, unique_destination_path


class OptionsFactory:
    def __call__(self, overrides=None):
        return dict(overrides or {})


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
        registry = AdapterRegistry([self.youtube])
        self.assertIs(registry.resolve("https://music.youtube.com/watch?v=abc"), self.youtube)
        with self.assertRaises(UnsupportedUrlError):
            registry.resolve("https://www.instagram.com/reel/example/")

    def test_duplicate_provider_registration_is_rejected(self):
        registry = AdapterRegistry([self.youtube])
        with self.assertRaises(ValueError):
            registry.register(self.youtube)

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
