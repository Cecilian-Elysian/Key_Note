$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DistDir = Join-Path $ProjectRoot "dist"
if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
if (Test-Path (Join-Path $ProjectRoot "build")) { Remove-Item -Recurse -Force (Join-Path $ProjectRoot "build") }

Write-Host "=== PyInstaller 构建中 ==="
python -m PyInstaller --clean --noconfirm `
    --onefile --windowed `
    --name "KeyNote" `
    --icon "icon.ico" `
    --add-data "icon.ico;." `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pynput.mouse._win32 `
    --hidden-import win32clipboard `
    main.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller 构建失败" -ForegroundColor Red
    exit 1
}

Write-Host "=== 构建完成 ===" -ForegroundColor Green
Write-Host "EXE: $ProjectRoot\dist\KeyNote.exe"
