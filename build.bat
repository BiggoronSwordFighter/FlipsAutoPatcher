@echo off
cd /d "%~dp0"

REM Clean previous builds
rmdir /s /q build
rmdir /s /q dist

REM Build ONEDIR executable
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