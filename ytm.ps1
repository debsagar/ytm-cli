# ytm.ps1 - resolve what to play on YouTube Music, then hand off to mpv.
#
# Normally started through ytm.cmd: this script only resolves the target,
# writes it to the file named in %YTM_OUT% and exits, and ytm.cmd starts mpv.
# That way no PowerShell process stays in memory while music plays.
# Run directly (powershell -File ytm.ps1 ...) it starts mpv itself.
#
# Public search / playlists only: no cookies, no Google account access.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Show-Usage {
    @'
ytm - minimal-RAM YouTube Music player (audio-only mpv + yt-dlp)

  ytm <search terms>          play the top YouTube Music song result
  ytm radio <search terms>    play a 100-track mix (radio) seeded from the top result
  ytm search <search terms>   list 10 song results and pick one by number
  ytm <url>                   play a YouTube / YT Music track, album or playlist
  ytm history [count]         list recently played tracks (default 20) and pick one
  ytm stop                    stop a running player

Anything starting with -- is passed straight to mpv, e.g.
  ytm --volume=40 --shuffle radio daft punk

Keys while playing:
  space  pause/resume        q      quit
  n / >  next track          p / <  previous track
  + / 0  volume up           - / 9  volume down        m  mute
  right / left  seek 5 s     up / down  seek 1 min     s  toggle shuffle
'@ | Write-Host
}

function Find-Exe([string[]]$names, [string[]]$extraDirs) {
    foreach ($n in $names) {
        $c = Get-Command $n -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c) { return $c.Source }
    }
    foreach ($d in $extraDirs) {
        foreach ($n in $names) {
            $p = Join-Path $d $n
            if (Test-Path -LiteralPath $p) { return $p }
        }
    }
    return $null
}

function Fail([string]$msg) {
    [Console]::Error.WriteLine("ytm: $msg")
    exit 1
}

# ---- split arguments: --options go to mpv, the rest is the request ----
$mpvOpts = @()
$words = @()
foreach ($a in $args) {
    if ("$a".StartsWith('--')) { $mpvOpts += "$a" } else { $words += "$a" }
}
if ($words.Count -eq 0) { Show-Usage; exit 0 }

$mode = 'play'
switch ($words[0].ToLower()) {
    'help'   { Show-Usage; exit 0 }
    '-h'     { Show-Usage; exit 0 }
    '/?'     { Show-Usage; exit 0 }
    'stop'   {
        Get-Process mpv -ErrorAction SilentlyContinue | Stop-Process -Force
        exit 0
    }
    'radio'  { $mode = 'radio' }
    'search' { $mode = 'search' }
    'history' { $mode = 'history' }
}
if ($mode -eq 'radio' -or $mode -eq 'search') {
    if ($words.Count -lt 2) { Fail "'$mode' needs search terms" }
    $words = $words[1..($words.Count - 1)]
}
$query = ($words -join ' ').Trim()

# ---- locate tools ----
$localBin  = Join-Path $here 'bin'
$wingetBin = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links'
$mpv  = Find-Exe @('mpv.com', 'mpv.exe') @($localBin, (Join-Path $env:ProgramFiles 'MPV Player'), $wingetBin)
$ytdl = Find-Exe @('yt-dlp.exe') @($localBin, $wingetBin)
if (-not $mpv)  { Fail 'mpv not found (winget install shinchiro.mpv)' }
if (-not $ytdl) { Fail 'yt-dlp not found (winget install yt-dlp.yt-dlp)' }

$oldEnc = [Console]::OutputEncoding
$oem    = [Text.Encoding]::GetEncoding($oldEnc.CodePage)

