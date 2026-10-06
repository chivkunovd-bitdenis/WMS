@echo off
setlocal
rem Starts the already installed Chrome in a separate profile. Installs nothing.
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined CHROME (
  echo Installed Google Chrome was not found. Nothing was installed or changed.
  pause
  exit /b 1
)
start "" "%CHROME%" --kiosk-printing "--user-data-dir=%LOCALAPPDATA%\WMS-Chrome-Print" --no-first-run --no-default-browser-check "https://sellerfocus.pro/packing-scan-check/"
