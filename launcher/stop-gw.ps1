param([int]$Port = 18075)
$ErrorActionPreference = 'SilentlyContinue'

function Kill-Tree([int]$rootPid) {
    $kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$rootPid"
    foreach ($k in $kids) { Kill-Tree -rootPid ([int]$k.ProcessId) }
    Write-Host ("[stop-gw]   kill pid {0}" -f $rootPid)
    Stop-Process -Id $rootPid -Force
}

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen
if (-not $listeners) {
    Write-Host ("[stop-gw] nothing listens on :{0} - the gateway is already stopped" -f $Port)
    exit 0
}

$owners = @($listeners | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)
foreach ($p in $owners) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$p"
    Write-Host ("[stop-gw] port {0} held by pid {1}: {2}" -f $Port, $p, $proc.CommandLine)
    Kill-Tree -rootPid $p
}

Start-Sleep -Seconds 2

# The router keeps one lazy backend per config as job children; the tree kill above takes
# them, but a build without the job tie-in can leave them orphaned. Only orphans are swept:
# a python router whose parent is gone, i.e. the same deployment this port belonged to.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -match 'strata-router\.py'
} | ForEach-Object {
    $parent = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $_.ParentProcessId)
    if (-not $parent) {
        Write-Host ("[stop-gw] orphan router pid {0} (parent gone) - killing" -f $_.ProcessId)
        Kill-Tree -rootPid ([int]$_.ProcessId)
    }
}

Start-Sleep -Seconds 2
$left = Get-NetTCPConnection -LocalPort $Port -State Listen
if ($left) {
    $pids = @($left | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique) -join ','
    Write-Host ("[stop-gw] FAILED: port {0} is still listening (pid {1})" -f $Port, $pids)
    exit 1
}
$sys = @(Get-Process strata,strata-vision -ErrorAction SilentlyContinue)
if ($sys.Count -gt 0) {
    Write-Host ("[stop-gw] note: {0} orphan strata process(es) still alive (port is free)" -f $sys.Count)
}
Write-Host ("[stop-gw] port {0} is free - gateway stopped" -f $Port)
exit 0
