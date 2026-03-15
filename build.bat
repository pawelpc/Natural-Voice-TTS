@echo off
setlocal enabledelayedexpansion

:: --- Build log: tee all output to build.log ---
set "BUILD_LOG=%~dp0build.log"
if "%BUILD_LOGGED%"=="" (
    set "BUILD_LOGGED=1"
    cmd /c "%~f0" %* 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%BUILD_LOG%'"
    exit /b %ERRORLEVEL%
)

echo ============================================================
echo   Natural Voice TTS - Build Script
echo ============================================================
echo   Started: %DATE% %TIME%
echo.

:: --- Step 0: Check prerequisites ---
echo [1/6] Checking prerequisites...

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    goto :error
)
echo   - Python: OK

:: Check PyInstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not found. Install with:
    echo   pip install pyinstaller
    goto :error
)
echo   - PyInstaller: OK

:: Check Inno Setup
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if "!ISCC!"=="" (
    echo WARNING: Inno Setup 6 not found.
    echo   Download from: https://jrsoftware.org/isdl.php
    echo   The build will continue but the installer will not be created.
    echo.
) else (
    echo   - Inno Setup: OK
)

:: Check espeak-ng
set "ESPEAK_DIR="
if exist "C:\Program Files\eSpeak NG\espeak-ng.exe" (
    set "ESPEAK_DIR=C:\Program Files\eSpeak NG"
) else if exist "C:\Program Files (x86)\eSpeak NG\espeak-ng.exe" (
    set "ESPEAK_DIR=C:\Program Files (x86)\eSpeak NG"
)
if "!ESPEAK_DIR!"=="" (
    echo ERROR: espeak-ng not found. Install from:
    echo   https://github.com/espeak-ng/espeak-ng/releases
    goto :error
)
echo   - espeak-ng: OK (!ESPEAK_DIR!)
echo.

:: --- Step 1: Download all Kokoro voice files ---
echo [2/6] Downloading all Kokoro voice files (if not cached)...
python -c "from huggingface_hub import hf_hub_download; voices=['af_alloy','af_aoede','af_bella','af_heart','af_jessica','af_kore','af_nicole','af_nova','af_river','af_sarah','af_sky','am_adam','am_echo','am_eric','am_fenrir','am_liam','am_michael','am_onyx','am_puck','bf_alice','bf_emma','bf_isabella','bf_lily','bm_daniel','bm_fable','bm_george','bm_lewis']; [print(f'  Downloaded: {v}') or hf_hub_download('hexgrad/Kokoro-82M', f'voices/{v}.pt') for v in voices]; print(f'  All {len(voices)} voices ready')"
if errorlevel 1 (
    echo WARNING: Could not download all voice files. Some voices may not work offline.
)
echo.

:: --- Step 2: Run PyInstaller ---
echo [3/6] Running PyInstaller (this may take several minutes)...
python -m PyInstaller naturalvoicetts.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller failed. Check build.log for details.
    goto :error
)
echo   - PyInstaller: OK
echo.

:: --- Step 3: Copy espeak-ng into dist ---
echo [4/6] Copying espeak-ng files...
set "DIST_DIR=dist\NaturalVoiceTTS"
set "ESPEAK_DEST=%DIST_DIR%\espeak-ng"

if not exist "%ESPEAK_DEST%" mkdir "%ESPEAK_DEST%"
xcopy /E /I /Y "!ESPEAK_DIR!" "%ESPEAK_DEST%" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy espeak-ng files.
    goto :error
)
echo   - espeak-ng copied to %ESPEAK_DEST%
echo.

:: --- Step 4: Copy Kokoro model files ---
echo [5/6] Copying Kokoro model files...

:: Find the kokoro model directory in HuggingFace cache
set "HF_CACHE=%USERPROFILE%\.cache\huggingface\hub"
set "KOKORO_MODEL_DIR="

:: Search for kokoro model snapshot directory
for /d %%d in ("%HF_CACHE%\models--hexgrad--Kokoro-82M\snapshots\*") do (
    if exist "%%d\config.json" (
        set "KOKORO_MODEL_DIR=%%d"
    )
)

if "!KOKORO_MODEL_DIR!"=="" (
    echo WARNING: Kokoro model files not found in HuggingFace cache.
    echo   Expected location: %HF_CACHE%\models--hexgrad--Kokoro-82M\
    echo   Run the app once from source first to download the model.
    echo.
) else (
    echo   Found model at: !KOKORO_MODEL_DIR!

    set "MODEL_DEST=%DIST_DIR%\kokoro_model"
    if not exist "!MODEL_DEST!" mkdir "!MODEL_DEST!"

    :: Copy model weights and config
    if exist "!KOKORO_MODEL_DIR!\config.json" (
        copy /Y "!KOKORO_MODEL_DIR!\config.json" "!MODEL_DEST!\" >nul
        echo   Copied config.json
    )
    for %%f in ("!KOKORO_MODEL_DIR!\*.pth") do (
        echo   Copying %%~nxf ...
        copy /Y "%%f" "!MODEL_DEST!\" >nul
    )

    :: Copy ALL voice files
    if exist "!KOKORO_MODEL_DIR!\voices" (
        if not exist "!MODEL_DEST!\voices" mkdir "!MODEL_DEST!\voices"
        set "VOICE_COUNT=0"
        for %%f in ("!KOKORO_MODEL_DIR!\voices\*.pt") do (
            copy /Y "%%f" "!MODEL_DEST!\voices\" >nul
            set /a VOICE_COUNT+=1
        )
        echo   Copied !VOICE_COUNT! voice files
    )

    echo   - Model files copied to !MODEL_DEST!
)
echo.

:: --- Step 5: Build installer (if Inno Setup is available) ---
if not "!ISCC!"=="" (
    echo [6/6] Building installer with Inno Setup...
    "!ISCC!" installer\setup.iss
    if errorlevel 1 (
        echo ERROR: Inno Setup compiler failed. Check build.log for details.
        goto :error
    )
    echo   - Installer created successfully
) else (
    echo [6/6] Skipping installer (Inno Setup not found^)
)
echo.

:: --- Done ---
echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo.
echo   App folder:  %CD%\dist\NaturalVoiceTTS\
echo   Executable:  %CD%\dist\NaturalVoiceTTS\NaturalVoiceTTS.exe

if not "!ISCC!"=="" (
    echo   Installer:   %CD%\dist\NaturalVoiceTTS_Setup_1.0.0.exe
)

echo   Build log:   %BUILD_LOG%
echo.

:: Show size
for /f "tokens=3" %%s in ('dir /s "%DIST_DIR%" ^| findstr "File(s)"') do (
    echo   Total size:  %%s bytes
)
echo.

echo   Finished: %DATE% %TIME%
goto :end

:error
echo.
echo BUILD FAILED. See build.log for details.
echo   Finished: %DATE% %TIME%
exit /b 1

:end
endlocal
