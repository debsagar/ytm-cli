@echo off
rem ytm - minimal-RAM YouTube Music player (see ytm.ps1 for the logic).
rem PowerShell only resolves what to play and exits; this shim then starts
rem mpv, so the only things left in memory are mpv and a tiny cmd.exe.
setlocal DisableDelayedExpansion

rem No arguments: open the mini-player app (ytm\app.py) in its own small
rem Windows Terminal window. "ytm here" runs it in the current terminal.
set "YTM_PY=%USERPROFILE%\.venvs\ytm\Scripts\python.exe"
if /i "%~1"=="here" goto app
if /i "%~1"=="import" (
    pushd "%~dp0"
    "%YTM_PY%" -m ytm.importer %*
    popd
    exit /b
)
if /i "%~1"=="proto" goto proto
if not "%~1"=="" goto classic
where wt >nul 2>nul || goto app
rem wt treats ";" as a command separator, so escape it in the folder path
set "YTM_DIR=%~dp0."
set "YTM_DIR=%YTM_DIR:;=\;%"
start "" wt -w new --size 74,24 --title ytm -d "%YTM_DIR%" "%YTM_PY%" -m ytm
exit /b 0

:proto
rem dev only: the widget dashboard prototype (dev\proto.py) in a bigger window
where wt >nul 2>nul || goto proto_here
set "YTM_DIR=%~dp0."
set "YTM_DIR=%YTM_DIR:;=\;%"
start "" wt -w new --size 120,34 --title "ytm proto" -d "%YTM_DIR%" "%YTM_PY%" dev\proto.py
exit /b 0
:proto_here
pushd "%~dp0"
"%YTM_PY%" dev\proto.py
popd
exit /b

:app
pushd "%~dp0"
"%YTM_PY%" -m ytm
popd
exit /b

:classic
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
