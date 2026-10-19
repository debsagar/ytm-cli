# Install or update ytm in one go:  irm https://raw.githubusercontent.com/debsagar/ytm-cli/main/install.ps1 | iex
# Safe to run again: it skips what is already there and updates an existing copy.
# Runs inside the caller's session (iex), so it never calls exit and keeps its settings in this block.
& {
    $ErrorActionPreference = 'Stop'
    $dir = Join-Path $env:LOCALAPPDATA 'ytm'
    $apps = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'

    function Has($names, $dirs) {
        foreach ($n in $names) {
            if (Get-Command $n -ErrorAction SilentlyContinue) { return $true }
            foreach ($d in $dirs) { if (Test-Path (Join-Path $d $n)) { return $true } }
        }
        $false
    }
    function RefreshPath {
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }

    # Same places ytm.ps1 looks: mpv's installer doesn't add itself to PATH.
    $links = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'
    $missing = @()
    if (-not (Has @('mpv.exe') @((Join-Path $env:ProgramFiles 'MPV Player'), $links))) { $missing += 'shinchiro.mpv' }
    if (-not (Has @('yt-dlp.exe') @($links))) { $missing += 'yt-dlp.yt-dlp' }
    if (-not (Has @('uv.exe') @())) { $missing += 'astral-sh.uv' }
    if (-not (Has @('git.exe') @())) { $missing += 'Git.Git' }
    # yt-dlp needs a JavaScript runtime; Node.js works too.
    if (-not (Has @('deno.exe', 'node.exe') @())) { $missing += 'DenoLand.Deno' }

    if ($missing) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Write-Host "ytm needs $($missing -join ', '), and installs them with winget, which isn't here."
            Write-Host 'Get "App Installer" from the Microsoft Store, then run this again.'
            return
        }
        foreach ($id in $missing) {
            Write-Host "Installing $id..."
            winget install -e --id $id --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE) { Write-Host "Installing $id failed (winget exit $LASTEXITCODE)."; return }
        }
        RefreshPath
    }

    if (Test-Path (Join-Path $dir '.git')) {
        Write-Host "Updating ytm in $dir..."
        & (Join-Path $dir 'ytm.cmd') update
        if ($LASTEXITCODE) { return }
    } else {
        if (Test-Path $dir) { Write-Host "$dir exists but isn't a ytm copy. Move it away, then run this again."; return }
        Write-Host "Downloading ytm to $dir..."
        git clone -q https://github.com/debsagar/ytm-cli.git $dir
        if ($LASTEXITCODE) { Write-Host 'git clone failed.'; return }
        Write-Host 'Installing Python packages...'
        uv sync -q --frozen --no-dev --directory $dir
        if ($LASTEXITCODE) { Write-Host "uv sync failed. Fix that, then run this again (or run: ytm update)."; return }
    }

    # WindowsApps is on PATH by default, so ytm works from any terminal, this one included.
    Set-Content (Join-Path $apps 'ytm.cmd') "@`"$dir\ytm.cmd`" %*" -Encoding Ascii
    Write-Host 'Done. Run: ytm'
}
