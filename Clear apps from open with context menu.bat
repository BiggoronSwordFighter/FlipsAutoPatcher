@echo off

# Put the name of the files that you wish to remove here.
set APPS=FlipsAutoPatcher-v2.0.0.exe file2.exe file3.exe 

echo Remove Flips entries from Windows 11 Open With Context Menu?
echo.
set /p CONFIRM=Are you sure you want to continue? (Y/N): 
if /i not "%CONFIRM%"=="Y" (
    exit /b
)

echo.
for %%A in (%APPS%) do (

  echo Removing %%A ...

  :: App Paths (WIN11 PRIMARY SOURCE)
  reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\%%A" /f >nul 2>&1
  reg delete "HKLM\Software\Microsoft\Windows\CurrentVersion\App Paths\%%A" /f >nul 2>&1

  :: Applications
  reg delete "HKCU\Software\Classes\Applications\%%A" /f >nul 2>&1
  reg delete "HKLM\Software\Classes\Applications\%%A" /f >nul 2>&1
  reg delete "HKCR\Applications\%%A" /f >nul 2>&1

  :: OpenWithProgids (all files)
  reg delete "HKCR\*\OpenWithProgids" /v %%A /f >nul 2>&1

)

:: Clear Explorer cache
taskkill /f /im explorer.exe >nul
start explorer.exe

echo Done. Entries should now be GONE.
pause

