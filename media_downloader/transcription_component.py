import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


TRANSCRIPTION_PROTOCOL_VERSION = 1
TRANSCRIPTION_COMPONENT_NAME = "awedev-transcription"


class TranscriptionComponentError(RuntimeError):
    pass


class TranscriptionComponentCancelled(TranscriptionComponentError):
    pass


@dataclass(frozen=True)
class TranscriptionComponentManifest:
    available: bool = False
    version: str = ""
    protocol_version: int = TRANSCRIPTION_PROTOCOL_VERSION
    url: str = ""
    sha256: str = ""
    worker: str = "AweDevMediaTranscription.exe"
    download_size: int = 0
    installed_size: int = 0

    @classmethod
    def load(cls, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict) or not data.get("available"):
            return cls()
        try:
            manifest = cls(
                available=True,
                version=str(data.get("version") or ""),
                protocol_version=int(data.get("protocol_version") or 0),
                url=str(data.get("url") or ""),
                sha256=str(data.get("sha256") or "").lower(),
                worker=str(data.get("worker") or "AweDevMediaTranscription.exe"),
                download_size=int(data.get("download_size") or 0),
                installed_size=int(data.get("installed_size") or 0),
            )
            manifest.validate()
            return manifest
        except (TypeError, ValueError, TranscriptionComponentError):
            return cls()

    def validate(self):
        if not self.available:
            raise TranscriptionComponentError("The transcription component is not available for this app build.")
        if not self.version or self.protocol_version != TRANSCRIPTION_PROTOCOL_VERSION:
            raise TranscriptionComponentError("The transcription component manifest is incompatible with this app.")
        if len(self.sha256) != 64 or any(character not in "0123456789abcdef" for character in self.sha256):
            raise TranscriptionComponentError("The transcription component manifest has an invalid SHA-256 digest.")
        parsed = urlparse(self.url)
        expected_prefix = "/AweGuider/AweDev-Media-Downloader/releases/download/"
        if parsed.scheme != "https" or parsed.hostname != "github.com" or not parsed.path.startswith(expected_prefix):
            raise TranscriptionComponentError("The transcription component URL is not an approved project release asset.")
        worker_path = Path(self.worker)
        if worker_path.is_absolute() or ".." in worker_path.parts:
            raise TranscriptionComponentError("The transcription component worker path is invalid.")


def default_component_root(app_id: str) -> Path:
    local_root = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(local_root) / app_id / "components" / "transcription"


def _format_megabytes(byte_count: int) -> str:
    if byte_count <= 0:
        return "unknown"
    return f"{byte_count / (1024 * 1024):.1f} MB"


