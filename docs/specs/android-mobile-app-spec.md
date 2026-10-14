# Android Mobile App Specification

## Status

Accepted planning baseline for the first Android release. This document defines product behavior and ownership; it does not select the final embedded downloader runtime or approve source implementation beyond the separate roadmap.

## Purpose

Create a simple, mobile-first Android edition of AweDev Media Downloader that runs downloads on the device and preserves the product's essential workflows: video downloads, audio-only downloads, and complete Instagram carousel downloads.

The Android application belongs in this repository as a separate application boundary. The existing Windows/Python application remains independently releasable and is not replaced or migrated by this work.

## Confirmed Decisions

- Android is the only committed mobile target.
- The UI may be redesigned completely for mobile usability.
- The initial distribution channel is GitHub Releases; F-Droid compatibility is a secondary release goal.
- Audio-only downloads are required in the first release.
- Instagram post and carousel downloads are required in the first release.
- OCR and speech transcription are deferred beyond the first release.
- The application uses a native Kotlin/Jetpack Compose shell with a replaceable downloader-engine interface.
- Downloads run locally on the device. No hosted download backend is part of the initial architecture.
- The runtime implementation is selected only after the feasibility work defined in the roadmap passes.

## Landscape Constraints

Research reviewed on 2026-10-14 established the following constraints:

- Android recommends Jetpack Compose, a single-activity application, layered UI/data separation, ViewModels, coroutines, and flows for new applications: <https://developer.android.com/topic/architecture/recommendations>.
- Full YouTube support in current `yt-dlp` requires a supported external JavaScript runtime and `yt-dlp-ejs`; running without one is deprecated: <https://github.com/yt-dlp/yt-dlp/wiki/EJS>.
- The available `youtubedl-android` wrapper can bundle `yt-dlp`, QuickJS, and FFmpeg, but its GPL-3.0 license, prerelease runtime, native-library provenance, and 16 KB compatibility require validation: <https://github.com/yausername/youtubedl-android>.
- Chaquopy can embed current Python versions in an Android Gradle application and is an alternative for directly packaging `yt-dlp` and Instaloader: <https://chaquo.com/chaquopy/doc/current/versions.html>.
- User-created downloads can be published through `MediaStore.Downloads` without broad storage access on modern Android: <https://developer.android.com/training/data-storage/shared/media>.
- Long downloads require Android-compliant visible background execution, such as user-initiated data-transfer jobs on Android 14 and later: <https://developer.android.com/develop/background-work/background-tasks/uidt>.
- Native dependencies must support 16 KB memory page sizes on current Android devices: <https://developer.android.com/guide/practices/page-sizes>.
- F-Droid requires FLOSS source, reviewable dependency provenance, and explicit user consent before downloading executable components: <https://f-droid.org/docs/Inclusion_Policy/>.

## Goals

- Provide a link-to-download workflow suited to a phone.
- Accept links pasted by the user or shared from another Android app.
- Inspect supported links before downloading and show understandable media information.
- Download supported media reliably while the app is backgrounded.
- Support video and required audio-only output.
- Download every accessible item in supported Instagram posts and carousels.
- Save final files where the user can access them from Android file and media applications.
- Keep provider failures, cancellation, and partial completion visible and recoverable.
- Keep the Android engine replaceable so runtime and extractor changes do not spread into the UI.
- Preserve a path to a future cross-platform UI without paying for unused multiplatform infrastructure in the first release.

## Non-Goals

- OCR or visible-text extraction.
- Local or remote speech transcription.
- Playlists, queues, or batch URL entry.
- Private, login-gated, age-gated, or DRM-protected media.
- Account login, browser-cookie extraction, or cookie-file management.
- A hosted download service.
- Google Play publication.
- Silent self-updates of the APK, downloader engine, JavaScript runtime, or native binaries.
- Feature parity with every desktop setting.
- Replacing the desktop application or creating a shared cross-platform runtime before the Android engine is proven.

## Target Environment

