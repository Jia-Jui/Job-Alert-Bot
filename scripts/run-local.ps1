param(
    [string]$PythonCommand = "python",
    [string]$SettingsFile = "local.settings.ps1"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if ($PythonCommand -eq "python") {
    $pythonCandidates = @(
        "C:\Program Files\PostgreSQL\17\pgAdmin 4\python\python.exe",
        "python",
        "py"
    )

    foreach ($candidate in $pythonCandidates) {
        if ($candidate -in @("python", "py")) {
            if (Get-Command $candidate -ErrorAction SilentlyContinue) {
                $PythonCommand = $candidate
                break
            }
        } elseif (Test-Path $candidate) {
            $PythonCommand = $candidate
            break
        }
    }
}

if (-not (Test-Path $SettingsFile)) {
    throw "Settings file not found: $SettingsFile. Copy local.settings.example.ps1 to local.settings.ps1 first."
}

. (Resolve-Path $SettingsFile)

$env:SSLKEYLOGFILE = ""
$pythonEntry = @"
import sys
sys.path.insert(0, r'$(Join-Path $repoRoot "src")')
from job_alert_bot.main import main
raise SystemExit(main())
"@

& $PythonCommand -c $pythonEntry
