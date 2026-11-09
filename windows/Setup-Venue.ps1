# One-time setup on the bar's PC. Run in an elevated PowerShell from the program folder:
#   powershell -ExecutionPolicy Bypass -File windows\Setup-Venue.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
if (-not (Test-Path ".venv")) { py -3 -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if (-not (Test-Path "venue.env")) {
    (Get-Content "venue.env.example") -replace '^OSB_BIND=.*', 'OSB_BIND=0.0.0.0' | Set-Content "venue.env"
}
if ($Root -match ' ') { throw "Install to a path without spaces, e.g. C:\BarStock" }
schtasks /Create /F /TN "Bar Stock Server" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR (Join-Path $PSScriptRoot "run-server.bat") | Out-Null
schtasks /Create /F /TN "Bar Stock Backup" /SC DAILY /ST 05:00 /RU SYSTEM /TR (Join-Path $PSScriptRoot "run-backup.bat") | Out-Null
# Work and private networks, this subnet only; never the public profile.
netsh advfirewall firewall delete rule name="Bar Stock 5052" | Out-Null
netsh advfirewall firewall add rule name="Bar Stock 5052" dir=in action=allow protocol=TCP localport=5052 profile=domain,private remoteip=localsubnet | Out-Null
schtasks /Run /TN "Bar Stock Server" | Out-Null
Write-Host "Done. Open http://localhost:5052/stock"
