$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DistDir = Join-Path $ProjectRoot "dist"
$PublishDir = Join-Path $ProjectRoot "build\publish"
$BackupDir = Join-Path $ProjectRoot "build\_data_bak"
$StageDir = Join-Path $ProjectRoot "build\setup_stage"

# 版本以 csproj 为唯一真源(安装包版本由其派生)
$CsprojPath = Join-Path $ProjectRoot "src\KeyNote.App\KeyNote.App.csproj"
[xml]$CsprojXml = Get-Content -LiteralPath $CsprojPath
$AppVer = @($CsprojXml.Project.PropertyGroup | ForEach-Object { $_.Version } | Where-Object { $_ })[0]
if (-not $AppVer) { $AppVer = "1.0.0" }
Write-Host "VERSION: $AppVer" -ForegroundColor Cyan

$UserDataFiles = @("keynote.db", "keynote.db-wal", "keynote.db-shm", "config.json")

# 复制便携版用户数据(失败即中止,绝不吞错)
function Copy-UserData {
    param([string]$From, [string]$To)
    foreach ($f in $UserDataFiles) {
        $src = Join-Path $From $f
        if (Test-Path $src -PathType Leaf) {
            Copy-Item -Path $src -Destination $To -Force -ErrorAction Stop
        }
    }
    $bakBackup = Join-Path $From "backups"
    if (Test-Path $bakBackup -PathType Container) {
        Copy-Item -Path $bakBackup -Destination $To -Recurse -Force -ErrorAction Stop
    }
}

# 校验还原结果:逐文件比对大小,任一不符即判定还原失败
function Test-UserDataRestored {
    param([string]$From, [string]$To)
    foreach ($f in $UserDataFiles) {
        $src = Join-Path $From $f
        $dst = Join-Path $To $f
        if (-not (Test-Path $src -PathType Leaf)) { continue }
        if (-not (Test-Path $dst -PathType Leaf)) { return $false }
        if ((Get-Item $src).Length -ne (Get-Item $dst).Length) { return $false }
    }
    return $true
}