- Initial minimum: Android 7.0 / API 24, subject to the selected engine's verified requirements.
- Initial target: the current Android API supported by the build toolchain; API 36 is the 2026 baseline.
- Required release ABI: `arm64-v8a`.
- Required development/test ABI: `x86_64` for emulators.
- Thirty-two-bit ABIs are not required for the first release.
- Portrait phone layout is required. Larger screens may use the same adaptive single-column workflow initially.

## Responsibility And Authority

### Product behavior

This specification is the source of truth for Android behavior. The desktop application is a behavioral reference, not an executable dependency or automatic authority for mobile UX.

### Compose UI

Owns:

- screen rendering and navigation;
- user input and option selection;
- presentation of inspection, progress, completion, and error state;
- accessibility semantics;
- lifecycle-safe observation of download state.

It does not call `yt-dlp`, Instaloader, FFmpeg, QuickJS, Python, or storage APIs directly.

### Android application layer

Owns:

- parsing paste/share intents into one candidate URL;
- coordinating inspection and download requests;
- persistent user preferences;
- background job and notification lifecycle;
- cancellation routing;
- publishing finalized files through Android storage APIs;
- exposing stable UI state independent of the selected engine.

### Downloader engine

Owns:

- supported-provider URL recognition;
- remote media inspection and normalized metadata;
- provider-specific extraction;
- format selection;
- downloading temporary media;
- FFmpeg merge or audio extraction when required;
- Instagram post/carousel enumeration;
- provider-specific diagnostics normalized into application errors.

The engine writes only inside an application-controlled staging area. It does not publish directly into shared storage.

### Desktop application

The Python/Tkinter application continues to own Windows behavior. Mobile changes must not require the Windows release to embed Android dependencies or change its distribution model.

## Shared Contracts

Exact language types may vary, but the Android boundary must expose these concepts.

### `MediaInspection`

- normalized source URL;
- provider;
- title;
- creator when available;
- preview image URL when available;
- upload date when available;
- duration when applicable;
- media items and item count;
- media type: video, image, or mixed;
- available quality choices;
- capabilities: video, audio-only, multi-item;
- optional description metadata for future use.

### `DownloadRequest`

- accepted inspection identity;
- mode: video or audio-only;
- selected quality for video;
- selected audio format;
- destination policy;
- group name for multi-item media;
- stable request identifier used by UI, notification, and cancellation paths.

### `DownloadProgress`

- request identifier;
- state: queued, preparing, downloading, processing, publishing, completed, partially completed, cancelled, or failed;
- current item and total items when known;
- bytes and total bytes when known;
- percentage when meaningful;
- speed and estimated remaining time when available;
- user-readable activity text.

Unavailable measurements remain absent rather than displaying invented values.

### `DownloadOutcome`

- overall state;
- successfully published files;
- failed carousel items, if any;
- normalized warning or failure details;
- whether temporary data was fully cleaned.

## Required Behavior

### URL entry and Android sharing

- The home screen provides a URL field, Paste action, Clear action, and explicit Check action.
- The app registers as a share target for plain text containing HTTP or HTTPS links.
- A single supported link shared to the app is placed into the URL field and inspected after the user reaches the app.
- Text containing no supported link remains editable and displays an unsupported-link message.
- Text containing multiple candidate links must not start multiple downloads. The app asks the user to leave one link before inspection.
- Inspection never starts a download.

### Inspection and preview

- Inspection occurs away from the main thread and can be cancelled or superseded by a newer URL.
- A successful inspection displays provider, title, creator, thumbnail when available, duration when applicable, media type, item count, and available quality choices.
- The UI exposes only capabilities reported by the inspection. Audio-only is hidden or disabled for unsupported media.
- A changed URL invalidates the previous inspection and disables Download until the new link passes inspection.
- Unsupported, unavailable, private, login-gated, expired, or network-failed links produce distinct user-facing states where the engine can distinguish them.

### Provider scope

The first release supports:

- public YouTube videos;
- public Instagram Reels;
- public Instagram image, video, and mixed-media posts and carousels;
- public Facebook videos and Reels;
- public TikTok videos and supported short-share links.

