# One-command install on the company PC. Needs no Git. Run in an administrator PowerShell.
# The encrypted bar-stock-data.txt must be in this user's Downloads folder.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Close this window and open PowerShell with Run as administrator." }
$Root = "C:\BarStock"
$Program = Join-Path $Root "program"
$Python = Join-Path $env:ProgramFiles "Python312\python.exe"
$Temp = Join-Path $env:TEMP "barstock-install"
$Bundle = Get-ChildItem (Join-Path $env:USERPROFILE "Downloads") -Filter "bar-stock-data*.txt" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$HasData = Test-Path (Join-Path $Program "data\venue.sqlite")
if (-not $Bundle -and -not $HasData) { throw "bar-stock-data.txt is not in your Downloads folder. Save it there and run this again." }
Remove-Item $Temp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Temp | Out-Null

Write-Host "[1/5] Installing Python (a few minutes)..."
if (-not (Test-Path $Python)) {
    $installer = Join-Path $Temp "python.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $installer -UseBasicParsing
    Start-Process $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    if (-not (Test-Path $Python)) { throw "Python did not install." }
}

Write-Host "[2/5] Downloading the app..."
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Root*" } | Stop-Process -Force
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

Write-Host "[5/5] Setting it to start with the PC..."
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Program "windows\Setup-Venue.ps1")
& powercfg /change standby-timeout-ac 0
try { Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq "Public" } | Set-NetConnectionProfile -NetworkCategory Private } catch {}
$desktop = [Environment]::GetFolderPath("CommonDesktopDirectory")
"[InternetShortcut]`r`nURL=http://localhost:5052/stock" | Set-Content (Join-Path $desktop "Bar Stock.url")
Copy-Item (Join-Path $Program "windows\End-of-Shift.txt") $desktop -Force

$up = $false
for ($i = 0; $i -lt 30 -and -not $up; $i++) {
    Start-Sleep -Seconds 2
    try { $up = (Invoke-WebRequest "http://localhost:5052/ping" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
}
Write-Host ""
if ($up) {
    Write-Host "ALL DONE. Open Bar Stock on the desktop, or http://localhost:5052/stock" -ForegroundColor Green
    Write-Host "Staff devices on this network: http://$($env:COMPUTERNAME):5052/stock"
} else {
    Write-Host "Installed, but the app has not started. Restart the PC, then open Bar Stock on the desktop." -ForegroundColor Yellow
}
Remove-Item $Temp -Recurse -Force -ErrorAction SilentlyContinue
