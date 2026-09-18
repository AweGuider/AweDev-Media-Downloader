import os
import time
import sys
import yt_dlp
import tempfile
import functools
import importlib.metadata
import json
import queue
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import shutil
import subprocess
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, ImageTk

from media_downloader import (
    AdapterRegistry,
    DownloadCancelled,
    DownloadOptions,
    MediaDownloadService,
    Provider,
)
from media_downloader.adapters import (
    FacebookAdapter,
    InstagramAdapter,
    TikTokAdapter,
    YtDlpVideoAdapter,
)
from media_downloader.health import (
    MODE_DEFINITIONS,
    PROVIDER_LABELS,
    PROVIDER_SUMMARIES,
    UNSUPPORTED_MODES,
    assess_mode_health,
    provider_health,
)
from media_downloader.url_feedback import provider_from_url, user_facing_media_error
from media_downloader.ocr_component import (
    OcrComponentCancelled,
    OcrComponentManager,
)
from media_downloader.ocr_postprocess import extract_visible_text

### Command to create .exe out of .py
# python -m PyInstaller --onefile downloader.py

APP_NAME = "AweDev Media Downloader"
APP_ID = "AweDevMediaDownloader"
SUPPORT_URL = "https://ko-fi.com/awedev"
SUPPORT_LABEL = "☕ Buy a Cappuccino"
PROJECT_URL = "https://github.com/AweGuider/AweDev-Media-Downloader"
LINKTREE_URL = "https://linktr.ee/awedev"
TEST_URL = "https://www.youtube.com/watch?v=QDia3e12czc"
DEFAULT_RESOLUTION = "1080p"
DEFAULT_AUDIO_FORMAT = "MP3"
RESOLUTION_OPTIONS = ("Highest Available", "1080p", "720p", "480p", "360p")
AUDIO_FORMATS = ("MP3", "WAV", "AAC", "FLAC")
PREVIEW_IMAGE_SIZE = (200, 112)
MAX_THUMBNAIL_BYTES = 4 * 1024 * 1024
HEALTH_COLORS = {
    "checking": "#6b7280",
    "pass": "#1f8f4d",
    "warn": "#b7791f",
    "fail": "#b00020",
}

# Default output directory (current folder)
# Set the default output folder for new installations.
default_output_folder = os.path.join(os.path.expanduser("~"), "Downloads", "AweDev-Media-Downloads")
# Ensure the folder exists
os.makedirs(default_output_folder, exist_ok=True)

def settings_path():
    settings_root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(settings_root, APP_ID, "settings.json")

def load_settings():
    try:
        with open(settings_path(), "r", encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}

saved_settings = load_settings()

# Use this as the initial output directory
saved_output_directory = saved_settings.get("output_directory")
output_directory = saved_output_directory if isinstance(saved_output_directory, str) and saved_output_directory else default_output_folder
try:
    os.makedirs(output_directory, exist_ok=True)
except OSError:
    output_directory = default_output_folder
    os.makedirs(output_directory, exist_ok=True)

saved_resolution = saved_settings.get("selected_resolution")
selected_resolution = saved_resolution if isinstance(saved_resolution, str) and saved_resolution else DEFAULT_RESOLUTION

fetch_delay = None  # Global variable to track scheduled fetch calls
fetch_request_id = 0
url_ready_for_download = False
latest_media_info = None
download_thread = None
download_cancel_event = None
ocr_install_thread = None
ocr_install_cancel_event = None
is_closing = False
ui_queue = queue.Queue()
startup_diagnostic_results = None
mode_health_results = ()
provider_session_issues = {}
provider_status_widgets = {}
about_window = None

# For future implementation of stable progress UI update
latest_progress = {"percent": "0%", "speed": "N/A", "eta": "Unknown"}

APP_VERSION = "2.0.0"
STALE_MEI_AGE_SECONDS = 24 * 60 * 60
JS_RUNTIME_CANDIDATES = (
    ("deno", "deno", (2, 3, 0), True),
    ("node", "node", (22, 0, 0), False),
    ("bun", "bun", (1, 2, 11), True),
    ("quickjs", "qjs", (2023, 12, 9), False),
)

