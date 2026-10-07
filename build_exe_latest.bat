@echo off
setlocal EnableExtensions EnableDelayedExpansion

title AweDev Media Downloader Build Script

cd /d "%~dp0"

set "SOURCE=downloader.py"
set "ICON_PATH=assets\app.ico"
set "PROJECT_ROOT=%CD%"

for /f "tokens=3" %%V in ('findstr /b /c:"APP_VERSION = " "%SOURCE%"') do set "APP_VERSION=%%~V"
if not defined APP_VERSION (
    echo Could not read APP_VERSION from %SOURCE%.
    pause
    exit /b 1
)

set "DEFAULT_FILE_NAME=AweDevMediaDownloader_v%APP_VERSION%"
set "DEFAULT_ZIP_BASE=AweDevMediaDownloader-v%APP_VERSION%-windows-x64"
set "RELEASE_NOTES=docs\release-notes\v%APP_VERSION%.md"
set "BUILD_ROOT=build\app"
set "BUILD_WORK_DIR=%BUILD_ROOT%\work"
set "BUILD_SPEC_DIR=%BUILD_ROOT%\spec"
set "DIST_DIR=dist\app\%APP_VERSION%"
set "STAGE_DIR=build\package-stage\app\%APP_VERSION%"
set "RELEASE_DIR=release\app\%APP_VERSION%"
set "LOG_DIR=logs\build"

echo Detected app version: %APP_VERSION%
echo.

set "FILE_NAME=%DEFAULT_FILE_NAME%"
set "FILE_INPUT="
set /p "FILE_INPUT=Executable name [%DEFAULT_FILE_NAME%]: "
if defined FILE_INPUT set "FILE_NAME=!FILE_INPUT!"
if /i "!FILE_NAME:~-4!"==".exe" set "FILE_NAME=!FILE_NAME:~0,-4!"
set "NAME_TO_VALIDATE=!FILE_NAME!"
call :validate_name
if errorlevel 1 (
    echo Invalid executable name: !FILE_NAME!
    pause
    exit /b 1
)

set "DO_ZIP=true"
set "DO_ZIP_INPUT="
set /p "DO_ZIP_INPUT=Create ZIP package? [Y/n]: "
if /i "!DO_ZIP_INPUT:~0,1!"=="n" set "DO_ZIP=false"

if "!DO_ZIP!"=="true" (
    set "ZIP_BASE=%DEFAULT_ZIP_BASE%"
    set "ZIP_INPUT="
    set /p "ZIP_INPUT=ZIP name without .zip [%DEFAULT_ZIP_BASE%]: "
    if defined ZIP_INPUT set "ZIP_BASE=!ZIP_INPUT!"
    if /i "!ZIP_BASE:~-4!"==".zip" set "ZIP_BASE=!ZIP_BASE:~0,-4!"
    set "NAME_TO_VALIDATE=!ZIP_BASE!"
    call :validate_name
    if errorlevel 1 (
        echo Invalid ZIP name: !ZIP_BASE!
        pause
        exit /b 1
    )
    set "ZIP_NAME=!ZIP_BASE!.zip"
    set "ZIP_PATH=%RELEASE_DIR%\!ZIP_NAME!"
)

set "EXE_PATH=%DIST_DIR%\!FILE_NAME!.exe"

echo.
echo Build plan:
echo   EXE: !EXE_PATH!
if "!DO_ZIP!"=="true" (
    echo   ZIP: !ZIP_PATH!
    echo   Package files: EXE, README.md, LICENSE, THIRD_PARTY_NOTICES.md, RELEASE_NOTES.md
)
echo.
set "CONTINUE_INPUT="
set /p "CONTINUE_INPUT=Continue? [Y/n]: "
if /i "!CONTINUE_INPUT:~0,1!"=="n" exit /b 0

for %%F in ("%SOURCE%" "%ICON_PATH%" "README.md" "LICENSE" "THIRD_PARTY_NOTICES.md" "%RELEASE_NOTES%") do (
    if not exist "%%~F" (
        echo Required file not found: %%~F
        pause
        exit /b 1
    )
)

call :validate_component_manifest "assets\ocr-component.json"
if errorlevel 1 exit /b 1
call :validate_component_manifest "assets\transcription-component.json"
if errorlevel 1 exit /b 1

