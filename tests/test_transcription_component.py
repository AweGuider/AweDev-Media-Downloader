import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from media_downloader.transcript_text import parse_subtitle_text, render_transcript, transcript_path
from media_downloader.transcription_component import (
    TranscriptionComponentCancelled,
    TranscriptionComponentError,
    TranscriptionComponentManager,
    TranscriptionComponentManifest,
)
from media_downloader.transcription_postprocess import create_transcripts


def component_archive(version="1.0.0", unsafe_name=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "component.json",
            json.dumps({
                "component": "awedev-transcription",
                "version": version,
                "protocol_version": 1,
            }),
        )
        archive.writestr("AweDevMediaTranscription.exe", b"worker")
        if unsafe_name:
            archive.writestr(unsafe_name, b"unsafe")
    return buffer.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class TranscriptionComponentTests(unittest.TestCase):
    def manifest(self, payload):
        return TranscriptionComponentManifest(
            available=True,
            version="1.0.0",
            protocol_version=1,
            url=(
                "https://github.com/AweGuider/AweDev-Media-Downloader/"
                "releases/download/transcription-v1.0.0/AweDevMediaTranscription-windows-x64-1.0.0.zip"
            ),
            sha256=hashlib.sha256(payload).hexdigest(),
            worker="AweDevMediaTranscription.exe",
            download_size=len(payload),
        )

    def test_verified_component_installs_after_self_test(self):
        payload = component_archive()
        with tempfile.TemporaryDirectory() as temp_directory:
            manager = TranscriptionComponentManager(
                self.manifest(payload),
                Path(temp_directory) / "components",
                runner=lambda _command: SimpleNamespace(returncode=0, stdout="", stderr=""),
            )
            manager.install(opener=lambda _request, timeout: FakeResponse(payload))
            self.assertTrue(manager.is_installed())

    def test_cancelled_install_leaves_component_uninstalled(self):
        payload = component_archive()
        cancel_event = SimpleNamespace(is_set=lambda: True)
        with tempfile.TemporaryDirectory() as temp_directory:
            manager = TranscriptionComponentManager(
                self.manifest(payload),
                Path(temp_directory) / "components",
                runner=lambda _command: SimpleNamespace(returncode=0, stdout="", stderr=""),
            )
            with self.assertRaises(TranscriptionComponentCancelled):
                manager.install(
                    cancel_event=cancel_event,
                    opener=lambda _request, timeout: FakeResponse(payload),
                )
            self.assertFalse(manager.is_installed())

    def test_unsafe_zip_path_is_rejected(self):
        payload = component_archive(unsafe_name="../outside.txt")
        with tempfile.TemporaryDirectory() as temp_directory:
            manager = TranscriptionComponentManager(
                self.manifest(payload),
                Path(temp_directory) / "components",
                runner=lambda _command: SimpleNamespace(returncode=0, stdout="", stderr=""),
            )
            with self.assertRaises(TranscriptionComponentError):
                manager.install(opener=lambda _request, timeout: FakeResponse(payload))
            self.assertFalse((Path(temp_directory) / "outside.txt").exists())

    def test_postprocessor_prefers_source_subtitles_and_falls_back_locally(self):
        class FakeComponent:
            def run_request(self, request, cancel_event=None):
                self.request = request
                output = transcript_path(Path(request["files"][0]))
                output.write_text("[00:00:00] local\n", encoding="utf-8")
                return {"ok": True, "outputs": [str(output)], "warnings": []}

        component = FakeComponent()
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            captioned = root / "captioned.mp4"
            local = root / "local.mp3"
            subtitles = root / "captioned.en.srt"
            captioned.touch()
            local.touch()
            subtitles.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nHello world\n",
                encoding="utf-8",
            )
            result = create_transcripts(component, (captioned, local), (subtitles,))

            self.assertEqual(component.request["files"], [str(local.resolve())])
            self.assertEqual(
                {path.name for path in result.outputs},
                {"captioned.transcript.txt", "local.transcript.txt"},
            )
            self.assertEqual(result.consumed_sources, (subtitles.resolve(),))
            self.assertEqual(
                (root / "captioned.transcript.txt").read_text(encoding="utf-8"),
                "[00:00:01] Hello world\n",
            )


class TranscriptTextTests(unittest.TestCase):
    def test_srt_and_vtt_cues_are_normalized(self):
        entries = parse_subtitle_text(
            "WEBVTT\n\n00:00:02.500 --> 00:00:04.000\n<c.green>Hello &amp; welcome</c>\n\n"
        )
        self.assertEqual(entries, ((2.5, "Hello & welcome"),))
        self.assertEqual(render_transcript(entries), "[00:00:02] Hello & welcome")

    def test_transcript_sidecar_name_replaces_media_suffix(self):
        self.assertEqual(transcript_path(Path("clip.mp4")), Path("clip.transcript.txt"))


if __name__ == "__main__":
    unittest.main()
