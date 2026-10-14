# Android Mobile App Roadmap

## Purpose

Sequence the work required to ship a simple, reliable Android edition of AweDev Media Downloader without destabilizing the existing Windows application.

The behavioral source of truth is `docs/specs/android-mobile-app-spec.md`.

## Confirmed Direction

- Build a native Kotlin/Jetpack Compose Android application with a replaceable downloader-engine boundary.
- Keep the Android application separate from the Python/Tkinter desktop runtime while retaining it in the same product repository.
- Distribute through GitHub Releases first and retain a path toward F-Droid.
- Require video, MP3 audio-only, and complete Instagram post/carousel downloads in the first mobile release.
- Exclude OCR and speech transcription from the early roadmap.
- Allow a complete mobile-first UI redesign after engine feasibility is established.

## Assumptions

- Android is the only committed mobile platform. Cross-platform expansion is preserved architecturally but does not justify Flutter or Kotlin Multiplatform overhead yet.
- The first release supports one active download and no queue.
- Android API 24 is the provisional minimum, ARM64 is the required release ABI, and x86-64 supports emulator validation.
- The current repository remains the product home unless licensing findings require a separately licensed Android repository.
- Runtime versions ship with signed application releases rather than silent component self-updates.

## Sequencing Logic

The downloader engine is the highest-risk dependency. Current YouTube extraction requires external JavaScript execution, audio output requires FFmpeg, and the existing desktop carousel path relies on Instaloader rather than the generic video adapter. Prove those three requirements on real Android hardware before investing in final UI or release packaging.

Once the engine passes, build a narrow end-to-end slice through Android sharing, inspection, background execution, and MediaStore. Provider parity follows that foundation. Visual redesign comes after the state model and workflows are stable, so presentation work does not hide or redefine runtime limitations.

## Phase 1: Android Engine Feasibility

### Outcome

A disposable Android harness proves or rejects candidate engine architectures using the mandatory provider and output workflows.

### Why This Comes Now

UI framework success is irrelevant if packaged YouTube JavaScript execution, FFmpeg audio processing, Instagram carousel enumeration, or Android native-library loading fails.

### Included Work

- Evaluate the current `youtubedl-android` runtime and an owned Chaquopy-based integration where comparison is needed.
- Inspect and download representative public YouTube, Instagram, Facebook, and TikTok media.
- Prove full YouTube format access with packaged EJS and a supported JavaScript runtime.
- Prove video merging and MP3 extraction with packaged FFmpeg.
- Prove ordered Instagram image, video, and mixed-media carousel enumeration and download.
- Exercise cancellation, temporary-file cleanup, and application-private staging.
- Publish representative outputs through MediaStore.
- Measure installed size, initialization delay, memory use, and processing behavior on a physical ARM64 device.
- Validate x86-64 emulator operation and 16 KB page-size compatibility.
- Audit runtime, transitive dependency, native binary, and app-license compatibility.
- Assess whether each candidate can be built transparently enough for F-Droid.

### Excluded Work

- Polished UI.
- Final navigation or visual system.
- General download queue.
- OCR or transcription experiments.
- Rewriting provider extractors from scratch.

### Dependencies And Risks

- Current platform behavior can change during the spike.
- TikTok may depend on browser impersonation support that is difficult to package on Android.
- The quickest wrapper is GPL-3.0 and may impose an unacceptable release-license decision.
- Prebuilt FFmpeg or QuickJS artifacts may fail provenance or 16 KB requirements.
- Carousel support may require direct Instaloader integration rather than the generic wrapper.

### Validation Gate

Choose a production engine only if it demonstrates all mandatory provider flows, playable video, one MP3 output, ordered carousel output, cancellation cleanup, MediaStore publication, and 16 KB compatibility. Record any licensing consequence explicitly. If no candidate passes, stop and revise the product architecture before UI implementation.

## Phase 2: Android Foundation And Vertical Slice

