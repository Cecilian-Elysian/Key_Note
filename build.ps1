$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DistDir = Join-Path $ProjectRoot "dist"
$BackupDir = Join-Path $ProjectRoot "build\_data_bak"

# Kill any running KeyNote.exe to release file lock on dist\keynote.db
$Running = Get-Process -Name "KeyNote" -ErrorAction SilentlyContinue
if ($Running) {
    Write-Host "Killing running KeyNote.exe to release file lock..." -ForegroundColor Yellow
    $Running | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

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
$BuildKeyNoteDir = Join-Path $ProjectRoot "build\KeyNote"
if (Test-Path $BuildKeyNoteDir) { Remove-Item -Recurse -Force $BuildKeyNoteDir }

Write-Host "=== PyInstaller building ==="
py -m PyInstaller --clean --noconfirm `
    --onefile --windowed `
    --name "KeyNote" `
    --icon "icon.ico" `
    --add-data "icon.ico;." `
    --hidden-import pynput.keyboard._win32 `
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