if exist "!EXE_PATH!" (
    set "OVERWRITE_EXE="
    set /p "OVERWRITE_EXE=Executable already exists. Overwrite? [y/N]: "
    if /i not "!OVERWRITE_EXE:~0,1!"=="y" (
        echo Build cancelled; existing executable was preserved.
        exit /b 1
    )
)

if "!DO_ZIP!"=="true" if exist "!ZIP_PATH!" (
    set "OVERWRITE_ZIP="
    set /p "OVERWRITE_ZIP=ZIP already exists. Overwrite? [Y/n]: "
    if /i "!OVERWRITE_ZIP:~0,1!"=="n" (
        echo Build cancelled; existing ZIP was preserved.
        exit /b 1
    )
)

for %%D in ("%BUILD_WORK_DIR%" "%BUILD_SPEC_DIR%" "%DIST_DIR%" "%LOG_DIR%") do if not exist "%%~D" mkdir "%%~D"
if "!DO_ZIP!"=="true" if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss-fff"') do set "LOG_TIMESTAMP=%%I"
set "LOG_FILE=%LOG_DIR%\app-!LOG_TIMESTAMP!.txt"

echo Checking Python build prerequisites...
python -c "import tkinter as tk; tk.Tcl(); import curl_cffi; import instaloader; import yt_dlp; import yt_dlp_ejs; import PIL; import PyInstaller" >> "!LOG_FILE!" 2>&1
if errorlevel 1 (
    echo Python build prerequisite check failed. Check !LOG_FILE! for details.
    echo Repair Python Tcl/Tk support or use a Python installation with working Tkinter, then rerun this script.
    pause
    exit /b 1
)

call :resolve_tool ffmpeg FFMPEG_PATH
if errorlevel 1 goto missing_prerequisite
call :resolve_tool ffprobe FFPROBE_PATH
if errorlevel 1 goto missing_prerequisite

set "JS_RUNTIME_NAME="
set "JS_RUNTIME_PATH="
call :resolve_tool deno DENO_PATH
if not errorlevel 1 (
    call :is_readable "!DENO_PATH!"
    if not errorlevel 1 (
        set "JS_RUNTIME_NAME=deno"
        set "JS_RUNTIME_PATH=!DENO_PATH!"
    )
)
if not defined JS_RUNTIME_PATH (
    call :resolve_tool node NODE_PATH
    if errorlevel 1 goto missing_prerequisite
    call :is_readable "!NODE_PATH!"
    if errorlevel 1 goto missing_prerequisite
    set "JS_RUNTIME_NAME=node"
    set "JS_RUNTIME_PATH=!NODE_PATH!"
)

echo Runtime tools:
echo   ffmpeg:     !FFMPEG_PATH!
echo   ffprobe:    !FFPROBE_PATH!
echo   JS runtime: !JS_RUNTIME_NAME! at !JS_RUNTIME_PATH!
echo.
echo Building executable...

python -m PyInstaller ^
    --clean ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "!FILE_NAME!" ^
    --icon "%PROJECT_ROOT%\%ICON_PATH%" ^
    --workpath "%BUILD_WORK_DIR%" ^
    --specpath "%BUILD_SPEC_DIR%" ^
    --distpath "%DIST_DIR%" ^
    --add-data "%PROJECT_ROOT%\assets;assets" ^
    --add-binary "!FFMPEG_PATH!;." ^
    --add-binary "!FFPROBE_PATH!;." ^
    --add-binary "!JS_RUNTIME_PATH!;." ^
    --hidden-import yt_dlp_ejs ^
    --collect-data yt_dlp_ejs ^
    --collect-submodules yt_dlp_ejs ^
    --collect-all curl_cffi ^
    --copy-metadata yt-dlp ^
    --copy-metadata yt-dlp-ejs ^
    --copy-metadata instaloader ^
    --copy-metadata curl-cffi ^
    "%PROJECT_ROOT%\%SOURCE%" >> "!LOG_FILE!" 2>&1
if errorlevel 1 (
    echo Build failed. Check !LOG_FILE! for details.
    pause
    exit /b 1
)

for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '!EXE_PATH!').Hash.ToLower()"') do set "EXE_SHA256=%%H"

