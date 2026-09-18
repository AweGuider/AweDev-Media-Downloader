import hashlib
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from media_downloader.ocr_component import (
    OcrComponentCancelled,
    OcrComponentError,
    OcrComponentManager,
    OcrComponentManifest,
)
from media_downloader.ocr_postprocess import extract_visible_text
from ocr_worker import format_timestamp, materially_different, normalize_lines, sidecar_path


def component_archive(version="1.0.0", unsafe_name=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "component.json",
            json.dumps({
                "component": "awedev-ocr",
                "version": version,
                "protocol_version": 1,
            }),
        )
        archive.writestr("AweDevMediaOCR.exe", b"worker")
        if unsafe_name:
            archive.writestr(unsafe_name, b"unsafe")
    return stream.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class OcrComponentTests(unittest.TestCase):
    def manifest(self, payload):
        return OcrComponentManifest(
            available=True,
            version="1.0.0",
            protocol_version=1,
            url=(
                "https://github.com/AweGuider/AweDev-Media-Downloader/"
                "releases/download/ocr-v1.0.0/AweDevMediaOCR-windows-x64-1.0.0.zip"
            ),
            sha256=hashlib.sha256(payload).hexdigest(),
            worker="AweDevMediaOCR.exe",
            download_size=len(payload),
            installed_size=12,
        )

    def test_verified_component_is_installed_only_after_self_test(self):
        payload = component_archive()
        with tempfile.TemporaryDirectory() as temp_directory:
            old_directory = Path(temp_directory) / "0.9.0"
            old_directory.mkdir()
            (old_directory / "component.json").write_text(
                json.dumps({"component": "awedev-ocr", "version": "0.9.0"}),
                encoding="utf-8",
            )
            manager = OcrComponentManager(
                self.manifest(payload),
                Path(temp_directory),
                runner=lambda _command: SimpleNamespace(returncode=0, stdout="", stderr=""),
            )
            progress = []
            manager.install(
                progress=lambda downloaded, total: progress.append((downloaded, total)),
                opener=lambda _request, timeout: FakeResponse(payload),
            )

            self.assertTrue(manager.is_installed())
            self.assertTrue(manager.worker_path.is_file())
            self.assertFalse(old_directory.exists())
            self.assertEqual(progress[-1], (len(payload), len(payload)))

    def test_checksum_failure_leaves_component_uninstalled(self):
        payload = component_archive()
        corrupt_payload = payload + b"corrupt"
        with tempfile.TemporaryDirectory() as temp_directory:
            manager = OcrComponentManager(
                self.manifest(payload),
                Path(temp_directory),
                runner=lambda _command: SimpleNamespace(returncode=0, stdout="", stderr=""),
            )
            with self.assertRaisesRegex(OcrComponentError, "verification failed"):
                manager.install(opener=lambda _request, timeout: FakeResponse(corrupt_payload))
            self.assertFalse(manager.is_installed())

    def test_unsafe_zip_path_is_rejected(self):
        payload = component_archive(unsafe_name="../outside.txt")
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            manager = OcrComponentManager(
                self.manifest(payload),
                root / "components",
                runner=lambda _command: SimpleNamespace(returncode=0, stdout="", stderr=""),
            )
            with self.assertRaisesRegex(OcrComponentError, "unsafe path"):
                manager.install(opener=lambda _request, timeout: FakeResponse(payload))
            self.assertFalse((root / "outside.txt").exists())

    def test_cancelled_download_is_not_installed(self):
        payload = component_archive()
        cancel_event = threading.Event()
        cancel_event.set()
        with tempfile.TemporaryDirectory() as temp_directory:
            manager = OcrComponentManager(
                self.manifest(payload),
                Path(temp_directory),
                runner=lambda _command: SimpleNamespace(returncode=0, stdout="", stderr=""),
            )
            with self.assertRaises(OcrComponentCancelled):
                manager.install(
                    cancel_event=cancel_event,
                    opener=lambda _request, timeout: FakeResponse(payload),
                )
            self.assertFalse(manager.is_installed())

    def test_postprocessor_sends_only_supported_media(self):
        class FakeComponent:
            def run_request(self, request, cancel_event=None):
                self.request = request
                return {"ok": True, "outputs": [request["files"][0] + ".ocr.txt"]}

        component = FakeComponent()
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            image = root / "image.jpg"
            description = root / "image.txt"
            image.touch()
            description.touch()
            outputs = extract_visible_text(component, (image, description))

        self.assertEqual(component.request["files"], [str(image.resolve())])
        self.assertEqual(component.request["sample_fps"], 1.0)
        self.assertEqual(component.request["max_frames"], 300)
        self.assertEqual(len(outputs), 1)


class OcrWorkerHelperTests(unittest.TestCase):
    def test_text_normalization_and_deduplication(self):
        self.assertEqual(normalize_lines(("  hello   world ", "", "next")), ("hello world", "next"))
        self.assertFalse(materially_different("Sale now", "sale now"))
        self.assertTrue(materially_different("Sale now", "Different caption"))

    def test_timestamp_and_sidecar_names(self):
        self.assertEqual(format_timestamp(3661.9), "01:01:01")
        self.assertEqual(sidecar_path(Path("clip.mp4")), Path("clip.ocr.txt"))


if __name__ == "__main__":
    unittest.main()