# Returns objects {Id, Title} for a query; YT Music "songs" first, plain YouTube as fallback.
function Search-Songs([string]$q, [int]$count) {
    $sources = @(
        ('https://music.youtube.com/search?q=' + [Uri]::EscapeDataString($q) + '#songs'),
        ("ytsearch${count}:" + $q)
    )
    foreach ($src in $sources) {
        $lines = @()
        try {
            [Console]::OutputEncoding = [Text.Encoding]::UTF8
            $ErrorActionPreference = 'Continue'
            $lines = @(& $ytdl --flat-playlist --playlist-end $count --no-warnings --encoding utf-8 `
                    --js-runtimes node --print "%(id)s`t%(title)s" -- $src 2>$null)
        } finally {
            $ErrorActionPreference = 'Stop'
            [Console]::OutputEncoding = $oldEnc
        }
        $found = @()
        foreach ($l in $lines) {
            $parts = "$l".Split("`t", 2)
            if ($parts.Count -eq 2 -and $parts[0] -match '^[\w-]{11}$') {
                $found += New-Object psobject -Property @{ Id = $parts[0]; Title = $parts[1] }
            }
        }
        if ($found.Count -gt 0) { return $found }
    }
    return @()
}

# ---- resolve the target URL ----
$isUrl = $query -match '^(https?://|(www\.|music\.|m\.)?youtu(be\.com|\.be)/)'
if ($mode -eq 'history') {
    # history.tsv is written by mpv\scripts\history.lua: time <TAB> url <TAB> title
    $histFile = Join-Path $here 'mpv\history.tsv'
    $count = 20
    if ($words.Count -ge 2 -and $words[1] -match '^\d+$' -and [int]$words[1] -ge 1) { $count = [int]$words[1] }
    $entries = @()
    if (Test-Path -LiteralPath $histFile) {
        $lines = @([IO.File]::ReadAllLines($histFile, [Text.Encoding]::UTF8))
        $seen = @{}
        for ($i = $lines.Count - 1; $i -ge 0 -and $entries.Count -lt $count; $i--) {
            $parts = $lines[$i].Split("`t", 3)
            if ($parts.Count -eq 3 -and -not $seen.ContainsKey($parts[1])) {
                $seen[$parts[1]] = $true
                $entries += New-Object psobject -Property @{ When = $parts[0]; Url = $parts[1]; Title = $parts[2] }
            }
        }
    }
    if ($entries.Count -eq 0) { Write-Host 'No history yet.'; exit 0 }
    for ($i = 0; $i -lt $entries.Count; $i++) {
        Write-Host ('{0,3}. {1}  {2}' -f ($i + 1), $entries[$i].When, $entries[$i].Title)
    }
    $answer = Read-Host 'Play number (r<number> for radio, Enter to cancel)'
    if ($answer -match '^\s*(r?)\s*(\d+)\s*$' -and [int]$Matches[2] -ge 1 -and [int]$Matches[2] -le $entries.Count) {
        $wantRadio = [bool]$Matches[1]
        $pick = $entries[[int]$Matches[2] - 1]
    } else {
        exit 0
    }
    $mode = 'play'
    $target = $pick.Url
    if ($wantRadio) {
        if ($pick.Url -notmatch '[?&]v=([\w-]{11})') { Fail 'radio needs a single track; that entry has no video id' }
        $mode = 'radio'
        $target = 'https://music.youtube.com/watch?v=' + $Matches[1] + '&list=RDAMVM' + $Matches[1]
        Write-Host "Radio from: $($pick.Title)"
    } else {
        Write-Host "Playing: $($pick.Title)"
    }
}
elseif ($isUrl -and $mode -eq 'play') {
    $target = $query
    if ($target -notmatch '^https?://') { $target = 'https://' + $target }
    Write-Host "Playing $target"
}
else {
    if ($isUrl) { Fail "'$mode' takes search terms, not a URL" }
    $n = 1
    if ($mode -eq 'search') { $n = 10 }
    Write-Host "Searching YouTube Music for '$query' ..."
    $results = @(Search-Songs $query $n)
    if ($results.Count -eq 0) { Fail "no results for '$query'" }

    $pick = $results[0]
    if ($mode -eq 'search') {
        for ($i = 0; $i -lt $results.Count; $i++) {
            Write-Host ('{0,3}. {1}' -f ($i + 1), $results[$i].Title)
        }
        $answer = Read-Host 'Play number (r<number> for radio, Enter to cancel)'
        if ($answer -match '^\s*(r?)\s*(\d+)\s*$' -and [int]$Matches[2] -ge 1 -and [int]$Matches[2] -le $results.Count) {
            if ($Matches[1]) { $mode = 'radio' }
            $pick = $results[[int]$Matches[2] - 1]
        } else {
            exit 0
        }
    }

    $target = 'https://music.youtube.com/watch?v=' + $pick.Id
    if ($mode -eq 'radio') {
        $target += '&list=RDAMVM' + $pick.Id
        Write-Host "Radio from: $($pick.Title)"
    } else {
        Write-Host "Playing: $($pick.Title)"
    }
}

# ---- hand off to mpv ----
$extra = @("--script-opts=ytdl_hook-ytdl_path=$ytdl")
# mpv's ytdl hook passes --no-playlist for watch?v=..&list=.. URLs unless told otherwise.
# The mix is capped at 100 tracks: uncapped it is ~700 entries and takes ~20 s to load.
if ($mode -eq 'radio') {
    $extra += '--ytdl-raw-options-append=yes-playlist='
    $extra += '--ytdl-raw-options-append=playlist-end=100'
}
$extra += $mpvOpts

if ($env:YTM_OUT) {
    # ytm.cmd reads these three lines and starts mpv after this process exits.
    $quoted = ($extra | ForEach-Object { '"' + ($_ -replace '"', '') + '"' }) -join ' '
    [IO.File]::WriteAllLines($env:YTM_OUT, @($mpv, $target, $quoted), $oem)
    exit 0
}

& $mpv "--config-dir=$(Join-Path $here 'mpv')" @extra '--' $target
exit $LASTEXITCODE