if "!DO_ZIP!"=="true" (
    if exist "%STAGE_DIR%" rmdir /s /q "%STAGE_DIR%"
    mkdir "%STAGE_DIR%"
    copy "!EXE_PATH!" "%STAGE_DIR%\!FILE_NAME!.exe" >nul
    copy "README.md" "%STAGE_DIR%\README.md" >nul
    copy "LICENSE" "%STAGE_DIR%\LICENSE" >nul
    copy "THIRD_PARTY_NOTICES.md" "%STAGE_DIR%\THIRD_PARTY_NOTICES.md" >nul
    copy "%RELEASE_NOTES%" "%STAGE_DIR%\RELEASE_NOTES.md" >nul

    if exist "!ZIP_PATH!" del /q "!ZIP_PATH!"
    set "ZIP_SOURCE=%STAGE_DIR%"
    set "ZIP_DESTINATION=!ZIP_PATH!"
    powershell -NoProfile -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; [IO.Compression.ZipFile]::CreateFromDirectory([IO.Path]::GetFullPath($env:ZIP_SOURCE), [IO.Path]::GetFullPath($env:ZIP_DESTINATION), [IO.Compression.CompressionLevel]::Optimal, $false)" >> "!LOG_FILE!" 2>&1
    if errorlevel 1 (
        echo ZIP creation failed. The executable remains at !EXE_PATH!.
        echo Check !LOG_FILE! for details.
        pause
        exit /b 1
    )
    for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '!ZIP_PATH!').Hash.ToLower()"') do set "ZIP_SHA256=%%H"
    powershell -NoProfile -Command "[IO.File]::WriteAllText('%RELEASE_DIR%\SHA256SUMS.txt','!ZIP_SHA256!  !ZIP_NAME!' + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))"
)

if exist "%BUILD_ROOT%" rmdir /s /q "%BUILD_ROOT%"
if exist "%STAGE_DIR%" rmdir /s /q "%STAGE_DIR%"

echo.
echo Build complete.
echo   EXE: !EXE_PATH!
echo   EXE SHA-256: !EXE_SHA256!
if "!DO_ZIP!"=="true" (
    echo   ZIP: !ZIP_PATH!
    echo   ZIP SHA-256: !ZIP_SHA256!
    echo   Checksums: %RELEASE_DIR%\SHA256SUMS.txt
)
echo   Log: !LOG_FILE!
pause
exit /b 0

:validate_name
powershell -NoProfile -Command "$name=$env:NAME_TO_VALIDATE; if ([string]::IsNullOrWhiteSpace($name) -or $name.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) { exit 1 }"
exit /b %errorlevel%

:validate_component_manifest
if not exist "%~1" exit /b 0
powershell -NoProfile -Command "$path='%~1'; try { $m=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json; if (-not $m.available -or $m.protocol_version -ne 1 -or $m.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or $m.url -notmatch '^https://github.com/AweGuider/AweDev-Media-Downloader/releases/download/') { throw 'invalid release manifest' }; if ($m.url -match '(?i)(?:^|[-_/])(rc|preview|beta)[0-9-]*(?:[-_/]|$)') { Write-Warning ($path + ' still points to a pre-release URL: ' + $m.url) } } catch { Write-Host ('Invalid component manifest ' + $path + ': ' + $_.Exception.Message); exit 1 }"
exit /b %errorlevel%

:missing_prerequisite
echo Missing or unreadable release build prerequisite.
echo Ensure ffmpeg, ffprobe, and Node or Deno are available, then rerun this script.
pause
exit /b 1

:resolve_tool
set "%~2="
for /f "delims=" %%I in ('where %~1 2^>nul') do if not defined %~2 set "%~2=%%I"
if not defined %~2 (
    for /f "delims=" %%I in ('powershell -NoProfile -Command "$cmd = Get-Command -Name '%~1' -ErrorAction SilentlyContinue; if ($cmd) { $cmd.Source }" 2^>nul') do if not defined %~2 set "%~2=%%I"
)
if not defined %~2 exit /b 1
exit /b 0

:is_readable
powershell -NoProfile -Command "try { $s=[IO.File]::Open('%~1',[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite); $s.Dispose(); exit 0 } catch { exit 1 }"
exit /b %errorlevel%
