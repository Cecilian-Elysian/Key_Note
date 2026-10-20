$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DistDir = Join-Path $ProjectRoot "dist"
$PublishDir = Join-Path $ProjectRoot "build\publish"
$BackupDir = Join-Path $ProjectRoot "build\_data_bak"

# Kill running instance to release file lock
$Running = Get-Process -Name "KeyNote.App" -ErrorAction SilentlyContinue
if ($Running) {
    Write-Host "Killing running KeyNote.App to release file lock..." -ForegroundColor Yellow
    $Running | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

# Preserve user data from previous dist (portable mode) before wiping
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

# Only clean the publish folder; build\_data_bak must survive
if (Test-Path $PublishDir) { Remove-Item -Recurse -Force $PublishDir }

Write-Host "=== dotnet publish (Release, x64, self-contained) ===" -ForegroundColor Cyan
dotnet publish "src\KeyNote.App\KeyNote.App.csproj" `
    -c Release `
    -p:Platform=x64 `
    -o $PublishDir `
    --nologo

if ($LASTEXITCODE -ne 0) {
    Write-Host "dotnet publish failed" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
Copy-Item -Path (Join-Path $PublishDir "*") -Destination $DistDir -Recurse -Force

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

$sizeMb = [math]::Round((Get-ChildItem -Recurse $DistDir | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "DIST: $DistDir ($sizeMb MB)"
Write-Host "EXE: $DistDir\KeyNote.App.exe"