Behavior outside this list is unsupported even if the embedded extractor happens to accept it.

### Video download

- The user can choose Best Available or a supported resolution at or below 1080p, 720p, 480p, or 360p when the source exposes those choices.
- The engine may download separate streams and merge them when required.
- The final video must be playable by common Android media applications.
- The UI reports separate preparing/downloading/processing/publishing stages instead of appearing stalled during FFmpeg work.

### Audio-only download

- Audio-only mode is mandatory for supported video sources.
- MP3 is the required first-release output and default.
- Additional desktop formats are deferred unless they are nearly free after engine validation.
- Exactly one final audio file is published per source media item.
- Extraction and transcoding progress is reported as processing when byte progress is unavailable.

### Instagram posts and carousels

- Every accessible image and video item is enumerated before download begins.
- Items retain source order.
- A multi-item post is saved under one named relative folder beneath the app's Downloads location when supported by the storage API.
- Filenames include a stable media or post identifier and an ordered item suffix where needed.
- A failure affecting one item does not delete already finalized items.
- When some items succeed and others fail, the result is `partially completed`, identifies the failed item count, and never reports full success.
- Audio-only mode is unavailable for image-only posts. For mixed posts, the first release does not offer carousel-wide audio extraction.

### Storage and filenames

- Final outputs are published through Android `MediaStore` into `Downloads/AweDev Media Downloader` or its platform-equivalent relative path.
- Temporary downloads remain private to the app until finalized.
- The app does not request all-files access.
- Existing files are never overwritten silently. A stable numeric suffix produces a unique name.
- Incomplete current-item files and engine staging data are removed after cancellation or failure; already published carousel items are retained and reported.
- The completion screen provides Open and Share actions through Android intents when the file type supports them.

### Background execution and cancellation

- A user-started download continues when the app leaves the foreground, subject to Android system constraints.
- Every active background download has an ongoing notification with current state and a Cancel action.
- The app supports one active download request in the first release.
- Starting another request while one is active shows the active request rather than creating a hidden queue.
- Cancellation is idempotent and transitions to a final cancelled state after engine and staging cleanup complete.
- If Android terminates the process, the next launch reports the interrupted request and cleans abandoned staging data before accepting a new download.

### Preferences and diagnostics

- The app remembers the last selected video quality and video/audio mode.
- The destination root is fixed for the first release; arbitrary folder selection is deferred.
- An About/Diagnostics surface displays app version, packaged downloader-engine version, JavaScript runtime availability, FFmpeg availability, supported providers, project link, issue link, license notices, and support link.
- Engine/runtime updates arrive through a signed app release. No runtime silently downloads executable replacements.

### Privacy and legal boundary

- Media URLs and downloaded media stay on the device except for requests made directly to the source platform and required extractor resources.
- No analytics, advertising SDK, telemetry, account system, or remote download backend is included.
- The app explains that users must have the right to download the selected media and that platform availability can change.
- The app does not claim to bypass DRM, authentication, regional controls, or platform restrictions.

## UI State Model

The redesigned UI must represent these states explicitly:

1. Empty: ready for paste or share.
2. Checking: link inspection in progress.
3. Ready: preview and valid options shown.
4. Unsupported/unavailable: actionable explanation shown.
5. Starting: background request is being created.
6. Active: progress, current stage, and Cancel shown.
7. Processing: merge or audio extraction shown without false byte progress.
8. Completed: published outputs and Open/Share actions shown.
9. Partially completed: successful and failed item counts shown.
10. Cancelled or failed: cleanup result and retry path shown.

Visual styling, branding treatment, component layout, animation, and illustration are intentionally left for a later UI design specification. Design work must preserve these states and actions.

## Failure And Edge-Case Rules