### Outcome

An installable development application completes one representative link-to-file workflow through the production architecture.

### Why This Comes Now

The selected engine must be exercised through real Android lifecycle, storage, and background-work ownership before provider breadth or visual design expands the surface.

### Included Work

- Establish the Compose application and stable engine interface defined by the specification.
- Implement paste and Android share-intent entry.
- Implement normalized inspection and a functional preview state.
- Run one video download through visible background execution and cancellation.
- Publish the final file into the app's Downloads location.
- Persist the minimal mode and quality preferences.
- Expose app and engine versions through a basic diagnostics surface.
- Establish automated checks around domain state and engine-boundary mapping.

### Excluded Work

- Final visual design.
- Full provider parity.
- Audio format choices beyond the required baseline.
- Arbitrary destination folders.
- Release-channel automation.

### Dependencies And Risks

- Phase 1 must fix the runtime boundary and licensing direction.
- Android notification permission and background restrictions vary by OS version.
- Storage publication must not leak temporary files or depend on broad file permissions.

### Validation Gate

On a physical phone, a URL shared from a browser can be inspected, downloaded while the app is backgrounded, cancelled from the notification, and published as a playable file without broad storage access.

## Phase 3: Mandatory Feature Parity

### Outcome

Every first-release provider and both mandatory download modes work through the same mobile workflow.

### Why This Comes Now

Provider differences and multi-item behavior should build on proven lifecycle and storage infrastructure rather than creating parallel workflows.

### Included Work

- Complete YouTube, Instagram Reel/post/carousel, Facebook video/Reel, and TikTok video support.
- Add MP3 audio-only mode for supported video sources.
- Add Best Available and bounded resolution choices.
- Implement ordered multi-item publishing under one logical carousel group.
- Implement unique filename behavior.
- Preserve successful carousel outputs when later items fail and report partial completion.
- Normalize unsupported, unavailable, private, login-gated, expired-link, network, storage, and processing failures.
- Validate repeat downloads and cleanup after failure, cancellation, and interrupted process recovery.

### Excluded Work

- Playlists, queues, batch input, and authenticated media.
- Advanced yt-dlp command exposure.
- Desktop settings that do not serve the mobile workflow.
- OCR and transcription.

### Dependencies And Risks

- Provider behavior may regress independently and require engine updates.
- Mixed-media carousel storage may behave differently across OEM file and gallery applications.
- Audio conversion increases processing time, heat, battery use, and temporary storage requirements.

### Validation Gate

The complete provider matrix passes on representative public media, including one mixed Instagram carousel, one MP3 extraction, repeat downloads, a partial-carousel failure, and cancellation during download and processing.

## Phase 4: Mobile UX And Accessibility

### Outcome

The proven workflows receive a coherent, mobile-first interface suitable for non-technical users.

### Why This Comes Now

The visual system should express stable states and real capabilities. Designing earlier would risk optimizing interactions around engine behavior that later changes.

### Included Work

- Produce and accept a focused mobile UI/interaction specification.
- Redesign empty, checking, ready, active, processing, completed, partial, cancelled, and failed states.
- Refine carousel preview and progress representation.
- Add clear Open, Share, Retry, and Cancel actions where valid.
- Apply accessible semantics, touch targets, contrast, dynamic text behavior, and screen-reader ordering.
- Validate portrait phones and reasonable larger-screen adaptation.
- Incorporate a separate visual-design contribution without changing the approved behavioral contract.

### Excluded Work

- New downloader capabilities introduced solely by visual design.
- Tablet-specific multi-pane workflows.
- Theme marketplaces or extensive customization.

### Dependencies And Risks

- The Android state model and provider capability reporting must be stable.
- External design work needs the specification's state inventory and constraints.
- Visual complexity must not obscure background, partial-success, or unsupported states.

### Validation Gate

