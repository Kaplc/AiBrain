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
python "$PSScriptRoot\sniff_claude.py"