- Offline inspection and download failures remain retryable and do not invalidate saved preferences.
- Insufficient storage fails before or during download with a clear message and cleanup attempt.
- Expired short links return a provider-specific explanation when recognized.
- Unsupported private or login-required media never opens a login flow.
- A thumbnail failure does not block download when inspection otherwise succeeds.
- Unknown total size does not prevent download or show a fabricated percentage.
- Notification permission denial does not allow a long background download to start in a state Android cannot support; the app explains the required next step.
- A malformed engine response becomes a controlled engine error rather than a UI crash.
- Repeated downloads of the same source create unique outputs.

## Compatibility And Licensing Gates

Before the engine can be accepted:

- YouTube inspection and full-format download must work with packaged EJS/JavaScript support.
- Instagram carousel enumeration must work without a hosted service.
- TikTok must be tested with the actual Android HTTP stack, including whether browser impersonation is required.
- FFmpeg, QuickJS, Python, and every packaged native library must install and execute on a 16 KB page-size Android environment.
- All runtime and transitive licenses must be compatible with the chosen Android application license and F-Droid goals.
- Native binaries must have documented, reproducible or reviewable provenance.
- APK size and first-run extraction time must be recorded before the engine choice is finalized.

## Acceptance Criteria

- Given a supported URL is shared from a browser, when the app opens, then the URL is ready for inspection without manual retyping.
- Given a supported public video, when inspection succeeds, then the user sees normalized preview information and only valid download options.
- Given a supported YouTube video, when Best Available video is selected, then the download completes with packaged JavaScript support and produces a playable final video.
- Given a supported video, when MP3 audio-only is selected, then exactly one playable MP3 is published.
- Given an Instagram carousel containing images and videos, when downloading, then every accessible item is published in source order under one logical group.
- Given one carousel item fails, when other items succeed, then the successful files remain and the final state reports partial completion.
- Given the app is backgrounded during a download, when Android permits work to continue, then an ongoing notification reports state and offers cancellation.
- Given Cancel is invoked from the app or notification, when cleanup finishes, then the request is cancelled, the current partial file is absent, and finalized earlier carousel items remain reported.
- Given a destination filename already exists, when the same source is downloaded again, then the existing file is preserved and the new output receives a unique name.
- Given the process was terminated during a download, when the app next starts, then it reports interruption, cleans abandoned staging data, and does not claim success.
- Given an unsupported, private, login-gated, or DRM-protected source, when inspection fails, then the app gives an honest unsupported-state message and offers no bypass workflow.
- Given a release APK, when its native libraries are tested in a 16 KB environment, then the app and required engine operations start without alignment or loader failures.
- Given network traffic is inspected, when the app is used normally, then no telemetry or hosted AweDev download service receives the user's URL or media.

## Verification Matrix

- Android 7/API 24 baseline device or emulator, subject to engine compatibility.
- Current Android 15 and Android 16 devices/emulators.
- At least one 16 KB page-size environment.
- Physical ARM64 phone for background, storage, share-intent, notification, and thermal behavior.
- x86-64 emulator for repeatable UI and lifecycle tests.
- Representative public test media for every supported provider and media type.
- Large file, unknown-size stream, interrupted network, low-storage, cancellation, duplicate download, and partial-carousel scenarios.

## Requirements Traceability

| Source decision | Spec coverage |
| --- | --- |
| GitHub/F-Droid distribution | Confirmed Decisions; Preferences and diagnostics; Compatibility and licensing gates |
| Audio-only mandatory | Audio-only download; Acceptance Criteria |
| Instagram carousels mandatory | Provider scope; Instagram posts and carousels; Acceptance Criteria |
| Mobile-first redesign allowed | UI State Model |
| Evaluate robust and cross-platform approaches | Architecture boundary; Landscape Constraints; engine remains replaceable |
| OCR/transcription not early | Non-Goals |

## Open Decisions

- Production engine: existing Android wrapper, owned Chaquopy integration, or another engine proven by the feasibility gate.
- Final Android application license if the selected engine introduces copyleft obligations.
- Whether AAC, M4A, WAV, or FLAC joins MP3 in the first release after cost and output-size validation.
- Whether F-Droid main-repository inclusion is practical or a project-owned F-Droid repository is the better secondary channel.