def app_runtime_dir():
    """Returns the PyInstaller extraction folder when frozen, otherwise the source folder."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

def app_resource_path(*parts):
    return os.path.join(app_runtime_dir(), *parts)

def ocr_component_manifest_path():
    configured_path = os.environ.get("AWEDEV_OCR_COMPONENT_MANIFEST")
    if configured_path:
        return configured_path
    release_manifest = app_resource_path("assets", "ocr-component.json")
    if os.path.isfile(release_manifest):
        return release_manifest
    return app_resource_path("assets", "ocr-component.unavailable.json")

ocr_component_manager = OcrComponentManager.from_manifest_path(
    Path(ocr_component_manifest_path()),
    APP_ID,
)

def set_app_icon(window):
    icon_path = app_resource_path("assets", "app.ico")
    if not os.path.exists(icon_path):
        return

    try:
        window.iconbitmap(icon_path)
    except tk.TclError:
        pass

def save_settings():
    data = {
        "output_directory": output_directory,
        "selected_resolution": selected_resolution,
        "audio_only": audio_only.get(),
        "audio_format": selected_audio_format.get(),
        "delete_temp_files": delete_temp_files.get(),
        "preserve_upload_date": preserve_upload_date.get(),
        "group_multi_item": group_multi_item.get(),
        "open_folder_after_download": open_folder_after_download.get(),
        "extract_visible_text": extract_visible_text_enabled.get(),
    }

    try:
        path = settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as settings_file:
            json.dump(data, settings_file, indent=2)
    except OSError as e:
        print(f"Could not save settings: {e}")

def binary_name(name):
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name

def bundled_binary_path(name):
    executable = binary_name(name)
    bundled_path = os.path.join(app_runtime_dir(), executable)
    if os.path.exists(bundled_path):
        return bundled_path
    return None

def resolve_windows_command(executable):
    if os.name != "nt":
        return None

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$cmd = Get-Command -Name '{executable}' -ErrorAction SilentlyContinue; if ($cmd) {{ $cmd.Source }}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None

    candidate = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
    if candidate and os.path.exists(candidate):
        return candidate
    return None

@functools.lru_cache(maxsize=None)
def system_binary_path(name):
    executable = binary_name(name)
    return shutil.which(executable) or resolve_windows_command(executable)

def runtime_binary_path(name):
    return bundled_binary_path(name) or system_binary_path(name)

def runtime_binary_dir(*required_names):
    runtime_dir = app_runtime_dir()
    if all(os.path.exists(os.path.join(runtime_dir, binary_name(name))) for name in required_names):
        return runtime_dir

    resolved = [runtime_binary_path(name) for name in required_names]
    if all(resolved):
        directories = {os.path.dirname(path) for path in resolved}
        if len(directories) == 1:
            return directories.pop()

    return None

def prepend_runtime_tools_to_path():
    runtime_dir = app_runtime_dir()
    current_path = os.environ.get("PATH", "")
    if runtime_dir and runtime_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = runtime_dir + os.pathsep + current_path

def iter_js_runtime_candidates():
    for source, resolver in (("bundled", bundled_binary_path), ("system", system_binary_path)):
        for runtime_name, executable_name, min_version, needs_remote_components in JS_RUNTIME_CANDIDATES:
            runtime_path = resolver(executable_name)
            if runtime_path:
                yield {
                    "name": runtime_name,
                    "executable": executable_name,
                    "path": runtime_path,
                    "min_version": min_version,
                    "needs_remote_components": needs_remote_components,
                    "source": source,
                }

@functools.lru_cache(maxsize=1)
def selected_js_runtime():
    for runtime in iter_js_runtime_candidates():
        is_usable, version_line, _ = probe_js_runtime(runtime)
        if is_usable:
            runtime["version_line"] = version_line
            return runtime
    return None

def create_ytdlp_options(overrides=None):
    options = {"quiet": True}

    ffmpeg_dir = runtime_binary_dir("ffmpeg", "ffprobe")
    if ffmpeg_dir:
        options["ffmpeg_location"] = ffmpeg_dir

    runtime = selected_js_runtime()
    if runtime:
        options["js_runtimes"] = {runtime["name"]: {"path": runtime["path"]}}
        if runtime["needs_remote_components"]:
            options["remote_components"] = ["ejs:npm"]

    if overrides:
        options.update(overrides)

    return options

prepend_runtime_tools_to_path()

adapter_registry = AdapterRegistry([
    YtDlpVideoAdapter(
        provider=Provider.YOUTUBE,
        supported_hosts=("youtube.com", "youtu.be", "youtube-nocookie.com"),
        options_factory=create_ytdlp_options,
        display_name="YouTube",
    ),
    InstagramAdapter(create_ytdlp_options),
    FacebookAdapter(create_ytdlp_options),
    TikTokAdapter(create_ytdlp_options),
])
media_service = MediaDownloadService(adapter_registry)

def diagnostic(status, label, detail):
    return {"status": status, "label": label, "detail": detail}

def package_version(package_name):
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None

def first_output_line(text):
    for line in text.splitlines():
        if line.strip():
            return clean_text(line.strip())
    return ""

def compact_version_line(line):
    words = line.split()
    if len(words) >= 3 and words[1].lower() == "version":
        return f"{words[0]} {words[2]}"
    return line[:120]

def js_runtime_version_arg(runtime_name):
    return "--help" if runtime_name == "quickjs" else "--version"

def run_command(args, timeout=5):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

def parse_version_tuple(text):
    numbers = re.findall(r"\d+", text)
    return tuple(int(number) for number in numbers[:3])

def compare_versions(left, right):
    left_parts = parse_version_tuple(left)
    right_parts = parse_version_tuple(right)
    length = max(len(left_parts), len(right_parts))
    left_parts += (0,) * (length - len(left_parts))
    right_parts += (0,) * (length - len(right_parts))
    return (left_parts > right_parts) - (left_parts < right_parts)

def probe_js_runtime(runtime):
    try:
        result = run_command([runtime["path"], js_runtime_version_arg(runtime["name"])])
    except Exception as e:
        return False, "", f"{runtime['name']} found but could not run: {e}"

    if result.returncode != 0 and runtime["name"] != "quickjs":
        return False, "", f"{runtime['name']} returned {result.returncode}"

    version_line = first_output_line(result.stdout or result.stderr) or runtime["name"]
    return True, version_line, None

def check_binary_version(name):
    binary_path = runtime_binary_path(name)
    if not binary_path:
        return diagnostic("fail", name, "missing")

    try:
        result = run_command([binary_path, "-version"])
    except Exception as e:
        return diagnostic("fail", name, f"found but could not run: {e}")

    if result.returncode != 0:
        return diagnostic("fail", name, f"found but returned {result.returncode}")

    version_line = compact_version_line(first_output_line(result.stdout or result.stderr))
    source = "bundled" if bundled_binary_path(name) else "system"
    return diagnostic("pass", name, f"{version_line} ({source})")

def check_js_runtime():
    runtime = selected_js_runtime()
    if not runtime:
        failures = []
        for candidate in iter_js_runtime_candidates():
            _, _, error = probe_js_runtime(candidate)
            if error:
                failures.append(error)

        if failures:
            return diagnostic("fail", "JS runtime", "; ".join(failures[:2]))
        return diagnostic("fail", "JS runtime", "missing Deno, Node, Bun, or QuickJS")

    version_line = runtime.get("version_line") or runtime["name"]
    version_text = " ".join(re.findall(r"\d+(?:\.\d+)*", version_line)[:1])
    if version_text and runtime["min_version"]:
        min_text = ".".join(str(part) for part in runtime["min_version"])
        if compare_versions(version_text, min_text) < 0:
            return diagnostic("warn", "JS runtime", f"{version_line}; recommended >= {min_text}")

    return diagnostic("pass", "JS runtime", f"{version_line} ({runtime['source']})")

def check_ytdlp_latest(local_version):
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/yt-dlp/json", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return diagnostic("warn", "yt-dlp update", f"could not check latest version: {e}")

    latest_version = data.get("info", {}).get("version")
    if not latest_version:
        return diagnostic("warn", "yt-dlp update", "latest version unknown")

    if compare_versions(local_version, latest_version) < 0:
        return diagnostic("warn", "yt-dlp update", f"local {local_version}, latest {latest_version}")

    return diagnostic("pass", "yt-dlp update", f"local {local_version} is current")

def check_network():
    try:
        with urllib.request.urlopen("https://www.youtube.com/generate_204", timeout=5) as response:
            status_code = getattr(response, "status", response.getcode())
    except Exception as e:
        return diagnostic("warn", "YouTube network", f"reachability check failed: {e}")

    if 200 <= status_code < 400:
        return diagnostic("pass", "YouTube network", "reachable")
    return diagnostic("warn", "YouTube network", f"returned HTTP {status_code}")

def check_pyinstaller_temp_leftovers():
    temp_root = tempfile.gettempdir()
    current_runtime = os.path.realpath(app_runtime_dir())
    stale_count = 0

    try:
        entries = os.listdir(temp_root)
    except OSError as e:
        return diagnostic("warn", "Temp cleanup", f"could not inspect Temp: {e}")

    now = time.time()
    for entry in entries:
        if not entry.startswith("_MEI"):
            continue

        path = os.path.realpath(os.path.join(temp_root, entry))
        if path == current_runtime or not os.path.isdir(path):
            continue

        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue

        if age >= STALE_MEI_AGE_SECONDS:
            stale_count += 1

    if stale_count:
        return diagnostic("warn", "Temp cleanup", f"{stale_count} old PyInstaller temp folder(s) found")
    return diagnostic("pass", "Temp cleanup", "no old PyInstaller temp folders found")

def run_startup_diagnostics():
    results = [
        diagnostic("pass", "App", f"{APP_VERSION} ({'EXE' if getattr(sys, 'frozen', False) else 'source'})")
    ]

    registered_providers = set(adapter_registry.providers)
    for provider in Provider:
        provider_label = PROVIDER_LABELS[provider]
        status = "pass" if provider in registered_providers else "fail"
        detail = "registered" if status == "pass" else "missing"
        results.append(diagnostic(status, f"{provider_label} adapter", detail))

    ytdlp_version = getattr(yt_dlp.version, "__version__", None) or package_version("yt-dlp")
    if ytdlp_version:
        results.append(diagnostic("pass", "yt-dlp", ytdlp_version))
        results.append(check_ytdlp_latest(ytdlp_version))
    else:
        results.append(diagnostic("fail", "yt-dlp", "version unknown"))

    ejs_version = package_version("yt-dlp-ejs")
    if ejs_version:
        results.append(diagnostic("pass", "yt-dlp-ejs", ejs_version))
    else:
        results.append(diagnostic("fail", "yt-dlp-ejs", "missing"))

    instaloader_version = package_version("instaloader")
    if instaloader_version:
        results.append(diagnostic("pass", "Instaloader", instaloader_version))
    else:
        results.append(diagnostic("fail", "Instaloader", "missing; Instagram posts are unavailable"))

    curl_cffi_version = package_version("curl-cffi")
    if curl_cffi_version:
        results.append(diagnostic("pass", "curl-cffi", curl_cffi_version))
    else:
        results.append(diagnostic("fail", "curl-cffi", "missing; TikTok downloads may be unavailable"))

    results.append(check_binary_version("ffmpeg"))
    results.append(check_binary_version("ffprobe"))
    results.append(check_js_runtime())
    results.append(check_network())
    results.append(check_pyinstaller_temp_leftovers())
    ocr_status = ocr_component_manager.status_text()
    ocr_state = (
        "warn"
        if ocr_component_manager.manifest.available
        and ocr_component_manager.install_directory.exists()
        and not ocr_component_manager.is_installed()
        else "pass"
    )
    results.append(diagnostic(ocr_state, "Optional OCR component", ocr_status))
    return results

def format_diagnostics(results, media_health=()):
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for result in results:
        counts[result["status"]] += 1

    lines = [f"Diagnostics: {counts['pass']} OK, {counts['warn']} warning(s), {counts['fail']} failure(s)"]
    labels = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}
    for result in results:
        lines.append(f"[{labels[result['status']]}] {result['label']}: {result['detail']}")
    if media_health:
        lines.extend(("", "Media support:"))
        state_labels = {"pass": "READY", "warn": "LIMITED", "fail": "UNAVAILABLE"}
        for mode in media_health:
            provider_label = PROVIDER_LABELS[mode.definition.provider]
            lines.append(
                f"[{state_labels[mode.status]}] {provider_label} — {mode.definition.label}: {mode.detail}"
            )
    return "\n".join(lines)

def diagnostics_color(results):
    statuses = {result["status"] for result in results}
    if "fail" in statuses:
        return "#b00020"
    if "warn" in statuses:
        return "#8a5a00"
    return "#1b6b34"

def show_diagnostics():
    diagnostics_visible.set(True)
    diagnostics_panel.grid()
    diagnostics_button.config(text="Hide Diagnostics")

def hide_diagnostics():
    diagnostics_visible.set(False)
    diagnostics_panel.grid_remove()
    diagnostics_button.config(text="Show Diagnostics")

def toggle_diagnostics():
    if diagnostics_visible.get():
        hide_diagnostics()
    else:
        show_diagnostics()

def apply_startup_diagnostics(results):
    global startup_diagnostic_results, mode_health_results

    startup_diagnostic_results = tuple(results)
    mode_health_results = assess_mode_health(results)
    formatted = format_diagnostics(results, mode_health_results)
    summary, _, details = formatted.partition("\n")
    color = diagnostics_color(results)
    diagnostics_summary_label.config(text=summary, foreground=color)
    diagnostics_text.config(state=tk.NORMAL)
    diagnostics_text.delete("1.0", tk.END)
    diagnostics_text.insert("1.0", details)
    diagnostics_text.config(state=tk.DISABLED)
    update_provider_status_widgets()

    if any(result["status"] != "pass" for result in results):
        show_diagnostics()

def run_startup_diagnostics_async():
    diagnostics_summary_label.config(text="Diagnostics: checking...", foreground="#333333")
    diagnostics_text.config(state=tk.NORMAL)
    diagnostics_text.delete("1.0", tk.END)
    diagnostics_text.config(state=tk.DISABLED)

    def worker():
        results = run_startup_diagnostics()
        queue_ui("diagnostics", results)

    threading.Thread(target=worker, daemon=True).start()

def provider_display_status(provider):
    if not startup_diagnostic_results:
        return "checking", "Checking..."

    status = provider_health(provider, mode_health_results)
    if status != "fail" and provider in provider_session_issues:
        return "warn", "Check failed"
    return status, {"pass": "Ready", "warn": "Limited", "fail": "Unavailable"}[status]

def provider_detail_text(provider):
    state_labels = {"pass": "Ready", "warn": "Limited", "fail": "Unavailable"}
    lines = []
    matching_health = [mode for mode in mode_health_results if mode.definition.provider == provider]
    if matching_health:
        for mode in matching_health:
            line = f"{mode.definition.label}: {state_labels[mode.status]}"
            if mode.status != "pass":
                line += f" — {mode.detail}"
            lines.append(line)
    else:
        lines.extend(
            f"{mode.label}: Checking..."
            for mode in MODE_DEFINITIONS
            if mode.provider == provider
        )

    lines.extend(
        f"{label}: {detail}"
        for mode_provider, label, detail in UNSUPPORTED_MODES
        if mode_provider == provider
    )
    if provider in provider_session_issues:
        lines.append(f"Last check failed: {provider_session_issues[provider]}")
    return "\n".join(lines)

def draw_platform_icon(canvas, provider, color):
    canvas.delete("all")
    background = canvas.cget("background")
    if provider == Provider.YOUTUBE:
        canvas.create_polygon(
            7, 9, 29, 9, 32, 12, 32, 26, 29, 29, 7, 29, 4, 26, 4, 12,
            smooth=True,
            fill=color,
            outline=color,
        )
        canvas.create_polygon(15, 14, 15, 24, 24, 19, fill=background, outline=background)
    elif provider == Provider.INSTAGRAM:
        canvas.create_rectangle(6, 6, 30, 30, outline=color, width=3)
        canvas.create_oval(12, 12, 24, 24, outline=color, width=3)
        canvas.create_oval(25, 9, 28, 12, fill=color, outline=color)
    elif provider == Provider.FACEBOOK:
        canvas.create_text(18, 19, text="f", fill=color, font=("Segoe UI", 27, "bold"))
    elif provider == Provider.TIKTOK:
        canvas.create_line(20, 7, 20, 24, fill=color, width=4)
        canvas.create_line(20, 8, 29, 12, fill=color, width=4)
        canvas.create_oval(10, 21, 21, 30, fill=color, outline=color)

def update_provider_status_widgets():
    for provider, widgets in provider_status_widgets.items():
        status, status_text = provider_display_status(provider)
        color = HEALTH_COLORS[status]
        draw_platform_icon(widgets["canvas"], provider, color)
        widgets["status_label"].config(text=status_text, foreground=color)

def record_provider_check(url, error_message=None):
    provider = provider_from_url(url)
    if not provider:
        return
    if error_message:
        provider_session_issues[provider] = error_message
    else:
        provider_session_issues.pop(provider, None)
    update_provider_status_widgets()

def create_provider_status_widget(parent, provider, column):
    card = ttk.Frame(parent, cursor="hand2")
    card.grid(row=0, column=column, sticky="nsew", padx=4)
    card.columnconfigure(0, weight=1)

    icon_canvas = tk.Canvas(
        card,
        width=36,
        height=36,
        borderwidth=0,
        highlightthickness=0,
        background=root.cget("background"),
        cursor="hand2",
    )
    icon_canvas.grid(row=0, column=0)
    name_label = ttk.Label(card, text=PROVIDER_LABELS[provider], font=("Segoe UI", 9, "bold"), cursor="hand2")
    name_label.grid(row=1, column=0)
    mode_label = ttk.Label(card, text=PROVIDER_SUMMARIES[provider], foreground="#5f6368", font=("Segoe UI", 8), cursor="hand2")
    mode_label.grid(row=2, column=0)
    status_label = ttk.Label(card, text="Checking...", foreground=HEALTH_COLORS["checking"], font=("Segoe UI", 8), cursor="hand2")
    status_label.grid(row=3, column=0, pady=(1, 0))

    clickable_widgets = (card, icon_canvas, name_label, mode_label, status_label)
    for widget in clickable_widgets:
        widget.bind("<Button-1>", lambda _event: show_about_dialog())
    provider_status_widgets[provider] = {
        "canvas": icon_canvas,
        "status_label": status_label,
    }
    draw_platform_icon(icon_canvas, provider, HEALTH_COLORS["checking"])

def show_about_dialog():
    global about_window

    if about_window:
        try:
            if about_window.winfo_exists():
                about_window.lift()
                about_window.focus_force()
                return
        except tk.TclError:
            about_window = None

    about_window = tk.Toplevel(root)
    about_window.title(f"About {APP_NAME}")
    about_window.transient(root)
    about_window.resizable(False, False)
    set_app_icon(about_window)

    def close_about():
        global about_window
        if about_window:
            about_window.destroy()
            about_window = None

    content = ttk.Frame(about_window, padding=18)
    content.grid(sticky="nsew")
    ttk.Label(content, text=APP_NAME, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(content, text=f"Version {APP_VERSION}", foreground="#5f6368").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))

    row = 2
    for provider in Provider:
        status, status_text = provider_display_status(provider)
        color = HEALTH_COLORS[status]
        ttk.Label(content, text=PROVIDER_LABELS[provider], font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=3)
        ttk.Label(content, text=status_text, foreground=color).grid(row=row, column=1, sticky="nw", padx=(0, 12), pady=3)
        ttk.Label(content, text=provider_detail_text(provider), justify=tk.LEFT, wraplength=310).grid(row=row, column=2, sticky="nw", pady=3)
        row += 1

    ttk.Label(
        content,
        text="Readiness reflects local checks. Platform access is confirmed when a URL is checked.",
        foreground="#5f6368",
        wraplength=480,
        justify=tk.LEFT,
    ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 0))
    row += 1

    links = ttk.Frame(content)
    links.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(14, 0))
    ttk.Button(links, text="About Project", command=lambda: open_external_url(PROJECT_URL, "About Project")).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(links, text="About AweDev", command=lambda: open_external_url(LINKTREE_URL, "About AweDev")).grid(row=0, column=1, padx=(0, 6))
    ttk.Button(links, text="Close", command=close_about).grid(row=0, column=2)

    about_window.protocol("WM_DELETE_WINDOW", close_about)

def queue_ui(action, *args):
    ui_queue.put((action, args))

def process_ui_queue():
    while True:
        try:
            action, args = ui_queue.get_nowait()
        except queue.Empty:
            break

        if action == "diagnostics":
            apply_startup_diagnostics(*args)
        elif action == "status":
            status_label.config(text=args[0])
        elif action == "media_info_results":
            apply_media_info_results(*args)
        elif action == "download_done":
            update_ui_after_download(*args)
        elif action == "ocr_install_progress":
            update_ocr_install_progress(*args)
        elif action == "ocr_install_done":
            update_ui_after_ocr_install(*args)

    if not is_closing or download_is_active() or ocr_install_is_active():
        root.after(100, process_ui_queue)

def queue_status(text):
    queue_ui("status", text)

def download_is_active():
    return download_thread is not None and download_thread.is_alive()

def ocr_install_is_active():
    return ocr_install_thread is not None and ocr_install_thread.is_alive()

def set_download_button_enabled(enabled):
    if "download_button" in globals():
        if enabled:
            download_button.config(state=tk.NORMAL, bg="#1f8f4d", cursor="hand2")
        else:
            download_button.config(state=tk.DISABLED, bg="#8aa99a", cursor="")

def set_quality_state(enabled):
    if (
        "resolution_dropdown" not in globals()
        or "audio_format_dropdown" not in globals()
        or "audio_checkbox" not in globals()
    ):
        return

    capabilities = latest_media_info.get("capabilities") if enabled and latest_media_info else None
    audio_supported = bool(capabilities and capabilities.audio_extraction)
    quality_supported = bool(capabilities and capabilities.quality_selection)
    audio_checkbox.config(state=tk.NORMAL if not enabled or audio_supported else tk.DISABLED)

    if audio_only.get():
        audio_format_dropdown.config(state="readonly" if enabled and audio_supported else "disabled")
        resolution_dropdown.config(state="disabled")
    else:
        audio_format_dropdown.config(state="disabled")
        resolution_dropdown.config(state="readonly" if enabled and quality_supported else "disabled")

def set_multi_item_option_visible(visible):
    if "group_multi_item_checkbox" not in globals():
        return
    if visible:
        group_multi_item_checkbox.grid()
    else:
        group_multi_item_checkbox.grid_remove()

def multi_item_ready_text(media_info):
    item_count = media_info.get("item_count") or 1
    if item_count <= 1:
        return "Ready to download."
    if group_multi_item.get():
        return f"Ready to download {item_count} items into one folder."
    return f"Ready to download {item_count} items."

def toggle_group_multi_item():
    save_settings()
    if url_ready_for_download and latest_media_info and not download_is_active():
        status_label.config(text=multi_item_ready_text(latest_media_info))

def update_ocr_component_controls():
    if "ocr_component_status_label" not in globals():
        return
    installed = ocr_component_manager.is_installed()
    ocr_component_status_label.config(text=ocr_component_manager.status_text())
    if ocr_install_is_active():
        remove_ocr_component_button.grid_remove()
        cancel_ocr_install_button.grid()
    elif installed:
        remove_ocr_component_button.grid()
        cancel_ocr_install_button.grid_remove()
    else:
        remove_ocr_component_button.grid_remove()
        cancel_ocr_install_button.grid_remove()
    controls_enabled = (
        not ocr_install_is_active()
        and not download_is_active()
        and not audio_only.get()
    )
    visible_text_checkbox.config(state=tk.NORMAL if controls_enabled else tk.DISABLED)
    remove_ocr_component_button.config(state=tk.NORMAL if controls_enabled else tk.DISABLED)

def cancel_ocr_component_install():
    if ocr_install_cancel_event:
        ocr_install_cancel_event.set()
        ocr_component_status_label.config(text="Canceling OCR component installation...")
        cancel_ocr_install_button.config(state=tk.DISABLED)

def toggle_visible_text_extraction():
    global ocr_install_thread, ocr_install_cancel_event

    if not extract_visible_text_enabled.get():
        save_settings()
        update_ocr_component_controls()
        return

    if ocr_component_manager.is_installed():
        save_settings()
        update_ocr_component_controls()
        return

    extract_visible_text_enabled.set(False)
    if not ocr_component_manager.manifest.available:
        messagebox.showinfo(
            "OCR Component Unavailable",
            "This app build does not include a verified OCR component download.\n\n"
            "Install a newer release when the optional component is published.",
        )
        update_ocr_component_controls()
        return

    confirmed = messagebox.askyesno(
        "Download Optional OCR Component",
        "Visible-text extraction requires the optional OCR component.\n\n"
        f"{ocr_component_manager.size_summary()}\n\n"
        "The component is downloaded from this project's GitHub Releases page. "
        "Text recognition runs locally after installation.\n\n"
        "Download and enable it now?",
    )
    if not confirmed:
        update_ocr_component_controls()
        return

    ocr_install_cancel_event = threading.Event()
    ocr_component_status_label.config(text="Downloading OCR component...")
    visible_text_checkbox.config(state=tk.DISABLED)
    remove_ocr_component_button.config(state=tk.DISABLED)

    def worker():
        try:
            ocr_component_manager.install(
                progress=lambda downloaded, total: queue_ui(
                    "ocr_install_progress", downloaded, total,
                ),
                cancel_event=ocr_install_cancel_event,
            )
            queue_ui("ocr_install_done", True, None)
        except Exception as error:
            queue_ui("ocr_install_done", False, str(error))

    ocr_install_thread = threading.Thread(target=worker, daemon=True)
    ocr_install_thread.start()
    update_ocr_component_controls()

def update_ocr_install_progress(downloaded, total):
    if total:
        percent = min(100, int(downloaded * 100 / total))
        ocr_component_status_label.config(text=f"Downloading OCR component... {percent}%")
    else:
        ocr_component_status_label.config(text=f"Downloading OCR component... {downloaded // (1024 * 1024)} MB")

def update_ui_after_ocr_install(success, error_message=None):
    global ocr_install_thread, ocr_install_cancel_event

    ocr_install_thread = None
    ocr_install_cancel_event = None
    cancel_ocr_install_button.config(state=tk.NORMAL)
    if success:
        extract_visible_text_enabled.set(True)
        save_settings()
        if not is_closing:
            messagebox.showinfo(
                "OCR Component Installed",
                "The optional OCR component was installed and visible-text extraction is now enabled.",
            )
    else:
        extract_visible_text_enabled.set(False)
        save_settings()
        if (
            not is_closing
            and error_message
            and error_message != "OCR component installation cancelled."
        ):
            messagebox.showerror("OCR Installation Failed", error_message)
    if is_closing and not download_is_active():
        root.destroy()
        return
    update_ocr_component_controls()
    run_startup_diagnostics_async()

def remove_ocr_component():
    if download_is_active() or ocr_install_is_active():
        messagebox.showwarning("OCR Component Busy", "Wait for the current operation to finish first.")
        return
    if not messagebox.askyesno(
        "Remove OCR Component",
        "Remove the optional OCR component and reclaim its disk space?",
    ):
        return
    try:
        ocr_component_manager.remove()
    except OSError as error:
        messagebox.showerror("Could Not Remove OCR Component", str(error))
        return
    extract_visible_text_enabled.set(False)
    save_settings()
    update_ocr_component_controls()
    run_startup_diagnostics_async()

def set_link_ready(is_ready, status_text=None):
    global url_ready_for_download
    url_ready_for_download = is_ready
    set_download_button_enabled(is_ready and not download_is_active())
    set_quality_state(is_ready)
    if not is_ready:
        set_multi_item_option_visible(False)

    if status_text is not None:
        status_label.config(text=status_text)

def copy_url_to_clipboard(url):
    root.clipboard_clear()
    root.clipboard_append(url)
    root.update_idletasks()

def open_external_url(url, title):
    try:
        if webbrowser.open(url, new=2):
            return
        raise RuntimeError("No browser accepted the support URL.")
    except Exception as e:
        print(f"Could not open {title}: {e}")

    try:
        copy_url_to_clipboard(url)
        messagebox.showinfo(
            title,
            f"Could not open the page automatically.\n\nThe link was copied to your clipboard:\n{url}",
        )
    except Exception as e:
        print(f"Could not copy {title} URL: {e}")
        messagebox.showerror(
            title,
            f"Could not open the page automatically.\n\nVisit:\n{url}",
        )

def open_support_page():
    """Opens the AweDev Ko-fi page, with a clipboard fallback."""
    open_external_url(SUPPORT_URL, "Support AweDev")

def open_download_folder():
    """ Opens the download folder in File Explorer. """
    folder_path = output_directory  # Use the configured output directory

    try:
        if sys.platform == "win32":
            os.startfile(folder_path)  # ✅ Windows
        elif sys.platform == "darwin":  # macOS
            subprocess.call(["open", folder_path])
        else:  # Linux
            subprocess.call(["xdg-open", folder_path])
    except Exception as e:
        print(f"❌ Error opening folder: {e}")
        messagebox.showerror("Error", "Could not open the download folder.")

def select_output_folder():
    """ Opens a dialog for the user to select an output folder. """
    global output_directory
    folder_selected = filedialog.askdirectory()
    if folder_selected:
        output_directory = folder_selected
        folder_label.config(text=f"Save to: {output_directory}")
        save_settings()

def set_resolution(value):
    """ Updates the selected resolution. """
    global selected_resolution
    selected_resolution = value
    if "resolution_menu" in globals():
        resolution_menu.set(value)
    save_settings()
    print(f"New Resolution: {selected_resolution}, Value: {value}")

def toggle_audio_mode():
    """ Enables or disables audio-only mode and format selection. """
    if audio_only.get():
        resolution_label.grid_remove()
        resolution_dropdown.grid_remove()
        audio_format_label.grid()
        audio_format_dropdown.grid()
    else:
        audio_format_label.grid_remove()
        audio_format_dropdown.grid_remove()
        resolution_label.grid()
        resolution_dropdown.grid()
    set_quality_state(url_ready_for_download)
    update_ocr_component_controls()
    save_settings()

def clean_text(text):
    """ Removes unwanted ANSI escape codes from yt-dlp output. """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def format_duration(duration_seconds):
    if duration_seconds is None:
        return "Length: Unknown"

    try:
        total_seconds = int(duration_seconds)
    except (TypeError, ValueError):
        return "Length: Unknown"

    if total_seconds < 0:
        return "Length: Unknown"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        duration_parts = [f"{hours} hr"]
        if minutes or seconds:
            duration_parts.append(f"{minutes} min")
        if seconds:
            duration_parts.append(f"{seconds} sec")
    elif minutes:
        duration_parts = [f"{minutes} min"]
        if seconds:
            duration_parts.append(f"{seconds} sec")
    else:
        duration_parts = [f"{seconds} sec"]

    return f"Length: {' '.join(duration_parts)}"

def format_upload_date(upload_date):
    if not upload_date:
        return ""

    try:
        return datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""

def clean_metadata_value(value):
    if not value:
        return ""
    return clean_text(str(value)).strip()

def format_live_status(info_dict):
    if info_dict.get("is_live"):
        return "Status: Live"

    live_status = info_dict.get("live_status")
    status_labels = {
        "is_live": "Status: Live",
        "is_upcoming": "Status: Upcoming",
        "was_live": "Status: Past live stream",
    }
    return status_labels.get(live_status, "")

def format_preview_details(media_info):
    details = []

    provider_labels = {
        "youtube": "YouTube",
        "instagram": "Instagram",
        "facebook": "Facebook",
        "tiktok": "TikTok",
    }
    provider = provider_labels.get(media_info.get("provider"))
    if provider:
        details.append(f"Source: {provider}")

    channel = media_info.get("channel")
    if channel:
        details.append(f"Creator: {channel}")

    upload_date_text = media_info.get("upload_date_text")
    if upload_date_text:
        details.append(f"Uploaded: {upload_date_text}")

    status_text = media_info.get("status_text")
    if status_text:
        details.append(status_text)

    return " | ".join(details)

def download_thumbnail_bytes(thumbnail_url):
    if not thumbnail_url:
        return None

    try:
        with urllib.request.urlopen(thumbnail_url, timeout=5) as response:
            thumbnail_bytes = response.read(MAX_THUMBNAIL_BYTES + 1)
    except Exception as e:
        print(f"Could not load preview thumbnail: {e}")
        return None

    if len(thumbnail_bytes) > MAX_THUMBNAIL_BYTES:
        print("Could not load preview thumbnail: image too large")
        return None

    return thumbnail_bytes

def build_media_info(bundle):
    title = clean_text(bundle.title or "Untitled media")
    thumbnail_url = bundle.thumbnail_url
    upload_date = bundle.upload_date
    resolutions = {
        resolution
        for item in bundle.items
        for resolution in item.resolutions
    }
    item_count = len(bundle.items)
    if bundle.media_type.value == "image":
        media_summary = f"Contents: {item_count} image{'s' if item_count != 1 else ''}"
    elif bundle.media_type.value == "mixed":
        media_summary = f"Contents: {item_count} media items"
    else:
        media_summary = format_duration(bundle.duration)

    return {
        "url": bundle.source_url,
        "title": title,
        "channel": clean_metadata_value(bundle.creator),
        "duration": bundle.duration,
        "duration_text": media_summary,
        "thumbnail_url": thumbnail_url,
        "thumbnail_bytes": download_thumbnail_bytes(thumbnail_url),
        "resolutions": sorted(
            resolutions,
            key=lambda value: int(value.replace("p", "")),
            reverse=True,
        ) or (["Highest Available"] if bundle.capabilities.quality_selection else ["Original"]),
        "upload_date": upload_date,
        "upload_date_text": format_upload_date(upload_date),
        "status_text": format_live_status({"live_status": bundle.live_status}),
        "provider": bundle.provider.value,
        "media_type": bundle.media_type.value,
        "item_count": item_count,
        "capabilities": bundle.capabilities,
        "bundle": bundle,
    }

def create_preview_photo(image_bytes):
    source_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    source_image = ImageOps.contain(source_image, PREVIEW_IMAGE_SIZE, Image.Resampling.LANCZOS)

    preview_image = Image.new("RGB", PREVIEW_IMAGE_SIZE, "#f0f0f0")
    x = (PREVIEW_IMAGE_SIZE[0] - source_image.width) // 2
    y = (PREVIEW_IMAGE_SIZE[1] - source_image.height) // 2
    preview_image.paste(source_image, (x, y))
    return ImageTk.PhotoImage(preview_image)

def update_preview_wraplength(event=None):
    if "preview_frame" not in globals() or "preview_details_label" not in globals():
        return

    frame_width = preview_frame.winfo_width()
    if not frame_width:
        return

    if preview_image_label.winfo_ismapped():
        wraplength = max(260, frame_width - PREVIEW_IMAGE_SIZE[0] - 48)
    else:
        wraplength = max(260, frame_width - 24)

    preview_title_label.config(wraplength=wraplength)
    preview_duration_label.config(wraplength=wraplength)
    preview_details_label.config(wraplength=wraplength)

def set_preview_text(title_text, duration_text="", details_text=""):
    global preview_photo_image

    if "preview_image_label" not in globals():
        return

    preview_photo_image = None
    preview_image_label.config(image="", text="")
    preview_image_label.grid_remove()

    preview_title_label.grid_configure(row=0, column=0, columnspan=2, sticky="ew")
    preview_title_label.config(text=title_text)

    if duration_text:
        preview_duration_label.grid_configure(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        preview_duration_label.config(text=duration_text)
        preview_duration_label.grid()
    else:
        preview_duration_label.config(text="")
        preview_duration_label.grid_remove()

    if details_text:
        preview_details_label.grid_configure(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        preview_details_label.config(text=details_text)
        preview_details_label.grid()
    else:
        preview_details_label.config(text="")
        preview_details_label.grid_remove()

    update_preview_wraplength()

def set_preview_with_image(photo_image, title_text, duration_text, details_text):
    global preview_photo_image

    if "preview_image_label" not in globals():
        return

    preview_photo_image = photo_image
    preview_image_label.config(image=preview_photo_image, text="")
    preview_image_label.grid(row=0, column=0, rowspan=3, sticky="w", padx=(0, 12))

    preview_title_label.grid_configure(row=0, column=1, columnspan=1, sticky="new")
    preview_title_label.config(text=title_text)

    preview_duration_label.grid_configure(row=1, column=1, columnspan=1, sticky="new", pady=(6, 0))
    preview_duration_label.config(text=duration_text)
    preview_duration_label.grid()

    if details_text:
        preview_details_label.grid_configure(row=2, column=1, columnspan=1, sticky="new", pady=(4, 0))
        preview_details_label.config(text=details_text)
        preview_details_label.grid()
    else:
        preview_details_label.config(text="")
        preview_details_label.grid_remove()

    update_preview_wraplength()

def reset_media_preview():
    set_preview_text("Nothing to preview")

def show_preview_loading():
    set_preview_text("Checking source...")

def show_preview_error():
    set_preview_text("Preview unavailable", "Link check failed.")

def apply_media_preview(media_info):
    if "preview_image_label" not in globals():
        return

    title_text = media_info.get("title") or "Untitled media"
    duration_text = media_info.get("duration_text") or "Length: Unknown"
    details_text = format_preview_details(media_info)

    thumbnail_bytes = media_info.get("thumbnail_bytes")
    if thumbnail_bytes:
        try:
            set_preview_with_image(
                create_preview_photo(thumbnail_bytes),
                title_text,
                duration_text,
                details_text,
            )
            return
        except Exception as e:
            print(f"Could not render preview thumbnail: {e}")

    set_preview_text(title_text, duration_text, details_text)

def make_progress_hook(cancel_event):
    """Creates a yt-dlp hook that reports progress through the main UI queue."""
    def hook(d):
        if cancel_event.is_set():
            raise DownloadCancelled("Download cancelled")

        if d["status"] == "downloading":
            percent = clean_text(d.get("_percent_str", "0%"))
            speed = clean_text(d.get("_speed_str", "N/A"))
            eta = clean_text(d.get("_eta_str", "Unknown"))
            queue_status(f"Progress: {percent}\nSpeed: {speed}\nETA: {eta}")
        elif d["status"] == "finished":
            queue_status("Processing downloaded file...")
        else:
            queue_status("Working...")

    return hook

def download_video_gui():
    """
    Function triggered when the Download button is clicked.
    """
    global download_thread, download_cancel_event

    url = url_entry.get().strip()

    if not url:
        messagebox.showerror("Error", "Please enter a media URL")
        return

    if not url_ready_for_download:
        messagebox.showwarning("Link Not Ready", "Please wait until the link has been checked.")
        return

    if download_is_active():
        messagebox.showwarning("Download In Progress", "Please wait for the current download to finish.")
        return

    media_info = latest_media_info if latest_media_info and latest_media_info.get("url") == url else None
    download_settings = {
        "url": url,
        "output_dir": output_directory,
        "resolution": selected_resolution,
        "is_audio_only": audio_only.get(),
        "audio_format": selected_audio_format.get().lower(),
        "cleanup_enabled": delete_temp_files.get(),
        "preserve_upload_date": preserve_upload_date.get(),
        "group_multi_item": group_multi_item.get(),
        "extract_visible_text": extract_visible_text_enabled.get(),
        "media_title": media_info.get("title") if media_info else None,
        "upload_date": media_info.get("upload_date") if media_info else None,
        "bundle": media_info.get("bundle") if media_info else None,
    }
    download_cancel_event = threading.Event()

    # Disable the button to prevent multiple clicks
    set_download_button_enabled(False)
    status_label.config(text="Connecting...")

    # Run the download in a separate thread
    download_thread = threading.Thread(
        target=download_video_thread,
        args=(download_settings, download_cancel_event),
    )
    download_thread.start()
    update_ocr_component_controls()

def update_resolution_options(*args):
    """Debounces media metadata fetching while the URL is being edited."""
    global fetch_delay, fetch_request_id, latest_media_info
    url = url_entry.get().strip()

    if fetch_delay:
        root.after_cancel(fetch_delay)
        fetch_delay = None

    if not url:
        fetch_request_id += 1
        latest_media_info = None
        set_link_ready(False, "")
        reset_media_preview()
        if "resolution_menu" in globals():
            resolution_menu.set(selected_resolution)
        status_label.config(text="")
        return

    fetch_request_id += 1
    request_id = fetch_request_id
    latest_media_info = None
    set_link_ready(False, "Checking link...")
    show_preview_loading()
    if not audio_only.get():
        resolution_menu.set("Checking...")
    fetch_delay = root.after(500, lambda: start_media_info_fetch(request_id, url))

def start_media_info_fetch(request_id, url):
    global fetch_delay
    fetch_delay = None

    if request_id != fetch_request_id:
        return

    set_link_ready(False, "Checking link...")
    show_preview_loading()
    if not audio_only.get():
        resolution_menu.set("Checking...")

    threading.Thread(
        target=fetch_media_info_thread,
        args=(request_id, url),
        daemon=True,
    ).start()

def fetch_media_info_thread(request_id, url):
    media_info, error_message = fetch_media_info(url)
    queue_ui("media_info_results", request_id, url, media_info, error_message)

def apply_media_info_results(request_id, url, media_info, error_message=None):
    global latest_media_info

    if request_id != fetch_request_id or url != url_entry.get().strip():
        return

    if error_message:
        record_provider_check(url, error_message)
        latest_media_info = None
        if not audio_only.get():
            resolution_menu.set("Unavailable")
        show_preview_error()
        set_link_ready(False, f"Link check failed\n{error_message}")
        return

    if not media_info:
        record_provider_check(url, "No media metadata returned")
        latest_media_info = None
        if not audio_only.get():
            resolution_menu.set("Unavailable")
        set_link_ready(False, "Link check failed\nNo media metadata returned.")
        show_preview_error()
        return

    record_provider_check(url)
    latest_media_info = media_info
    capabilities = media_info.get("capabilities")
    if capabilities and not capabilities.audio_extraction and audio_only.get():
        audio_only.set(False)
        toggle_audio_mode()

    resolutions = media_info.get("resolutions") if media_info else None
    if not resolutions:
        resolutions = ["Highest Available"]

    resolution_dropdown.config(values=resolutions)

    if capabilities and not capabilities.quality_selection:
        resolution_menu.set(resolutions[0])
    else:
        preferred_resolution = selected_resolution if selected_resolution in resolutions else resolutions[0]
        set_resolution(preferred_resolution)
    apply_media_preview(media_info)
    item_count = media_info.get("item_count") or 1
    set_multi_item_option_visible(bool(capabilities and capabilities.multi_item and item_count > 1))
    ready_text = multi_item_ready_text(media_info)
    set_link_ready(True, ready_text)

def fetch_media_info(url):
    """Fetches normalized preview metadata for a supported URL."""
    try:
        bundle = media_service.inspect(url)
        return build_media_info(bundle), None
    except Exception as e:
        error_message = clean_text(user_facing_media_error(url, e)) or e.__class__.__name__
        print(f"❌ Error fetching media info: {error_message}")
        return None, error_message

def download_video_thread(download_settings, cancel_event):
    """ Runs the video download process in a separate thread. """
    success, error_message, final_path, warning_message = download_video(download_settings, cancel_event)
    queue_ui("download_done", success, error_message, final_path, warning_message)

def update_ui_after_download(success, error_message=None, final_paths=None, warning_message=None):
    """ Updates the UI after the download is completed. """
    global download_thread, download_cancel_event

    download_thread = None
    download_cancel_event = None

    if is_closing and not ocr_install_is_active():
        root.destroy()
        return
    if is_closing:
        return

    if success:
        status_label.config(text="Download complete" if not warning_message else "Download complete with OCR warning")
        saved_paths = list(final_paths or [])
        if len(saved_paths) == 1:
            completion_message = f"File saved to:\n{saved_paths[0]}"
        else:
            parent_paths = {os.path.dirname(path) for path in saved_paths}
            saved_location = parent_paths.pop() if len(parent_paths) == 1 else output_directory
            completion_message = f"{len(saved_paths)} files saved to:\n{saved_location}"
        if warning_message:
            completion_message += f"\n\nVisible-text extraction was skipped:\n{warning_message}"
            messagebox.showwarning("Download Complete", completion_message)
        else:
            messagebox.showinfo("Download Complete", completion_message)
        if open_folder_after_download.get():
            open_download_folder()
    else:
        details = error_message or "Unknown error"
        status_label.config(text=f"Download failed\n{details}")
        if details != "Download cancelled":
            messagebox.showerror("Download Failed", details)

    set_download_button_enabled(url_ready_for_download)
    update_ocr_component_controls()

def download_video(download_settings, cancel_event):
    """Downloads inspected media through its registered provider adapter."""
    url = download_settings["url"]
    output_dir = download_settings["output_dir"]

    # If the user has not changed the output folder, use the default folder
    if output_dir == os.getcwd():
        output_dir = default_output_folder

    try:
        if cancel_event.is_set():
            raise DownloadCancelled("Download cancelled")
        bundle = download_settings.get("bundle") or media_service.inspect(url)
        options = DownloadOptions(
            output_directory=Path(output_dir),
            resolution=download_settings["resolution"],
            audio_only=download_settings["is_audio_only"],
            audio_format=download_settings["audio_format"],
            cleanup_enabled=download_settings["cleanup_enabled"],
            preserve_upload_date=download_settings["preserve_upload_date"],
            group_multi_item=download_settings["group_multi_item"],
        )
        result = media_service.download(bundle, options, cancel_event, make_progress_hook(cancel_event))
        output_files = tuple(result.files)
        warning_message = None
        if download_settings.get("extract_visible_text"):
            queue_status("Extracting visible text...")
            try:
                ocr_files = extract_visible_text(
                    ocr_component_manager,
                    output_files,
                    cancel_event=cancel_event,
                    sample_fps=1.0,
                    max_frames=300,
                )
                output_files += ocr_files
            except OcrComponentCancelled:
                raise DownloadCancelled("Download cancelled")
            except Exception as error:
                warning_message = clean_text(str(error)) or error.__class__.__name__
        return True, None, tuple(str(path) for path in output_files), warning_message

    except DownloadCancelled as e:
        print(f"Download cancelled: {e}")
        return False, str(e), None, None
    except Exception as e:
        error_message = clean_text(user_facing_media_error(url, e)) or e.__class__.__name__
        print(f"❌ Error downloading media: {error_message}")
        return False, error_message, None, None

# Function to clear the URL entry box
def clear_url():
    url_entry.delete(0, tk.END)
    update_resolution_options()

def insert_test_url():
    clear_url()
    url_entry.insert(0, TEST_URL)
    update_resolution_options()

def paste_url_from_clipboard():
    try:
        clipboard_text = root.clipboard_get().strip()
    except tk.TclError:
        messagebox.showwarning("Clipboard Empty", "No text found in the clipboard.")
        return

    if not clipboard_text:
        messagebox.showwarning("Clipboard Empty", "No text found in the clipboard.")
        return

    clear_url()
    url_entry.insert(0, clipboard_text)
    update_resolution_options()

def handle_paste_event(event=None):
    root.after(10, update_resolution_options)

def select_all_url(event=None):
    url_entry.select_range(0, tk.END)
    url_entry.icursor(tk.END)
    return "break"

def delete_previous_word(event=None):
    cursor_position = url_entry.index(tk.INSERT)
    text = url_entry.get()
    start = cursor_position

    while start > 0 and text[start - 1].isspace():
        start -= 1

    while start > 0 and not text[start - 1].isspace():
        start -= 1

    if start != cursor_position:
        url_entry.delete(start, cursor_position)
        update_resolution_options()

    return "break"

def handle_control_keypress(event):
    if not event.state & 0x4:
        return None

    if event.keycode == 65:
        return select_all_url(event)

    if event.keycode == 86:
        paste_url_from_clipboard()
        return "break"

    if event.keysym == "BackSpace" or event.keycode == 8:
        return delete_previous_word(event)

    return None

def reset_output_folder():
    global output_directory
    output_directory = default_output_folder
    os.makedirs(output_directory, exist_ok=True)
    folder_label.config(text=f"Save to: {output_directory}")
    save_settings()

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.hide_job = None
        self.bind_widget(widget)

    def bind_widget(self, widget):
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.schedule_hide, add="+")

    def bind_tree(self, widget):
        self.bind_widget(widget)
        for child in widget.winfo_children():
            self.bind_tree(child)

    def show(self, event=None):
        if self.hide_job:
            self.widget.after_cancel(self.hide_job)
            self.hide_job = None
        if self.tip_window or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            padx=6,
            pady=4,
            wraplength=280,
        )
        label.pack()

    def schedule_hide(self, event=None):
        if self.hide_job:
            self.widget.after_cancel(self.hide_job)
        self.hide_job = self.widget.after(60, self.hide)

    def hide(self):
        self.hide_job = None
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

def on_close():
    global is_closing

    save_settings()

    if download_is_active() or ocr_install_is_active():
        is_closing = True
        if download_cancel_event:
            download_cancel_event.set()
        if ocr_install_cancel_event:
            ocr_install_cancel_event.set()
        status_label.config(text="Canceling active work and cleaning up...")
        download_button.config(state=tk.DISABLED)
        return

    root.destroy()

def update_page_scroll_region(event=None):
    if "page_canvas" in globals():
        page_canvas.configure(scrollregion=page_canvas.bbox("all"))

def update_page_width(event):
    if "page_window" in globals():
        page_canvas.itemconfigure(page_window, width=event.width)

def handle_page_mousewheel(event):
    if "page_canvas" not in globals():
        return None

    if getattr(event, "num", None) == 4:
        scroll_units = -3
    elif getattr(event, "num", None) == 5:
        scroll_units = 3
    elif getattr(event, "delta", 0):
        scroll_units = -3 if event.delta > 0 else 3
    else:
        return None

    page_canvas.yview_scroll(scroll_units, "units")
    return None

# GUI Setup
root = tk.Tk()
root.title(APP_NAME)
root.geometry("760x720")
root.minsize(700, 500)
set_app_icon(root)

try:
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    style.configure("TButton", padding=(8, 4))
except tk.TclError:
    pass

delete_temp_files = tk.BooleanVar(value=bool(saved_settings.get("delete_temp_files", True)))
preserve_upload_date = tk.BooleanVar(value=bool(saved_settings.get("preserve_upload_date", True)))
group_multi_item = tk.BooleanVar(value=bool(saved_settings.get("group_multi_item", True)))
open_folder_after_download = tk.BooleanVar(value=bool(saved_settings.get("open_folder_after_download", True)))
ocr_setting_was_reset = bool(saved_settings.get("extract_visible_text", False)) and not ocr_component_manager.is_installed()
extract_visible_text_enabled = tk.BooleanVar(
    value=bool(saved_settings.get("extract_visible_text", False))
    and ocr_component_manager.is_installed()
)
audio_only = tk.BooleanVar(value=bool(saved_settings.get("audio_only", False)))
saved_audio_format = saved_settings.get("audio_format")
selected_audio_format = tk.StringVar(value=saved_audio_format if saved_audio_format in AUDIO_FORMATS else DEFAULT_AUDIO_FORMAT)
diagnostics_visible = tk.BooleanVar(value=False)
preview_photo_image = None

page_container = ttk.Frame(root)
page_container.pack(fill=tk.BOTH, expand=True)
page_container.columnconfigure(0, weight=1)
page_container.rowconfigure(0, weight=1)

page_canvas = tk.Canvas(page_container, borderwidth=0, highlightthickness=0)
page_canvas.grid(row=0, column=0, sticky="nsew")

page_scrollbar = ttk.Scrollbar(page_container, orient=tk.VERTICAL, command=page_canvas.yview)
page_scrollbar.grid(row=0, column=1, sticky="ns")
page_canvas.configure(yscrollcommand=page_scrollbar.set)

main_frame = ttk.Frame(page_canvas, padding=14)
page_window = page_canvas.create_window((0, 0), window=main_frame, anchor="nw")
main_frame.bind("<Configure>", update_page_scroll_region)
page_canvas.bind("<Configure>", update_page_width)
root.bind_all("<MouseWheel>", handle_page_mousewheel, add="+")
root.bind_all("<Button-4>", handle_page_mousewheel, add="+")
root.bind_all("<Button-5>", handle_page_mousewheel, add="+")
main_frame.columnconfigure(0, weight=1)

app_header_frame = ttk.Frame(main_frame)
app_header_frame.grid(row=0, column=0, sticky="ew")
app_header_frame.columnconfigure(0, weight=1)

app_title_label = ttk.Label(
    app_header_frame,
    text=f"{APP_NAME}  v{APP_VERSION}",
    font=("Segoe UI", 14, "bold"),
)
app_title_label.grid(row=0, column=0, sticky="w")

info_button = tk.Canvas(
    app_header_frame,
    width=28,
    height=28,
    borderwidth=0,
    highlightthickness=0,
    background=root.cget("background"),
    cursor="hand2",
    takefocus=True,
)
info_button.grid(row=0, column=1, sticky="e")

def draw_info_button(color="#5f6368"):
    info_button.delete("all")
    info_button.create_oval(3, 3, 25, 25, outline=color, width=2)
    info_button.create_text(14, 14, text="i", fill=color, font=("Segoe UI", 12, "bold"))

draw_info_button()
info_button.bind("<Button-1>", lambda _event: show_about_dialog())
info_button.bind("<Return>", lambda _event: show_about_dialog())
info_button.bind("<space>", lambda _event: show_about_dialog())
info_button.bind("<Enter>", lambda _event: draw_info_button("#202124"), add="+")
info_button.bind("<Leave>", lambda _event: draw_info_button(), add="+")
ToolTip(info_button, "About, supported media, project links, and current availability.")

availability_frame = ttk.LabelFrame(main_frame, text="Media support", padding=(10, 7))
availability_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
for provider_column in range(len(Provider)):
    availability_frame.columnconfigure(provider_column, weight=1)
for provider_column, provider in enumerate(Provider):
    create_provider_status_widget(availability_frame, provider, provider_column)
media_support_tooltip = ToolTip(availability_frame, "Click for supported media details and current availability.")
for provider_card in availability_frame.winfo_children():
    media_support_tooltip.bind_tree(provider_card)

source_frame = ttk.LabelFrame(main_frame, text="Source", padding=10)
source_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
source_frame.columnconfigure(0, weight=1)

url_frame = ttk.Frame(source_frame)
url_frame.grid(row=0, column=0, sticky="ew")
url_frame.columnconfigure(0, weight=1)

url_entry = ttk.Entry(url_frame)
url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
url_entry.bind("<KeyRelease>", update_resolution_options)
url_entry.bind("<<Paste>>", handle_paste_event, add="+")
url_entry.bind("<Control-KeyPress>", handle_control_keypress)
url_entry.bind("<Control-a>", select_all_url)
url_entry.bind("<Control-A>", select_all_url)
url_entry.bind("<Control-BackSpace>", delete_previous_word)

clear_button = ttk.Button(url_frame, text="Clear", command=clear_url)
clear_button.grid(row=0, column=1, padx=(0, 6))

paste_button = ttk.Button(url_frame, text="Paste", command=paste_url_from_clipboard)
paste_button.grid(row=0, column=2, padx=(0, 6))

fetch_resolution_button = ttk.Button(url_frame, text="Check", command=update_resolution_options)
fetch_resolution_button.grid(row=0, column=3)

test_link_button = ttk.Button(url_frame, text="Try example", command=insert_test_url)
test_link_button.grid(row=1, column=0, sticky="w", pady=(8, 0))

preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding=10)
preview_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
preview_frame.columnconfigure(1, weight=1)
preview_frame.bind("<Configure>", update_preview_wraplength)

preview_image_label = tk.Label(
    preview_frame,
    bg="#f0f0f0",
    relief=tk.SOLID,
    borderwidth=1,
    width=PREVIEW_IMAGE_SIZE[0],
    height=PREVIEW_IMAGE_SIZE[1],
    anchor=tk.CENTER,
)

preview_title_label = ttk.Label(
    preview_frame,
    text="Nothing to preview",
    wraplength=470,
    justify=tk.LEFT,
    font=("Segoe UI", 10, "bold"),
)
preview_title_label.grid(row=0, column=1, sticky="new")

preview_duration_label = ttk.Label(preview_frame, text="", wraplength=470, justify=tk.LEFT)
preview_duration_label.grid(row=1, column=1, sticky="new", pady=(6, 0))

preview_details_label = ttk.Label(preview_frame, text="", wraplength=470, justify=tk.LEFT)
preview_details_label.grid(row=2, column=1, sticky="new", pady=(4, 0))

download_frame = ttk.LabelFrame(main_frame, text="Download", padding=10)
download_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
download_frame.columnconfigure(1, weight=1)

audio_checkbox = ttk.Checkbutton(download_frame, text="Audio only", variable=audio_only, command=toggle_audio_mode)
audio_checkbox.grid(row=0, column=0, sticky="w", columnspan=2)

quality_frame = ttk.Frame(download_frame)
quality_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
quality_frame.columnconfigure(1, weight=1)

resolution_options = list(RESOLUTION_OPTIONS)
if selected_resolution not in resolution_options:
    resolution_options.insert(1, selected_resolution)
resolution_menu = tk.StringVar(root, value=selected_resolution)
resolution_label = ttk.Label(quality_frame, text="Quality")
resolution_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
resolution_dropdown = ttk.Combobox(
    quality_frame,
    textvariable=resolution_menu,
    values=resolution_options,
    state="disabled",
    width=22,
)
resolution_dropdown.grid(row=0, column=1, sticky="w")
resolution_dropdown.bind("<<ComboboxSelected>>", lambda event: set_resolution(resolution_menu.get()))

audio_format_label = ttk.Label(quality_frame, text="Format")
audio_format_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
audio_format_dropdown = ttk.Combobox(
    quality_frame,
    textvariable=selected_audio_format,
    values=AUDIO_FORMATS,
    state="disabled",
    width=22,
)
audio_format_dropdown.grid(row=0, column=1, sticky="w")
audio_format_dropdown.bind("<<ComboboxSelected>>", lambda event: save_settings())

options_frame = ttk.Frame(download_frame)
options_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

cleanup_checkbox = ttk.Checkbutton(
    options_frame,
    text="Delete temp files after download",
    variable=delete_temp_files,
    command=save_settings,
)
cleanup_checkbox.grid(row=0, column=0, sticky="w", padx=(0, 18))

timestamp_checkbox = ttk.Checkbutton(
    options_frame,
    text="Preserve upload date",
    variable=preserve_upload_date,
    command=save_settings,
)
timestamp_checkbox.grid(row=0, column=1, sticky="w")
ToolTip(timestamp_checkbox, "When enabled, downloaded files use the media's upload date for file timestamps. Turn it off to keep today's download time.")

group_multi_item_checkbox = ttk.Checkbutton(
    options_frame,
    text="Put multiple items in one folder",
    variable=group_multi_item,
    command=toggle_group_multi_item,
)
group_multi_item_checkbox.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
group_multi_item_checkbox.grid_remove()
ToolTip(group_multi_item_checkbox, "Shown for sources containing multiple media items. The preference is remembered.")
ToolTip(test_link_button, "Insert a tiny example video link.")

visible_text_frame = ttk.Frame(options_frame)
visible_text_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
visible_text_frame.columnconfigure(1, weight=1)

visible_text_checkbox = ttk.Checkbutton(
    visible_text_frame,
    text="Extract visible text from media",
    variable=extract_visible_text_enabled,
    command=toggle_visible_text_extraction,
)
visible_text_checkbox.grid(row=0, column=0, sticky="w", padx=(0, 8))
ToolTip(
    visible_text_checkbox,
    "Creates .ocr.txt files. Videos are sampled once per second, up to 300 frames.",
)

ocr_component_status_label = ttk.Label(
    visible_text_frame,
    text=ocr_component_manager.status_text(),
    foreground="#5f6368",
    font=("Segoe UI", 8),
)
ocr_component_status_label.grid(row=0, column=1, sticky="w")

remove_ocr_component_button = ttk.Button(
    visible_text_frame,
    text="Remove component",
    command=remove_ocr_component,
)
remove_ocr_component_button.grid(row=0, column=2, sticky="e")

cancel_ocr_install_button = ttk.Button(
    visible_text_frame,
    text="Cancel",
    command=cancel_ocr_component_install,
)
cancel_ocr_install_button.grid(row=0, column=3, sticky="e")

destination_frame = ttk.LabelFrame(main_frame, text="Destination", padding=10)
destination_frame.grid(row=5, column=0, sticky="ew", pady=(12, 0))
destination_frame.columnconfigure(0, weight=1)

folder_label = ttk.Label(destination_frame, text=f"Save to: {output_directory}", wraplength=680)
folder_label.grid(row=0, column=0, columnspan=2, sticky="ew")

destination_left_actions = ttk.Frame(destination_frame)
destination_left_actions.grid(row=1, column=0, sticky="w", pady=(8, 0))

folder_button = ttk.Button(destination_left_actions, text="Choose Folder", command=select_output_folder)
folder_button.grid(row=0, column=0, padx=(0, 6))

default_folder_button = ttk.Button(destination_left_actions, text="Use Downloads", command=reset_output_folder)
default_folder_button.grid(row=0, column=1)

destination_right_actions = ttk.Frame(destination_frame)
destination_right_actions.grid(row=1, column=1, sticky="e", pady=(8, 0))

open_folder_checkbox = ttk.Checkbutton(
    destination_right_actions,
    text="Open after download",
    variable=open_folder_after_download,
    command=save_settings,
)
open_folder_checkbox.grid(row=0, column=0, padx=(0, 8))
ToolTip(open_folder_checkbox, "Open the destination folder after dismissing a successful download message.")

open_folder_button = ttk.Button(destination_right_actions, text="Open Folder", command=open_download_folder)
open_folder_button.grid(row=0, column=1)

actions_frame = ttk.Frame(main_frame)
actions_frame.grid(row=6, column=0, sticky="ew", pady=(14, 0))
actions_frame.columnconfigure(0, weight=1)

download_button = tk.Button(
    actions_frame,
    text="Download",
    command=download_video_gui,
    bg="#1f8f4d",
    fg="white",
    activebackground="#18743f",
    activeforeground="white",
    disabledforeground="#d8e9df",
    padx=28,
    pady=6,
    relief=tk.RAISED,
    cursor="hand2",
)
download_button.grid(row=0, column=0)

support_frame = ttk.Frame(main_frame)
support_frame.grid(row=7, column=0, sticky="ew", pady=(8, 0))
support_frame.columnconfigure(0, weight=1)

support_inner_frame = ttk.Frame(support_frame)
support_inner_frame.grid(row=0, column=0)

support_text_label = ttk.Label(
    support_inner_frame,
    text="Enjoying the app? Support future fixes and Windows builds.",
    foreground="#666666",
    font=("Segoe UI", 8),
)

support_button = tk.Button(
    support_inner_frame,
    text=SUPPORT_LABEL,
    command=open_support_page,
    bg="#a8753d",
    fg="white",
    activebackground="#8f6333",
    activeforeground="white",
    font=("Segoe UI", 9),
    padx=10,
    pady=2,
    relief=tk.RAISED,
    cursor="hand2",
)
support_button.grid(row=0, column=0)
support_text_label.grid(row=1, column=0, pady=(4, 0))
ToolTip(support_button, "Support future releases, dependency updates, and Windows testing.")

status_frame = ttk.LabelFrame(main_frame, text="Status", padding=10)
status_frame.grid(row=8, column=0, sticky="nsew", pady=(12, 0))
status_frame.columnconfigure(0, weight=1)
status_frame.rowconfigure(2, weight=1)
main_frame.rowconfigure(8, weight=1)

status_label = ttk.Label(status_frame, text="", wraplength=680, justify=tk.LEFT)
status_label.grid(row=0, column=0, sticky="ew")

diagnostics_header = ttk.Frame(status_frame)
diagnostics_header.grid(row=1, column=0, sticky="ew", pady=(8, 0))
diagnostics_header.columnconfigure(1, weight=1)

diagnostics_button = ttk.Button(
    diagnostics_header,
    text="Show Diagnostics",
    command=toggle_diagnostics,
)
diagnostics_button.grid(row=0, column=0, sticky="w", padx=(0, 8))

diagnostics_summary_label = ttk.Label(diagnostics_header, text="Diagnostics: checking...")
diagnostics_summary_label.grid(row=0, column=1, sticky="w")

diagnostics_panel = ttk.Frame(status_frame)
diagnostics_panel.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
diagnostics_panel.columnconfigure(0, weight=1)
diagnostics_panel.rowconfigure(0, weight=1)

diagnostics_text = tk.Text(
    diagnostics_panel,
    height=6,
    wrap=tk.WORD,
    borderwidth=1,
    relief=tk.SOLID,
    font=("Consolas", 9),
)
diagnostics_text.grid(row=0, column=0, sticky="nsew")

diagnostics_scrollbar = ttk.Scrollbar(diagnostics_panel, orient=tk.VERTICAL, command=diagnostics_text.yview)
diagnostics_scrollbar.grid(row=0, column=1, sticky="ns")
diagnostics_text.configure(yscrollcommand=diagnostics_scrollbar.set, state=tk.DISABLED)
hide_diagnostics()

reset_media_preview()
toggle_audio_mode()
set_link_ready(False)
update_ocr_component_controls()
if ocr_setting_was_reset:
    save_settings()
root.protocol("WM_DELETE_WINDOW", on_close)
process_ui_queue()
run_startup_diagnostics_async()

root.mainloop()
