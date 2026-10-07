import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from media_downloader.transcript_text import parse_subtitle_text, render_transcript, transcript_path, write_transcript


PROTOCOL_VERSION = 1
COMPONENT_VERSION = "1.0.0"
MODEL_NAME = "ggml-base-q5_1.bin"
VAD_MODEL_NAME = "ggml-silero-v6.2.0.bin"
MEDIA_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".opus", ".wav", ".webm",
}


def component_directory() -> Path:
    configured = os.environ.get("AWEDEV_TRANSCRIPTION_COMPONENT_DIR")
    if configured:
        return Path(configured)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def required_paths() -> tuple[Path, Path, Path]:
    root = component_directory()
    cli_name = "whisper-cli.exe" if os.name == "nt" else "whisper-cli"
    return root / cli_name, root / MODEL_NAME, root / VAD_MODEL_NAME


def ffmpeg_path() -> str:
    resolved = shutil.which("ffmpeg")
    if not resolved:
        raise RuntimeError("ffmpeg is required for transcription")
    return resolved


def run_checked(command, failure_message: str):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or failure_message).strip())
    return result


def transcribe_media(media_path: Path) -> Path | None:
    whisper_cli, model_path, vad_model_path = required_paths()
    with tempfile.TemporaryDirectory(prefix="awedev-transcription-") as temp_directory:
        temp_root = Path(temp_directory)
        wav_path = temp_root / "audio.wav"
        output_base = temp_root / "transcript"
        run_checked(
            [
                ffmpeg_path(),
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(media_path),
                "-vn",
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                str(wav_path),
            ],
            "ffmpeg could not extract audio for transcription",
        )
        run_checked(
            [
                str(whisper_cli),
                "-m", str(model_path),
                "-f", str(wav_path),
                "-l", "auto",
                "--vad",
                "-vm", str(vad_model_path),
                "-osrt",
                "-of", str(output_base),
                "-np",
            ],
            "whisper.cpp could not transcribe the media",
        )
        subtitle_path = output_base.with_suffix(".srt")
        if not subtitle_path.is_file():
            raise RuntimeError("whisper.cpp did not create transcript output")
        entries = parse_subtitle_text(subtitle_path.read_text(encoding="utf-8-sig", errors="replace"))
        return write_transcript(transcript_path(media_path), render_transcript(entries))


def process_request(request: dict) -> dict:
    if request.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("Unsupported transcription protocol version")
    outputs = []
    warnings = []
    for path in request.get("files") or []:
        media_path = Path(path)
        if not media_path.is_file() or media_path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        try:
            output = transcribe_media(media_path)
            if output:
                outputs.append(str(output))
            else:
                warnings.append(f"{media_path.name}: no speech detected")
        except Exception as error:
            warnings.append(f"{media_path.name}: {error}")
    return {"ok": True, "outputs": outputs, "warnings": warnings}


def self_test() -> int:
    try:
        whisper_cli, model_path, vad_model_path = required_paths()
        missing = [str(path.name) for path in (whisper_cli, model_path, vad_model_path) if not path.is_file()]
        if missing:
            raise RuntimeError(f"Missing transcription component file(s): {', '.join(missing)}")
        ffmpeg_path()
        result = subprocess.run(
            [str(whisper_cli), "--help"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError("whisper-cli self-test failed")
        print(json.dumps({
            "ok": True,
            "component_version": COMPONENT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
        }))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


def run_request(request_path: Path) -> int:
    response_path = None
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        response_path = Path(request["response_path"])
        response = process_request(request)
    except Exception as error:
        response = {"ok": False, "error": str(error)}
    if response_path is not None:
        response_path.write_text(json.dumps(response), encoding="utf-8")
    if response.get("ok"):
        return 0
    print(response["error"], file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.request:
        return run_request(args.request)
    parser.error("either --self-test or --request is required")


if __name__ == "__main__":
    raise SystemExit(main())
