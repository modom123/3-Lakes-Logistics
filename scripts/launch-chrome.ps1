# Bond — Launch Chrome with remote debugging enabled
# Run this in PowerShell: .\scripts\launch-chrome.ps1

$chromePaths = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
  "$env:ProgramFiles\Google\Chrome Beta\Application\chrome.exe",
  "$env:ProgramFiles\Chromium\Application\chrome.exe"
)

$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) {
  Write-Host "Chrome not found. Download it from https://www.google.com/chrome" -ForegroundColor Red
  exit 1
}

Write-Host "Found Chrome: $chrome" -ForegroundColor Green
Write-Host "Launching with remote debugging on port 9222..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Once Chrome opens:" -ForegroundColor Yellow
Write-Host "  1. Log into github.com as the repo owner"
Write-Host "  2. Log into play.google.com/console as nwtcinvestment@gmail.com"
Write-Host "  3. Then run: node scripts/bond-install-all.js"
Write-Host ""

Start-Process -FilePath $chrome -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=$env:TEMP\bond-chrome"
