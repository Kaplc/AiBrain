# 清理旧实例
$connections = Get-NetTCPConnection -LocalPort 9999 -ErrorAction SilentlyContinue | Where-Object State -eq 'Listen'
if ($connections) {
    foreach ($conn in $connections) {
        Write-Host "发现旧实例 PID=$($conn.OwningProcess)，正在清理..." -ForegroundColor Yellow
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
    Write-Host "清理完成" -ForegroundColor Green
}

# 启动拦截脚本
Write-Host "正在启动拦截脚本..." -ForegroundColor Cyan
$venvPython = Join-Path $PSScriptRoot "..\venv312\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}
try {
    & $venvPython "$PSScriptRoot\sniff_claude.py"
} catch {
    Write-Host "脚本异常: $_" -ForegroundColor Red
}
Write-Host "`n脚本已退出，按 Enter 键关闭窗口..." -ForegroundColor Yellow
Read-Host
