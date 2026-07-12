$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DistDir = Join-Path $ProjectRoot "dist"
$BackupDir = Join-Path $ProjectRoot "build\_data_bak"

if (Test-Path $DistDir) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    $DataFiles = @("keynote.db", "keynote.db-wal", "keynote.db-shm", "config.json")
    foreach ($f in $DataFiles) {
        $src = Join-Path $DistDir $f
        if (Test-Path $src -PathType Leaf) { Copy-Item -Path $src -Destination $BackupDir -Force }
    }
    $bakBackup = Join-Path $DistDir "backups"
    if (Test-Path $bakBackup -PathType Container) { Copy-Item -Path $bakBackup -Destination $BackupDir -Recurse -Force }

    Remove-Item -Recurse -Force $DistDir
}
if (Test-Path (Join-Path $ProjectRoot "build" "KeyNote")) { Remove-Item -Recurse -Force (Join-Path $ProjectRoot "build" "KeyNote") }

Write-Host "=== PyInstaller building ==="
py -m PyInstaller --clean --noconfirm `
    --onefile --windowed `
    --name "KeyNote" `
    --icon "icon.ico" `
    --add-data "icon.ico;." `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pynput.mouse._win32 `
    --hidden-import win32clipboard `
    key_note.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller build failed" -ForegroundColor Red
    exit 1
}

if (Test-Path $BackupDir) {
    $DataFiles = @("keynote.db", "keynote.db-wal", "keynote.db-shm", "config.json")
    foreach ($f in $DataFiles) {
        $src = Join-Path $BackupDir $f
        if (Test-Path $src -PathType Leaf) { Copy-Item -Path $src -Destination $DistDir -Force }
    }
    $bakBackup = Join-Path $BackupDir "backups"
    if (Test-Path $bakBackup -PathType Container) { Copy-Item -Path $bakBackup -Destination $DistDir -Recurse -Force }
    Remove-Item -Recurse -Force $BackupDir
    Write-Host "User data restored" -ForegroundColor Green
}

Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "EXE: $ProjectRoot\dist\KeyNote.exe"