# Kill running instance to release file lock
$Running = Get-Process -Name "KeyNote.App" -ErrorAction SilentlyContinue
if ($Running) {
    Write-Host "Killing running KeyNote.App to release file lock..." -ForegroundColor Yellow
    $Running | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

# Preserve user data from previous dist (portable mode) before wiping
$HasBackup = $false
if (Test-Path $DistDir) {
    try {
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
        Copy-UserData -From $DistDir -To $BackupDir
        $HasBackup = $true
        Remove-Item -Recurse -Force $DistDir -ErrorAction Stop
    }
    catch {
        Write-Host "备份用户数据失败,已中止构建(原 dist 保持不动): $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

# Only clean the publish folder; build\_data_bak must survive
if (Test-Path $PublishDir) { Remove-Item -Recurse -Force $PublishDir }
if (Test-Path $StageDir) { Remove-Item -Recurse -Force $StageDir }

Write-Host "=== dotnet publish (Release, x64) ===" -ForegroundColor Cyan
dotnet publish "src\KeyNote.App\KeyNote.App.csproj" `
    -c Release `
    -p:Platform=x64 `
    -o $PublishDir `
    --nologo

if ($LASTEXITCODE -ne 0) {
    Write-Host "dotnet publish failed" -ForegroundColor Red
    if ($HasBackup) {
        New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
        Copy-UserData -From $BackupDir -To $DistDir
        Write-Host "用户数据已还原到 $DistDir" -ForegroundColor Yellow
    }
    exit 1
}

# Trim publish output: drop pdbs and non-zh/en language resources (WindowsAppSDK MUI noise)
Get-ChildItem $PublishDir -File -Filter *.pdb -Recurse | Remove-Item -Force
$KeepLangs = @("zh-CN", "en-us")
Get-ChildItem $PublishDir -Directory |
    Where-Object { $_.Name -match '^[a-z]{2,3}(-[A-Za-z]{2,8}){1,2}$' -and $KeepLangs -notcontains $_.Name } |
    Remove-Item -Recurse -Force
# 卫星资源文件(如 XXX.Resources_ec.dll):语言后缀形态,只删纯语言后缀,避免误伤 e_sqlite3 之类
Get-ChildItem $PublishDir -File -Recurse |
    Where-Object { $_.Name -match '^[^.]+_[a-z]{2,3}\.dll$' -and $_.DirectoryName -eq $PublishDir } |
    Remove-Item -Force

New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
Copy-Item -Path (Join-Path $PublishDir "*") -Destination $DistDir -Recurse -Force -ErrorAction Stop

# Restore user data into the portable dist, then verify before dropping the only backup
if ($HasBackup) {
    try {
        Copy-UserData -From $BackupDir -To $DistDir
        if (Test-UserDataRestored -From $BackupDir -To $DistDir) {
            Remove-Item -Recurse -Force $BackupDir
            Write-Host "User data restored" -ForegroundColor Green
        }
        else {
            Write-Host "用户数据还原校验不通过,备份保留在 $BackupDir" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "还原用户数据失败,备份保留在 $BackupDir : $($_.Exception.Message)" -ForegroundColor Red
    }
}

# ──── 体积构成报告 ────
$distFiles = Get-ChildItem $DistDir -File -Recurse
$totalMb = [math]::Round(($distFiles | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "=== 体积构成 Top 20 ===" -ForegroundColor Cyan
$distFiles | Sort-Object Length -Descending | Select-Object -First 20 | ForEach-Object {
    $mb = [math]::Round($_.Length / 1MB, 2)
    $rel = $_.FullName.Replace($DistDir + "\", "")
    Write-Host ("  {0,8} MB  {1}" -f $mb, $rel)
}
Write-Host "=== 分类汇总 ===" -ForegroundColor Cyan
$groups = [ordered]@{
    "WindowsAppSDK 运行时" = '^Microsoft\.(Windows|UI|WinUI|Web)|^WinUI|^WinRT|^WindowsApp|^Microsoft\.Windows\.SDK|^DWrite|^dwm|^Dwm|^dcompi|^CoreMessaging|^marshal|^wuceffectsi|^MRM|^RestartAgent|^workloads|^NpuDetect|\.winmd$|^resources\.pri$'
    ".NET 运行时"          = '^System\.|^Microsoft\.CSharp|^Microsoft\.NETCore|^mscorlib|^netstandard|^coreclr|^clrjit|^hostfxr|^hostpolicy|^windowsdesktop'
    "SQLite"               = 'Sqlite|SQLitePCL|e_sqlite3'
    "本应用"               = '^KeyNote\.'
    "其他"                 = '.*'
}
$classified = @{}
foreach ($g in $groups.Keys) { $classified[$g] = 0 }
foreach ($f in $distFiles) {
    $name = $f.Name
    $hit = "其他"
    foreach ($g in $groups.Keys) {
        if ($name -match $groups[$g]) { $hit = $g; break }
    }
    $classified[$hit] += $f.Length
}
foreach ($g in $groups.Keys) {
    $mb = [math]::Round($classified[$g] / 1MB, 1)
    Write-Host ("  {0,-22} {1,8} MB" -f $g, $mb)
}
Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "DIST: $DistDir ($totalMb MB)"
Write-Host "EXE: $DistDir\KeyNote.App.exe"

# ──── 安装包:从干净 staging 打包(绝不含用户数据) ────
$Isscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Isscc)) {
    Write-Host "未找到 Inno Setup 6($Isscc),已跳过安装包" -ForegroundColor Red
    Write-Host "请安装 Inno Setup 6 后重跑 build.ps1" -ForegroundColor Red
    exit 2
}

New-Item -ItemType Directory -Path $StageDir -Force | Out-Null
Copy-Item -Path (Join-Path $PublishDir "*") -Destination $StageDir -Recurse -Force -ErrorAction Stop
Copy-Item -Path (Join-Path $ProjectRoot "README.md") -Destination $StageDir -Force -ErrorAction Stop
Write-Host "=== Inno Setup installer ===" -ForegroundColor Cyan
& $Isscc "/DAppVer=$AppVer" "/DSrcDir=build\setup_stage" (Join-Path $ProjectRoot "KeyNote_Setup.iss")
if ($LASTEXITCODE -ne 0) {
    Write-Host "ISCC failed; installer not built" -ForegroundColor Red
    exit 2
}
$setupExe = Join-Path $ProjectRoot "installer\KeyNote_Setup.exe"
$setupMb = [math]::Round((Get-Item $setupExe).Length / 1MB, 1)
Write-Host "SETUP: $setupExe ($setupMb MB)" -ForegroundColor Green
