@echo off
cd /d "%~dp0"

REM ==== Pre-build file checks ====
if not exist "flips\flips.exe" (
    echo ERROR: Required file "flips\flips.exe" not found.
    echo Build aborted.
    pause
    exit /b 1
)

if not exist "ico\flips.ico" (
    echo ERROR: Required file "ico\flips.ico" not found.
    echo Build aborted.
    pause
    exit /b 1
)

REM ==== Clean previous builds ====
rmdir /s /q build
rmdir /s /q dist

REM ==== Build ONEDIR executable ====
pyinstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --icon=ico/flips.ico ^
    --add-data "ico;ico" ^
    --add-data "flips;flips" ^
    --name "FlipsAutoPatcher-v2.0.0" ^
    main.py

echo.
echo Build complete!
pause
