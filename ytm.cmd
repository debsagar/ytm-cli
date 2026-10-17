@echo off
rem ytm - minimal-RAM YouTube Music player (see ytm.ps1 for the logic).
rem PowerShell only resolves what to play and exits; this shim then starts
rem mpv, so the only things left in memory are mpv and a tiny cmd.exe.
setlocal DisableDelayedExpansion
set "YTM_OUT=%TEMP%\ytm-%RANDOM%-%RANDOM%.txt"
set "YTM_MPV="
set "YTM_TARGET="
set "YTM_EXTRA="

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ytm.ps1" %*
if errorlevel 1 (
    if exist "%YTM_OUT%" del "%YTM_OUT%"
    exit /b 1
)
if not exist "%YTM_OUT%" exit /b 0

rem line 1 = mpv path, line 2 = URL to play, line 3 = extra mpv options
<"%YTM_OUT%" (
    set /p "YTM_MPV="
    set /p "YTM_TARGET="
    set /p "YTM_EXTRA="
)
del "%YTM_OUT%"
if not defined YTM_TARGET exit /b 1

"%YTM_MPV%" "--config-dir=%~dp0mpv" %YTM_EXTRA% -- "%YTM_TARGET%"
exit /b %ERRORLEVEL%
