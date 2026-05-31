param([int]$Pid = 31896, [int]$DurationSec = 300)

$samples = @()
$start   = Get-Date
$endTime = $start.AddSeconds($DurationSec)
$logFile = Join-Path $PSScriptRoot "mem_log.txt"

"" | Out-File $logFile
Write-Host "[monitor] Watching PID $Pid for up to ${DurationSec}s — output: $logFile"

while ((Get-Date) -lt $endTime) {
    $proc = Get-Process -Id $Pid -ErrorAction SilentlyContinue
    if (-not $proc) { "[monitor] Process $Pid gone." | Tee-Object -Append $logFile; break }

    $rss  = [math]::Round($proc.WorkingSet64 / 1MB, 1)
    $cpu  = [math]::Round($proc.CPU, 1)
    $elapsed = [math]::Round(((Get-Date) - $start).TotalSeconds, 1)
    $ts   = (Get-Date).ToString("HH:mm:ss")
    $line = "  $ts  +${elapsed}s  RSS ${rss} MB  CPU ${cpu}s"
    $line | Tee-Object -Append $logFile
    $samples += [pscustomobject]@{ Elapsed=$elapsed; RSS=$rss }
    Start-Sleep -Seconds 1
}

# --- Report ---
if ($samples.Count -gt 0) {
    $baseline = $samples[0].RSS
    $peak     = ($samples | Measure-Object RSS -Maximum).Maximum
    $peakRow  = $samples | Where-Object { $_.RSS -eq $peak } | Select-Object -First 1
    $final    = $samples[-1].RSS

    $report = @"

===================================================
MEMORY REPORT
===================================================
  Baseline  : $baseline MB
  Peak      : $peak MB  (+$([math]::Round($peak - $baseline,1)) MB spike)  at +$($peakRow.Elapsed)s
  Final     : $final MB  (+$([math]::Round($final - $baseline,1)) MB retained)
  Samples   : $($samples.Count)  (1 s interval)

  Jumps > 50 MB:
"@

    $jumped = $false
    for ($i = 1; $i -lt $samples.Count; $i++) {
        $delta = $samples[$i].RSS - $samples[$i-1].RSS
        if ([math]::Abs($delta) -gt 50) {
            $sign = if ($delta -gt 0) { "+" } else { "" }
            $report += "`n    +$($samples[$i].Elapsed)s  $($samples[$i-1].RSS) -> $($samples[$i].RSS) MB  ($sign$([math]::Round($delta,1)) MB)"
            $jumped = $true
        }
    }
    if (-not $jumped) { $report += "`n    none" }
    $report += "`n===================================================`n"

    $report | Tee-Object -Append $logFile
}
