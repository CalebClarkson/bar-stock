# One-command install for this Windows account only. Needs no administrator password or Git.
# The app is served to this PC alone, because opening the firewall to staff devices needs admin.
# The encrypted bar-stock-data.txt must be in this user's Downloads folder.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = Join-Path $env:LOCALAPPDATA "BarStock"
$Program = Join-Path $Root "program"
$PythonDir = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
$Python = Join-Path $PythonDir "python.exe"
$Temp = Join-Path $env:TEMP "barstock-install"
$Bundle = Get-ChildItem (Join-Path $env:USERPROFILE "Downloads") -Filter "bar-stock-data*.txt" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$HasData = Test-Path (Join-Path $Program "data\venue.sqlite")
if (-not $Bundle -and -not $HasData) { throw "bar-stock-data.txt is not in your Downloads folder. Save it there and run this again." }
Remove-Item $Temp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Temp | Out-Null

Write-Host "[1/5] Installing Python for this account (a few minutes)..."
if (-not (Test-Path $Python)) {
    $installer = Join-Path $Temp "python.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $installer -UseBasicParsing
    Start-Process $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 InstallLauncherAllUsers=0 Include_test=0" -Wait
    if (-not (Test-Path $Python)) { throw "Python did not install. This PC may block installers for normal accounts." }
}

Write-Host "[2/5] Downloading the app..."
Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Root*" -or $_.Path -like "$PythonDir*" } | Stop-Process -Force
$zip = Join-Path $Temp "app.zip"
Invoke-WebRequest "https://github.com/CalebClarkson/bar-stock/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
Expand-Archive $zip -DestinationPath $Temp -Force
$src = (Get-ChildItem $Temp -Directory | Select-Object -First 1).FullName
& robocopy $src $Program /E /XD data .venv backups /XF venue.env /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Could not copy the app into $Program." }
New-Item -ItemType Directory -Force -Path (Join-Path $Program "data") | Out-Null

Write-Host "[3/5] Installing app components..."
Set-Location $Program
if (-not (Test-Path ".venv")) { & $Python -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install app components. Check the internet connection." }
if (-not (Test-Path "venue.env")) {
    (Get-Content "venue.env.example") -replace '^OSB_BIND=.*', 'OSB_BIND=127.0.0.1' | Set-Content "venue.env"
}

Write-Host "[4/5] Restoring stock data..."
if ($HasData) {
    Write-Host "Stock data already here. Leaving it alone."
} else {
    for ($try = 1; ; $try++) {
        $env:OSB_BUNDLE_PASSWORD = Read-Host "Enter the password from Caleb's message"
        $ErrorActionPreference = "Continue"
        & ".venv\Scripts\python.exe" manage.py import-data $Bundle.FullName
        $code = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        if ($code -eq 0) { break }
        if ($try -ge 3 -or $code -ne 4) { Remove-Item Env:\OSB_BUNDLE_PASSWORD; throw "Stock data was not restored." }
    }
    Remove-Item Env:\OSB_BUNDLE_PASSWORD
}

Write-Host "[5/5] Setting it to start when you sign in..."
$serverBat = Join-Path $Program "windows\run-server.bat"
$backupBat = Join-Path $Program "windows\run-backup.bat"
$starter = Join-Path ([Environment]::GetFolderPath("Startup")) "Bar Stock.vbs"
@"
Set shell = CreateObject("WScript.Shell")
shell.Run """$backupBat""", 0, False
shell.Run """$serverBat""", 0, False
"@ | Set-Content $starter
$ErrorActionPreference = "Continue"
& schtasks /Create /F /TN "Bar Stock Backup" /SC DAILY /ST 05:00 /TR "`"$backupBat`"" 2>&1 | Out-Null
$daily = $LASTEXITCODE
& powercfg /change standby-timeout-ac 0 2>&1 | Out-Null
$awake = $LASTEXITCODE
$ErrorActionPreference = "Stop"
$desktop = [Environment]::GetFolderPath("Desktop")
"[InternetShortcut]`r`nURL=http://localhost:5052/stock" | Set-Content (Join-Path $desktop "Bar Stock.url")
Copy-Item (Join-Path $Program "windows\End-of-Shift.txt") $desktop -Force
Start-Process wscript.exe -ArgumentList "`"$starter`""

$up = $false
for ($i = 0; $i -lt 30 -and -not $up; $i++) {
    Start-Sleep -Seconds 2
    try { $up = (Invoke-WebRequest "http://localhost:5052/ping" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
}
Write-Host ""
if ($daily -ne 0) { Write-Host "Note: the 05:00 backup could not be scheduled. A backup still runs each time you sign in." -ForegroundColor Yellow }
if ($awake -ne 0) { Write-Host "Note: could not turn off sleep. Set Sleep to Never in Windows Settings > Power." -ForegroundColor Yellow }
if ($up) {
    Write-Host "ALL DONE. Open Bar Stock on the desktop, or http://localhost:5052/stock" -ForegroundColor Green
} else {
    Write-Host "Installed, but the app has not started. Sign out and back in, then open Bar Stock on the desktop." -ForegroundColor Yellow
}
Remove-Item $Temp -Recurse -Force -ErrorAction SilentlyContinue
