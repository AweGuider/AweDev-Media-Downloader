@echo off
setlocal EnableExtensions EnableDelayedExpansion

title AweDev OCR Component Build Script

cd /d "%~dp0"

set "COMPONENT_VERSION=1.0.0"
set "WORKER_NAME=AweDevMediaOCR"
set "OUTPUT_ZIP=AweDevMediaOCR-windows-x64-%COMPONENT_VERSION%.zip"
set "PROJECT_ROOT=%CD%"
set "BUILD_ROOT=build\components\ocr"
set "BUILD_WORK_DIR=%BUILD_ROOT%\work"
set "BUILD_SPEC_DIR=%BUILD_ROOT%\spec"
set "DIST_DIR=dist\components\ocr\%COMPONENT_VERSION%"
set "WORKER_PATH=%DIST_DIR%\%WORKER_NAME%.exe"
set "STAGE_DIR=build\package-stage\components\ocr\%COMPONENT_VERSION%"
set "RELEASE_DIR=release\components\ocr\%COMPONENT_VERSION%"
set "ZIP_PATH=%RELEASE_DIR%\%OUTPUT_ZIP%"
set "LOG_DIR=logs\build"

echo OCR component build %COMPONENT_VERSION%
echo   Worker: %WORKER_PATH%
echo   ZIP:    %ZIP_PATH%
echo.

for %%F in ("ocr_worker.py" "LICENSE" "THIRD_PARTY_NOTICES.md") do (
    if not exist "%%~F" (
        echo Required file not found: %%~F
        pause
        exit /b 1
    )
)

if exist "%WORKER_PATH%" (
    set "OVERWRITE_WORKER="
    set /p "OVERWRITE_WORKER=Executable already exists. Overwrite? [y/N]: "
    if /i not "!OVERWRITE_WORKER:~0,1!"=="y" (
        echo Build cancelled; existing executable was preserved.
        exit /b 1
    )
)
if exist "%ZIP_PATH%" (
    set "OVERWRITE_ZIP="
    set /p "OVERWRITE_ZIP=ZIP already exists. Overwrite? [Y/n]: "
    if /i "!OVERWRITE_ZIP:~0,1!"=="n" (
        echo Build cancelled; existing ZIP was preserved.
        exit /b 1
    )
)

for %%D in ("%BUILD_WORK_DIR%" "%BUILD_SPEC_DIR%" "%DIST_DIR%" "%RELEASE_DIR%" "%LOG_DIR%") do if not exist "%%~D" mkdir "%%~D"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss-fff"') do set "LOG_TIMESTAMP=%%I"
set "LOG_FILE=%LOG_DIR%\ocr-!LOG_TIMESTAMP!.txt"

python -c "import rapidocr; import onnxruntime; import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo OCR build prerequisites are missing.
    echo Run: python -m pip install -r requirements-ocr-build.txt
    pause
    exit /b 1
)

python ocr_worker.py --self-test
if errorlevel 1 (
    echo OCR dependency self-test failed.
    pause
    exit /b 1
)

python -m PyInstaller ^
    --clean ^
    --noconfirm ^
    --onefile ^
    --name "%WORKER_NAME%" ^
    --workpath "%BUILD_WORK_DIR%" ^
    --specpath "%BUILD_SPEC_DIR%" ^
    --distpath "%DIST_DIR%" ^
    --collect-all rapidocr ^
    --collect-all onnxruntime ^
    "%PROJECT_ROOT%\ocr_worker.py" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo OCR component build failed. Check %LOG_FILE% for details.
    pause
    exit /b 1
)

"%WORKER_PATH%" --self-test
if errorlevel 1 (
    echo Packaged OCR worker self-test failed.
    pause
    exit /b 1
)

if exist "%STAGE_DIR%" rmdir /s /q "%STAGE_DIR%"
mkdir "%STAGE_DIR%"
copy "%WORKER_PATH%" "%STAGE_DIR%\%WORKER_NAME%.exe" >nul
copy "LICENSE" "%STAGE_DIR%\LICENSE-AweDev.txt" >nul
copy "THIRD_PARTY_NOTICES.md" "%STAGE_DIR%\THIRD_PARTY_NOTICES.md" >nul
powershell -NoProfile -Command "$data = [ordered]@{ component='awedev-ocr'; version='%COMPONENT_VERSION%'; protocol_version=1 }; [IO.File]::WriteAllText('%STAGE_DIR%\component.json', ($data | ConvertTo-Json), [Text.UTF8Encoding]::new($false))"

if exist "%ZIP_PATH%" del /q "%ZIP_PATH%"
set "ZIP_SOURCE=%STAGE_DIR%"
set "ZIP_DESTINATION=%ZIP_PATH%"
powershell -NoProfile -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; [IO.Compression.ZipFile]::CreateFromDirectory([IO.Path]::GetFullPath($env:ZIP_SOURCE), [IO.Path]::GetFullPath($env:ZIP_DESTINATION), [IO.Compression.CompressionLevel]::Optimal, $false)" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo OCR component ZIP creation failed. Check %LOG_FILE% for details.
    pause
    exit /b 1
)

for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%ZIP_PATH%').Hash.ToLower()"') do set "COMPONENT_SHA256=%%H"
for %%F in ("%ZIP_PATH%") do set "COMPONENT_SIZE=%%~zF"
for /f %%S in ('powershell -NoProfile -Command "(Get-ChildItem -File -Recurse -LiteralPath '%STAGE_DIR%' | Measure-Object Length -Sum).Sum"') do set "INSTALLED_SIZE=%%S"
powershell -NoProfile -Command "[IO.File]::WriteAllText('%RELEASE_DIR%\SHA256SUMS.txt','%COMPONENT_SHA256%  %OUTPUT_ZIP%' + [Environment]::NewLine,[Text.UTF8Encoding]::new($false))"

echo.
echo Built %ZIP_PATH%
echo SHA-256: %COMPONENT_SHA256%
echo Download size: %COMPONENT_SIZE% bytes
echo Installed size: %INSTALLED_SIZE% bytes
echo.
set "RELEASE_TAG="
set /p "RELEASE_TAG=GitHub release tag for this component (leave blank to skip manifest): "
if defined RELEASE_TAG (
    powershell -NoProfile -Command "$data = [ordered]@{ available=$true; version='%COMPONENT_VERSION%'; protocol_version=1; url='https://github.com/AweGuider/AweDev-Media-Downloader/releases/download/%RELEASE_TAG%/%OUTPUT_ZIP%'; sha256='%COMPONENT_SHA256%'; worker='%WORKER_NAME%.exe'; download_size=[long]%COMPONENT_SIZE%; installed_size=[long]%INSTALLED_SIZE% }; [IO.File]::WriteAllText('assets\ocr-component.json', ($data | ConvertTo-Json), [Text.UTF8Encoding]::new($false))"
    echo Wrote verified release manifest: assets\ocr-component.json
)

if exist "%BUILD_ROOT%" rmdir /s /q "%BUILD_ROOT%"
if exist "%STAGE_DIR%" rmdir /s /q "%STAGE_DIR%"

echo Upload %ZIP_PATH% to the matching GitHub release before building the main application.
echo Attach all release assets before publishing an immutable release.
echo Log: %LOG_FILE%
pause
exit /b 0
