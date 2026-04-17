$ErrorActionPreference = 'SilentlyContinue'
Write-Host "=== Killing old processes ==="

# 读取端口配置
$portConfig = Get-Content '.port_config' -Raw
if ($portConfig) {
    $ports = $portConfig -split ','
    foreach ($p in $ports) {
        $p = $p.Trim()
        if ($p) {
            $conn = Get-NetTCPConnection -LocalPort $p -State Listen
            if ($conn) {
                Write-Host "  Killed port $p PID $($conn.OwningProcess)"
                Stop-Process -Id $conn.OwningProcess -Force
            }
        }
    }
}

# 杀掉占用本项目端口的 qdrant 进程
$portConfig = Get-Content '.port_config' -Raw
if ($portConfig) {
    $ports = $portConfig -split ','
    $qdrantPorts = @($ports[1], $ports[2])  # HTTP 和 GRPC 端口
    Get-Process qdrant -ErrorAction SilentlyContinue | ForEach-Object {
        $proc = $_
        $bindings = Get-NetTCPConnection -OwningProcess $proc.Id -State Listen -ErrorAction SilentlyContinue
        $boundPorts = $bindings | ForEach-Object { $_.LocalPort }
        $shouldKill = $false
        foreach ($bp in $boundPorts) {
            if ($qdrantPorts -contains $bp) {
                $shouldKill = $true
                break
            }
        }
        if ($shouldKill) {
            Write-Host "  Killed qdrant: $($proc.Id) (port match)"
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "=== Done ==="
