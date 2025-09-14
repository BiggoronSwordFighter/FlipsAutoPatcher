@echo off
setlocal
REM Change to the folder this BAT lives in (handles other drives too).
cd /d "%~dp0"

REM Prefer py launcher if present, otherwise fall back to python.
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py "%~dp0main.py" %*
) else (
  python "%~dp0main.py" %*
)

pause
endlocal


