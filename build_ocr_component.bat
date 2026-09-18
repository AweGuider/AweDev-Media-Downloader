@echo off
setlocal

title AweDev OCR Component Build Script

set "COMPONENT_VERSION=1.0.0"
set "WORKER_NAME=AweDevMediaOCR"
set "OUTPUT_ZIP=AweDevMediaOCR-windows-x64-%COMPONENT_VERSION%.zip"

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
    --collect-all rapidocr ^
    --collect-all onnxruntime ^
    ocr_worker.py
if errorlevel 1 (
    echo OCR component build failed.
    pause
    exit /b 1
)

if exist "ocr-component-stage" rmdir /s /q "ocr-component-stage"
mkdir "ocr-component-stage"
copy "dist\%WORKER_NAME%.exe" "ocr-component-stage\%WORKER_NAME%.exe" >nul
powershell -NoProfile -Command "$data = [ordered]@{ component='awedev-ocr'; version='%COMPONENT_VERSION%'; protocol_version=1 }; $data | ConvertTo-Json | Set-Content -Encoding UTF8 'ocr-component-stage\component.json'"
copy "LICENSE" "ocr-component-stage\LICENSE-AweDev.txt" >nul
copy "THIRD_PARTY_NOTICES.md" "ocr-component-stage\THIRD_PARTY_NOTICES.md" >nul

if exist "%OUTPUT_ZIP%" del /q "%OUTPUT_ZIP%"
tar -a -cf "%OUTPUT_ZIP%" -C "ocr-component-stage" .
if errorlevel 1 (
    echo OCR component ZIP creation failed.
    pause
    exit /b 1
)

for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 '%OUTPUT_ZIP%').Hash.ToLower()"') do set "COMPONENT_SHA256=%%H"
for %%F in ("%OUTPUT_ZIP%") do set "COMPONENT_SIZE=%%~zF"
for /f %%S in ('powershell -NoProfile -Command "(Get-ChildItem -File -Recurse 'ocr-component-stage' | Measure-Object Length -Sum).Sum"') do set "INSTALLED_SIZE=%%S"

echo.
echo Built %OUTPUT_ZIP%
echo SHA-256: %COMPONENT_SHA256%
echo Download size: %COMPONENT_SIZE% bytes
echo Installed size: %INSTALLED_SIZE% bytes
echo.
set /p "RELEASE_TAG=GitHub release tag for this component (leave blank to skip manifest): "
if not "%RELEASE_TAG%"=="" (
    powershell -NoProfile -Command "$data = [ordered]@{ available=$true; version='%COMPONENT_VERSION%'; protocol_version=1; url='https://github.com/AweGuider/AweDev-Media-Downloader/releases/download/%RELEASE_TAG%/%OUTPUT_ZIP%'; sha256='%COMPONENT_SHA256%'; worker='%WORKER_NAME%.exe'; download_size=[long]%COMPONENT_SIZE%; installed_size=[long]%INSTALLED_SIZE% }; $data | ConvertTo-Json | Set-Content -Encoding UTF8 'assets\ocr-component.json'"
    echo Wrote verified release manifest: assets\ocr-component.json
)
echo Upload the ZIP to the matching GitHub release before building the main application.
echo Attach all release assets before publishing the release as immutable.
pause
