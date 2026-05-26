# Generate the Android release signing keystore for 3 Lakes Driver
# Run in PowerShell on Windows: .\scripts\generate-keystore.ps1
# Requires Java JDK (keytool is included with Java)

$KEYSTORE_FILE = "3lakes-release.keystore"
$KEY_ALIAS     = "threelakes"
$VALIDITY_DAYS = 10000

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " 3 Lakes Driver — Android Keystore Generator" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "You will be prompted for passwords and organization info." -ForegroundColor Yellow
Write-Host "Use the values below when prompted:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  First and Last Name  ->  3 Lakes Logistics"
Write-Host "  Organizational Unit  ->  Operations"
Write-Host "  Organization         ->  3 Lakes Logistics"
Write-Host "  City                 ->  (your city)"
Write-Host "  State                ->  (your state, e.g. MI)"
Write-Host "  Country Code         ->  US"
Write-Host ""

# Check if keytool is available
if (-not (Get-Command keytool -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: keytool not found." -ForegroundColor Red
    Write-Host "Install Java JDK from: https://adoptium.net" -ForegroundColor Yellow
    Write-Host "Then restart PowerShell and run this script again." -ForegroundColor Yellow
    exit 1
}

# Generate the keystore
keytool -genkey -v `
  -keystore $KEYSTORE_FILE `
  -alias $KEY_ALIAS `
  -keyalg RSA `
  -keysize 2048 `
  -validity $VALIDITY_DAYS

if ($LASTEXITCODE -ne 0) {
    Write-Host "Keystore generation failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Keystore created: $KEYSTORE_FILE" -ForegroundColor Green
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " NEXT: Add these 4 GitHub Secrets" -ForegroundColor Cyan
Write-Host " Repo -> Settings -> Secrets -> Actions" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Encode keystore to base64 for GitHub Secrets
$bytes  = [System.IO.File]::ReadAllBytes((Resolve-Path $KEYSTORE_FILE))
$base64 = [Convert]::ToBase64String($bytes)

Write-Host "ANDROID_KEYSTORE_BASE64  (copy everything after the = sign):" -ForegroundColor Yellow
Write-Host $base64
Write-Host ""
Write-Host "ANDROID_KEY_ALIAS        ->  $KEY_ALIAS" -ForegroundColor Yellow
Write-Host "ANDROID_STORE_PASSWORD   ->  (the keystore password you just entered)" -ForegroundColor Yellow
Write-Host "ANDROID_KEY_PASSWORD     ->  (the key password you just entered)" -ForegroundColor Yellow
Write-Host ""
Write-Host "WARNING: Never commit $KEYSTORE_FILE to git. Store it safely." -ForegroundColor Red
