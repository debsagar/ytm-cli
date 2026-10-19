@echo off
rem ytm - minimal-RAM YouTube Music player (see ytm.ps1 for the logic).
rem PowerShell only resolves what to play and exits; this shim then starts
rem mpv, so the only things left in memory are mpv and a tiny cmd.exe.
setlocal DisableDelayedExpansion

rem No arguments: open the mini-player app (ytm\app.py) in its own small
rem Windows Terminal window. "ytm here" runs it in the current terminal.
set "YTM_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%YTM_PY%" call :setup || exit /b 1
if /i "%~1"=="here" goto app
if /i "%~1"=="import" (
    pushd "%~dp0"
    "%YTM_PY%" -m ytm.importer %*
    popd
    exit /b
)
rem One line on purpose: cmd re-reads this file as it runs, and the update replaces it.
if /i "%~1"=="update" (pushd "%~dp0" & "%YTM_PY%" -m ytm.update "%~2" & popd & exit /b)
if not "%~1"=="" goto classic
where wt >nul 2>nul || goto app
rem wt treats ";" as a command separator, so escape it in the paths it gets
set "YTM_DIR=%~dp0."
set "YTM_DIR=%YTM_DIR:;=\;%"
start "" wt -w new --size 74,24 --title ytm -d "%YTM_DIR%" "%YTM_DIR%\.venv\Scripts\python.exe" -m ytm
exit /b 0

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

rem First run: create .venv next to the code with the locked packages.
:setup
echo Setting up ytm's Python packages (first run only)...
where uv >nul 2>nul || (
    echo ytm needs uv. Install it, open a new terminal, then run ytm again:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    exit /b 1
)
uv sync -q --frozen --no-dev --directory "%~dp0."
exit /b