class TranscriptionComponentManager:
    def __init__(self, manifest: TranscriptionComponentManifest, component_root: Path, runner=None):
        self.manifest = manifest
        self.component_root = Path(component_root)
        self._runner = runner or self._run_worker

    @classmethod
    def from_manifest_path(cls, path: Path, app_id: str, component_root: Path | None = None):
        return cls(
            TranscriptionComponentManifest.load(Path(path)),
            component_root or default_component_root(app_id),
        )

    @property
    def install_directory(self) -> Path:
        return self.component_root / self.manifest.version

    @property
    def worker_path(self) -> Path:
        return self.install_directory / self.manifest.worker

    def is_installed(self) -> bool:
        if not self.manifest.available:
            return False
        metadata_path = self.install_directory / "component.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            metadata.get("component") == TRANSCRIPTION_COMPONENT_NAME
            and metadata.get("version") == self.manifest.version
            and metadata.get("protocol_version") == TRANSCRIPTION_PROTOCOL_VERSION
            and self.worker_path.is_file()
        )

    def status_text(self) -> str:
        if self.is_installed():
            return f"Transcription component {self.manifest.version} installed"
        if self.manifest.available:
            return "Transcription component not installed"
        return "Transcription component unavailable in this build"

    def size_summary(self) -> str:
        return (
            f"Download: {_format_megabytes(self.manifest.download_size)}\n"
            f"Installed size: {_format_megabytes(self.manifest.installed_size)}"
        )

    def self_test(self):
        if not self.is_installed():
            raise TranscriptionComponentError("The transcription component is not installed.")
        result = self._runner([str(self.worker_path), "--self-test"])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Self-test failed").strip()
            raise TranscriptionComponentError(detail)

    def install(self, progress=None, cancel_event=None, opener=None):
        self.manifest.validate()
        progress = progress or (lambda _downloaded, _total: None)
        opener = opener or urllib.request.urlopen
        self.component_root.mkdir(parents=True, exist_ok=True)
        work_directory = Path(tempfile.mkdtemp(prefix="install-", dir=self.component_root))
        archive_path = work_directory / "component.zip"
        extract_directory = work_directory / "extracted"
        try:
            request = urllib.request.Request(
                self.manifest.url,
                headers={"User-Agent": "AweDev-Media-Downloader"},
            )
            digest = hashlib.sha256()
            with opener(request, timeout=30) as response, archive_path.open("wb") as archive:
                response_size = int(response.headers.get("Content-Length") or 0)
                total_size = response_size or self.manifest.download_size
                downloaded = 0
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise TranscriptionComponentCancelled("Transcription component installation cancelled.")
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    archive.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    progress(downloaded, total_size)
            if digest.hexdigest() != self.manifest.sha256:
                raise TranscriptionComponentError(
                    "Transcription component verification failed. The downloaded file was not installed."
                )
            extract_directory.mkdir()
            self._safe_extract(archive_path, extract_directory)
            self._validate_extracted_component(extract_directory)
            result = self._runner([str(extract_directory / self.manifest.worker), "--self-test"])
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "Self-test failed").strip()
                raise TranscriptionComponentError(f"Transcription component self-test failed: {detail}")
            final_directory = self.install_directory
            backup_directory = work_directory / "previous"
            if final_directory.exists():
                final_directory.replace(backup_directory)
            try:
                extract_directory.replace(final_directory)
            except Exception:
                if backup_directory.exists() and not final_directory.exists():
                    backup_directory.replace(final_directory)
                raise
            self._remove_previous_versions(final_directory, work_directory)
            return self.worker_path
        finally:
            shutil.rmtree(work_directory, ignore_errors=True)

    def remove(self):
        if self.component_root.exists():
            shutil.rmtree(self.component_root)

    def run_request(self, request_data: dict, cancel_event=None):
        if not self.is_installed():
            raise TranscriptionComponentError("The transcription component is not installed.")
        if cancel_event is not None and cancel_event.is_set():
            raise TranscriptionComponentCancelled("Download cancelled")
        with tempfile.TemporaryDirectory(prefix="awedev-transcription-request-") as temp_directory:
            request_path = Path(temp_directory) / "request.json"
            response_path = Path(temp_directory) / "response.json"
            payload = {
                **request_data,
                "protocol_version": TRANSCRIPTION_PROTOCOL_VERSION,
                "response_path": str(response_path),
            }
            request_path.write_text(json.dumps(payload), encoding="utf-8")
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt":
                creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            process = subprocess.Popen(
                [str(self.worker_path), "--request", str(request_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
            )
            while process.poll() is None:
                if cancel_event is not None and cancel_event.wait(0.1):
                    self._terminate_process_tree(process)
                    raise TranscriptionComponentCancelled("Transcription cancelled")
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise TranscriptionComponentError((stderr or stdout or "Transcription failed").strip())
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise TranscriptionComponentError("The transcription component returned an invalid response.") from error
            if not response.get("ok"):
                raise TranscriptionComponentError(str(response.get("error") or "Transcription failed"))
            return response

    @staticmethod
    def _run_worker(command):
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    @staticmethod
    def _terminate_process_tree(process):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()

    @staticmethod
    def _safe_extract(archive_path: Path, destination: Path):
        destination_root = destination.resolve()
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    member_path = Path(member.filename)
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise TranscriptionComponentError(
                            "The transcription component archive contains an unsafe symbolic link."
                        )
                    target = (destination / member_path).resolve()
                    if destination_root != target and destination_root not in target.parents:
                        raise TranscriptionComponentError(
                            "The transcription component archive contains an unsafe path."
                        )
                archive.extractall(destination)
        except zipfile.BadZipFile as error:
            raise TranscriptionComponentError(
                "The transcription component download is not a valid ZIP archive."
            ) from error

    def _validate_extracted_component(self, directory: Path):
        metadata_path = directory / "component.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise TranscriptionComponentError(
                "The transcription component metadata is missing or invalid."
            ) from error
        if (
            metadata.get("component") != TRANSCRIPTION_COMPONENT_NAME
            or metadata.get("version") != self.manifest.version
            or metadata.get("protocol_version") != TRANSCRIPTION_PROTOCOL_VERSION
        ):
            raise TranscriptionComponentError("The downloaded transcription component is incompatible with this app.")
        if not (directory / self.manifest.worker).is_file():
            raise TranscriptionComponentError("The downloaded transcription component worker is missing.")

    def _remove_previous_versions(self, current_directory: Path, work_directory: Path):
        for candidate in self.component_root.iterdir():
            if candidate in {current_directory, work_directory} or not candidate.is_dir():
                continue
            try:
                metadata = json.loads((candidate / "component.json").read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if metadata.get("component") == TRANSCRIPTION_COMPONENT_NAME:
                shutil.rmtree(candidate, ignore_errors=True)