A new user can share a link, understand available modes, start or cancel a download, and locate or share the result without reading documentation. Accessibility checks pass for every required state.

## Phase 5: Hardening And GitHub Release

### Outcome

A signed, supportable APK is ready for public installation through GitHub Releases.

### Why This Comes Now

Signing, dependency provenance, recovery behavior, and release documentation must describe the actual finished runtime rather than an earlier candidate architecture.

### Included Work

- Finalize the application ID, signing process, versioning, and upgrade behavior.
- Verify all packaged licenses and third-party notices.
- Run ARM64 physical-device, x86-64 emulator, Android-version, and 16 KB compatibility checks.
- Validate large downloads, insufficient storage, network interruption, backgrounding, process death, duplicate names, and partial carousel completion.
- Document installation, updates, supported providers, privacy, legal limits, troubleshooting, and checksums.
- Publish a signed APK and matching source/release notes through GitHub Releases.
- Register the package and signing identity as required by Android's current developer-verification rollout.

### Excluded Work

- Google Play submission.
- Silent APK or runtime self-update.
- F-Droid acceptance claims.
- OCR and transcription.

### Dependencies And Risks

- Release signing and package identity become long-lived commitments.
- Extractor behavior can change between final validation and release.
- Native binary provenance or license findings can still block publication.

### Validation Gate

A clean physical device installs the signed APK, completes the required provider matrix, upgrades from a previous test build without losing preferences, and exposes complete source, checksums, license notices, and limitations.

## Phase 6: F-Droid Readiness

### Outcome

The application either qualifies for the main F-Droid repository or has a documented alternative distribution decision.

### Why This Comes Now

F-Droid build reproducibility and inclusion review should follow a stable GitHub release rather than constrain engine discovery prematurely.

### Included Work

- Confirm every dependency and native artifact is FLOSS and acceptable to F-Droid tooling.
- Provide a source-buildable flavor with no proprietary services or silent executable downloads.
- Make builds reproducible where practical and document remaining variance.
- Demonstrate independent value relative to existing F-Droid downloader applications.
- Submit to the main repository when viable, or document a project-owned F-Droid repository as the fallback.

### Excluded Work

- Changing core product behavior only to mimic another F-Droid application.
- Treating submission as guaranteed acceptance.
- Adding alternate stores before GitHub release maintenance is stable.

### Dependencies And Risks

- Prebuilt native runtimes may not meet review or provenance expectations.
- A functionally similar existing app can raise the bar for demonstrated independent value.
- F-Droid review timelines and decisions are external.

### Validation Gate

An F-Droid-compatible build succeeds from published source and passes the relevant inclusion review, or the project records why GitHub Releases or a project-owned repository remains the supported channel.

## Deferred Directions

- Additional audio formats need a small follow-up spec if they add meaningful UX or processing differences.
- OCR requires a separate Android OCR spec; ML Kit and fully FLOSS/offline alternatives must be compared against F-Droid goals.
- Speech transcription requires a separate device-performance and model-distribution research phase before a feature spec.
- iOS or broader cross-platform work requires a new roadmap and a fresh assessment of runtime, distribution, and platform policy constraints.
- Download queues, playlists, authentication, custom destinations, and resumable recovery each require separate product decisions.

## Primary Risks

1. YouTube JavaScript and proof-of-origin changes can invalidate the packaged engine.
2. Instagram carousel support may prevent use of a single generic yt-dlp wrapper.
3. Native FFmpeg, QuickJS, Python, or HTTP dependencies may fail 16 KB or F-Droid provenance requirements.
4. GPL dependencies may require a different application-license or repository boundary.
5. Provider instability can create a higher ongoing maintenance burden than the UI itself.
6. Large downloads and audio conversion can expose storage, thermal, battery, and lifecycle failures not visible in desktop testing.

## Recommended Next Step

Execute Phase 1 as an isolated Android engine feasibility spike. Do not begin the final UI implementation until the engine validation gate passes.
