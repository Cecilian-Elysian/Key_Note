$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DistDir = Join-Path $ProjectRoot "dist"
$PublishDir = Join-Path $ProjectRoot "build\publish"
$BackupDir = Join-Path $ProjectRoot "build\_data_bak"

# 版本以 csproj 为唯一真源(安装包版本由其派生)
$CsprojPath = Join-Path $ProjectRoot "src\KeyNote.App\KeyNote.App.csproj"
[xml]$CsprojXml = Get-Content -LiteralPath $CsprojPath
$AppVer = @($CsprojXml.Project.PropertyGroup | ForEach-Object { $_.Version } | Where-Object { $_ })[0]
if (-not $AppVer) { $AppVer = "1.0.0" }
Write-Host "VERSION: $AppVer" -ForegroundColor Cyan

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

# Trim publish output: drop pdbs and non-zh/en language resource dirs (WindowsAppSDK MUI noise)
Get-ChildItem $PublishDir -File -Filter *.pdb -Recurse | Remove-Item -Force
$KeepLangs = @("zh-CN", "en-us")
Get-ChildItem $PublishDir -Directory |
    Where-Object { $_.Name -match '^[a-z]{2,3}(-[A-Za-z]{2,8}){1,2}$' -and $KeepLangs -notcontains $_.Name } |
    Remove-Item -Recurse -Force

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

# Inno Setup installer: pack dist\* first, then drop the setup exe into dist
$Isscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (Test-Path $Isscc) {
    Write-Host "=== Inno Setup installer ===" -ForegroundColor Cyan
    & $Isscc "/DAppVer=$AppVer" (Join-Path $ProjectRoot "KeyNote_Setup.iss") | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Copy-Item (Join-Path $ProjectRoot "installer\KeyNote_Setup.exe") $DistDir -Force
        $setupMb = [math]::Round((Get-Item (Join-Path $DistDir "KeyNote_Setup.exe")).Length / 1MB, 1)
        Write-Host "SETUP: $DistDir\KeyNote_Setup.exe ($setupMb MB)" -ForegroundColor Green
    } else {
        Write-Host "ISCC failed; installer not built" -ForegroundColor Red
    }
}
