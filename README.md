# AweDev Media Downloader

[AweDev Media Downloader](https://github.com/AweGuider/AweDev-Media-Downloader) is a small Windows-first desktop downloader for saving media from supported social platforms. It wraps provider adapters in a Tkinter GUI, uses `yt-dlp` for video extraction, bundles runtime helpers for release builds, and shows startup diagnostics so users can see whether downloader dependencies are healthy.

## Features

- Download one public YouTube, Instagram Reel, Facebook video, or TikTok video URL at a time as MP4.
- Download every image and video from a public Instagram post or carousel.
- Optionally keep every item from a multi-item post together in one folder.
- Save the original post caption or description as a UTF-8 text file when it is available.
- Download audio-only files as MP3, WAV, AAC, or FLAC.
- Preview the checked media's thumbnail, title, creator, contents, and upload date before downloading.
- See color-coded platform readiness and supported media immediately at startup.
- Choose best available quality or a quality at or below the selected resolution.
- Save repeated downloads with unique filenames.
- Show dependency diagnostics for `yt-dlp`, `yt-dlp-ejs`, Instaloader, `curl-cffi`, JavaScript runtime support, `ffmpeg`, `ffprobe`, network access, and old PyInstaller temp folders.
- Save user settings such as output folder, cleanup behavior, timestamp behavior, folder-opening behavior, mode, and format.
- Optionally extract visible text into `.ocr.txt` sidecars through a separately downloaded OCR component.
- Optionally create timestamped `.transcript.txt` sidecars from source subtitles or local speech recognition.
- Open the project, issue tracker, and AweDev links from the in-app information dialog.

## Support AweDev

If this tool saved you time, you can buy a cappuccino to support the road to future releases, dependency updates, and Windows build testing. Support is optional; the app stays free.

[☕ Buy a Cappuccino on Ko-fi](https://ko-fi.com/awedev)

## Supported Platform

The first public release target is Windows. The source may run on other platforms with Python and compatible dependencies, but non-Windows use is not the release target yet.

## Install From Release

1. Download the latest release ZIP or EXE from the [repository Releases page](https://github.com/AweGuider/AweDev-Media-Downloader/releases).
2. Extract the ZIP if needed.
3. Run `AweDevMediaDownloader.exe`.
4. If Windows SmartScreen appears, review the publisher/file details and choose whether to run it.

The release EXE is intended to include the needed Python app package, thumbnail preview support, `ffmpeg`, `ffprobe`, and a JavaScript runtime used by `yt-dlp`.

Visible-text extraction is an optional component and is not bundled into the main EXE. When a release provides a verified OCR component, enabling **Extract visible text from media** offers to download it from this project's GitHub Releases page. The component is stored under `%LOCALAPPDATA%\AweDevMediaDownloader\components\ocr`, and OCR processing stays local. Disabling OCR leaves the component installed; use **Remove component** to reclaim its disk space.

Speech transcription is also an optional component and is not bundled into the main EXE. Enabling **Create speech transcript** offers to download the verified component when one is published. The app prefers source subtitles when available and otherwise runs `whisper.cpp` locally. The component is stored under `%LOCALAPPDATA%\AweDevMediaDownloader\components\transcription`; downloaded media is not uploaded for transcription.

## Run From Source

Requirements:

- Windows
- Python 3.13 or newer
- `ffmpeg` and `ffprobe` available on `PATH`
- Node or Deno available on `PATH`

Install Python dependencies:

```bat
python -m pip install -r requirements.txt
```

Run the app:

```bat
run_downloader.bat
```

Or run directly:

```bat
python downloader.py
```

Version 2 stores settings under `%APPDATA%\AweDevMediaDownloader` and saves downloads to `Downloads\AweDev-Media-Downloads` by default. Settings saved by the former YouTube Downloader identity are not migrated automatically.

## Build A Release EXE

Install build dependencies:

```bat
python -m pip install -r requirements-build.txt
```

Make sure these commands work before building:

```bat
ffmpeg -version
ffprobe -version
node --version
```

Then run:

```bat
build_exe_latest.bat
```

The builder reads `APP_VERSION` from `downloader.py` and uses it in the default EXE and ZIP names. It asks whether to create a ZIP before asking for its name; enter the ZIP name without `.zip`. Existing EXEs default to preserve, while existing ZIP packages default to overwrite.

When ZIP packaging is enabled, the archive contains the EXE, `README.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the matching release notes as `RELEASE_NOTES.md`.

Build output is organized by purpose:

- `build\` contains disposable PyInstaller work files and package staging; successful builders remove their own temporary directories.
- `dist\app\<version>\` and `dist\components\...` contain raw compiled executables for local testing.
- `release\app\<version>\` and `release\components\...` contain ZIP packages and `SHA256SUMS.txt` files ready for GitHub Releases.
- `archive\` preserves superseded, legacy, staging, and test artifacts that no longer belong in active build output.
- `logs\build\` contains timestamped build logs.

All generated build output and the local archive are ignored by Git. Builders use separate app, OCR, and transcription subdirectories so their intermediates cannot overwrite one another.

## Build The Optional OCR Component

Install its separate build dependencies:

```bat
python -m pip install -r requirements-ocr-build.txt
```

Then run:

```bat
build_ocr_component.bat
```

The script builds and self-tests `AweDevMediaOCR.exe`, packages it with its component metadata, and writes its ZIP and checksum under `release\components\ocr\<version>\`. Enter the planned release tag when prompted to generate `assets\ocr-component.json`, upload that exact ZIP to the matching GitHub release, and then build the main application so it embeds the verified manifest. Publish the release as immutable only after every asset is attached.

## Build The Optional Transcription Component

Prepare `transcription-runtime` with:

- the Windows x64 CPU build of `whisper-cli.exe` and its required DLLs;
- multilingual `ggml-base-q5_1.bin`;
- `ggml-silero-v6.2.0.bin` for voice activity detection;
- `LICENSE-whisper.cpp.txt`, `LICENSE-Whisper-model.txt`, and `LICENSE-Silero-VAD.txt` from the exact downloaded distributions.

Install the build dependency and run the component builder:

```bat
python -m pip install -r requirements-transcription-build.txt
build_transcription_component.bat
```

The builder packages and self-tests the worker, `whisper.cpp`, models, and notices; writes its ZIP and checksum under `release\components\transcription\<version>\`; and can generate `assets\transcription-component.json` for a version-specific GitHub release. Upload that exact ZIP before building the main application.

## Troubleshooting

- If diagnostics says `yt-dlp` is outdated, update the package in source builds or download a newer app release.
- If diagnostics says `ffmpeg` or `ffprobe` is missing, install FFmpeg and make sure both tools are on `PATH`, or use the packaged EXE.
- If diagnostics says JavaScript runtime support is missing, install Node or Deno, or use the packaged EXE.
- If a URL cannot be checked, confirm the media is public, available in your region, and reachable in a browser without signing in.
- Instagram Stories require login and are not supported. Use a Reel or post/carousel URL instead.
- If a `tt.site` link fails, copy a `vm.tiktok.com` or direct TikTok video link; expired `tt.site` links can return a non-media response.
- If the app creates a PyInstaller temp folder while running, that is expected for one-file EXEs. Clean shutdown should remove it; diagnostics warns about older leftovers.

## Limitations

- One URL at a time.
- No playlist or batch downloads in the first release.
- Transcription does not identify speakers, translate speech, or summarize the transcript.
- No DRM or copyright bypassing.
- Supported sites and `yt-dlp` behavior can change, so some failures may require dependency updates or a new app release.
- Instagram authentication and private media are not supported. Public availability can still vary because Instagram rate-limits automated requests.
- Facebook posts, photos, private videos, and login-gated videos are not supported.
- TikTok photo posts, private videos, and login-gated videos are not supported.

## Legal Note

Use this tool only for content you have the right to download. This project does not bypass DRM and does not grant rights to third-party content. You are responsible for following each source platform's terms and applicable law.

Packaged releases may include third-party tools and packages such as `yt-dlp`, `yt-dlp-ejs`, `curl-cffi`, `Instaloader`, `Pillow`, `ffmpeg`, `ffprobe`, and Node or Deno. Those components are governed by their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before publishing release binaries.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
