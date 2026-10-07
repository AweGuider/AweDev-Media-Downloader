@echo off
setlocal

title AweDev Transcription Component Build Script

set "COMPONENT_VERSION=1.0.0"
set "WORKER_NAME=AweDevMediaTranscription"
set "OUTPUT_ZIP=AweDevMediaTranscription-windows-x64-%COMPONENT_VERSION%.zip"
set "RUNTIME_DIR=transcription-runtime"
set "MODEL_NAME=ggml-base-q5_1.bin"
set "VAD_MODEL_NAME=ggml-silero-v6.2.0.bin"

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Transcription build prerequisites are missing.
    echo Run: python -m pip install -r requirements-transcription-build.txt
    pause
    exit /b 1
)

for %%F in (
    whisper-cli.exe
    %MODEL_NAME%
    %VAD_MODEL_NAME%
    LICENSE-whisper.cpp.txt
    LICENSE-Whisper-model.txt
    LICENSE-Silero-VAD.txt
) do (
    if not exist "%RUNTIME_DIR%\%%F" (
        echo Missing required runtime file: %RUNTIME_DIR%\%%F
        echo See README.md for transcription component preparation.
        pause
        exit /b 1
    )
)

python -m PyInstaller ^
    --clean ^
    --noconfirm ^
    --onefile ^
    --name "%WORKER_NAME%" ^
    transcription_worker.py
if errorlevel 1 (
    echo Transcription component worker build failed.
    pause
    exit /b 1
)

if exist "transcription-component-stage" rmdir /s /q "transcription-component-stage"
mkdir "transcription-component-stage"
copy "dist\%WORKER_NAME%.exe" "transcription-component-stage\%WORKER_NAME%.exe" >nul
copy "%RUNTIME_DIR%\whisper-cli.exe" "transcription-component-stage\whisper-cli.exe" >nul
copy "%RUNTIME_DIR%\*.dll" "transcription-component-stage\" >nul 2>&1
copy "%RUNTIME_DIR%\%MODEL_NAME%" "transcription-component-stage\%MODEL_NAME%" >nul
copy "%RUNTIME_DIR%\%VAD_MODEL_NAME%" "transcription-component-stage\%VAD_MODEL_NAME%" >nul
copy "%RUNTIME_DIR%\LICENSE-*.txt" "transcription-component-stage\" >nul
copy "LICENSE" "transcription-component-stage\LICENSE-AweDev.txt" >nul
copy "THIRD_PARTY_NOTICES.md" "transcription-component-stage\THIRD_PARTY_NOTICES.md" >nul
powershell -NoProfile -Command "$data = [ordered]@{ component='awedev-transcription'; version='%COMPONENT_VERSION%'; protocol_version=1 }; [IO.File]::WriteAllText('transcription-component-stage\component.json', ($data | ConvertTo-Json), [Text.UTF8Encoding]::new($false))"

"transcription-component-stage\%WORKER_NAME%.exe" --self-test
if errorlevel 1 (
    echo Transcription component self-test failed.
    pause
    exit /b 1
)

if exist "%OUTPUT_ZIP%" del /q "%OUTPUT_ZIP%"
tar -a -cf "%OUTPUT_ZIP%" -C "transcription-component-stage" .
if errorlevel 1 (
    echo Transcription component ZIP creation failed.
    pause
    exit /b 1
)

for /f %%H in ('python -c "import hashlib; print(hashlib.sha256(open(r'%OUTPUT_ZIP%', 'rb').read()).hexdigest())"') do set "COMPONENT_SHA256=%%H"
for %%F in ("%OUTPUT_ZIP%") do set "COMPONENT_SIZE=%%~zF"
for /f %%S in ('powershell -NoProfile -Command "(Get-ChildItem -File -Recurse 'transcription-component-stage' | Measure-Object Length -Sum).Sum"') do set "INSTALLED_SIZE=%%S"

echo.
echo Built %OUTPUT_ZIP%
echo SHA-256: %COMPONENT_SHA256%
echo Download size: %COMPONENT_SIZE% bytes
echo Installed size: %INSTALLED_SIZE% bytes
echo.
set /p "RELEASE_TAG=GitHub release tag for this component (leave blank to skip manifest): "
if not "%RELEASE_TAG%"=="" (
    powershell -NoProfile -Command "$data = [ordered]@{ available=$true; version='%COMPONENT_VERSION%'; protocol_version=1; url='https://github.com/AweGuider/AweDev-Media-Downloader/releases/download/%RELEASE_TAG%/%OUTPUT_ZIP%'; sha256='%COMPONENT_SHA256%'; worker='%WORKER_NAME%.exe'; download_size=[long]%COMPONENT_SIZE%; installed_size=[long]%INSTALLED_SIZE% }; [IO.File]::WriteAllText('assets\transcription-component.json', ($data | ConvertTo-Json), [Text.UTF8Encoding]::new($false))"
    echo Wrote verified release manifest: assets\transcription-component.json
)
echo Upload the ZIP to the matching GitHub release before building the main application.
pause
