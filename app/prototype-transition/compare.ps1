param([Parameter(Mandatory)][string]$ExperimentDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$rows = [System.Collections.Generic.List[object]]::new()
$scenarios = @('piston-open', 'piston-close', 'delayed', 'hopper-cooldown', 'hopper-locked', 'hopper-empty', 'clock')

function Check([bool]$Condition, [string]$Message) {
    if (!$Condition) { $failures.Add($Message) }
}

function BlockAt($Endpoint, [int]$X, [int]$Y, [int]$Z) {
    @($Endpoint.blocks | Where-Object { $_.pos[0] -eq $X -and $_.pos[1] -eq $Y -and $_.pos[2] -eq $Z })[0]
}

foreach ($scenario in $scenarios) {
    $results = @()
    foreach ($attempt in 1..3) {
        $name = "$scenario-$attempt"
        $traceRoot = Join-Path $ExperimentDirectory "$name/traces"
        try {
            Check (!(Test-Path -LiteralPath (Join-Path $traceRoot 'error.txt'))) "$name : server error"
            $result = Get-Content -LiteralPath (Join-Path $traceRoot "$name.result.json") -Raw | ConvertFrom-Json
            $expected = if ($scenario -eq 'clock') { 'limit-reached' } elseif ($scenario.StartsWith('hopper')) { 'indeterminate' } else { 'terminated' }
            Check ($result.status -eq $expected) "$name : expected $expected, got $($result.status)"
            Check ($result.name -eq $name -and $result.scenario -eq $scenario) "$name : incorrect result identity"
            $lineCount = 0
            $lastTick = -1
            $lastWorldTime = -1L
            $transferTicks = [System.Collections.Generic.List[int]]::new()
            $inputRows = 0
            $traceError = $false
            # Stream the 36 001-row clock trace instead of retaining it in memory.
            foreach ($line in [System.IO.File]::ReadLines((Join-Path $traceRoot "$name.jsonl"))) {
                $row = $line | ConvertFrom-Json
                if ($row.tick -ne $lastTick + 1) { $traceError = $true }
                if ($lastWorldTime -ge 0 -and $row.worldTime -ne $lastWorldTime + 1) { $traceError = $true }
                $lastTick = $row.tick
                $lastWorldTime = $row.worldTime
                if ($row.event -eq 'input') { $inputRows++ }
                $lineCount++
                if ($row.reason -eq 'quiescent') {
                    if (!$row.relevantStateUnchanged -or $row.blockTicks.Count -gt 0 -or $row.fluidTicks.Count -gt 0 -or $row.blockEvents.Count -gt 0) { $traceError = $true }
                }
                if ($scenario -eq 'hopper-cooldown' -and $row.event -eq 'tick') {
                    foreach ($block in $row.changedBlocks) {
                        if ($block.pos[0] -eq 4 -and $block.pos[1] -eq 80 -and $block.pos[2] -eq 2) {
                            $transferTicks.Add($row.tick)
                        }
                    }
                }
                if ($scenario.StartsWith('hopper') -and $row.event -eq 'diagnostic') {
                    if ($row.relevantStateUnchanged) { $traceError = $true }
                }
            }
            Check (!$traceError -and $inputRows -eq 1) "$name : invalid or skipped trace ticks"
            Check ($lineCount -eq 1 + $result.tick + $result.diagnosticTicks) "$name : incomplete trace"
            Check ($result.tick -gt 0 -and $result.tick -le 36000) "$name : invalid detection tick"
            if ($expected -eq 'terminated') {
                $verified = Get-Content -LiteralPath (Join-Path $traceRoot "$name.verification.json") -Raw | ConvertFrom-Json
                Check ($verified.success -and $verified.ticks -eq 200) "$name : missing post-endpoint validation"
                $verificationRows = @(Get-Content -LiteralPath (Join-Path $traceRoot "$name.verification.jsonl") | ForEach-Object { $_ | ConvertFrom-Json })
                Check ($verificationRows.Count -eq 201) "$name : incomplete verification trace"
                for ($i = 0; $i -lt $verificationRows.Count; $i++) {
                    Check ($verificationRows[$i].tick -eq $i -and $verificationRows[$i].relevantStateUnchanged) "$name : verification change at tick $i"
                    Check ($verificationRows[$i].worldTime -eq $verificationRows[0].worldTime + $i) "$name : verification did not advance world ticks"
                }
                Check ($result.movingTicks -gt 0 -and $result.pendingTicks -gt 0) "$name : piston or scheduled activity not exercised"
                $pistonX = if ($scenario -eq 'delayed') { 5 } else { 3 }
                $piston = BlockAt $result.endpoint $pistonX 80 1
                $closed = $scenario -eq 'piston-close'
                $extension = if ($closed) { 'extended=false' } else { 'extended=true' }
                Check ($piston.state.Contains($extension)) "$name : incorrect piston endpoint"
                $stoneX = if ($closed) { 4 } else { $pistonX + 2 }
                Check ((BlockAt $result.endpoint $stoneX 80 1).state.Contains('minecraft:stone')) "$name : door block at incorrect position"
            }
            if ($scenario -eq 'delayed') {
                Check ($result.quietWithPendingTicks -ge 3 -and $result.tick -gt 24) "$name : delayed quiet gap not exercised"
            }
            if ($scenario.StartsWith('hopper')) {
                Check ($result.reason -eq 'hopper-lastTickTime-keeps-changing' -and $result.diagnosticTicks -eq 200) "$name : uncertainty reason or followup missing"
                $hopper = BlockAt $result.endpoint 3 80 2
                Check ($hopper.runtime.transferCooldown -eq 0) "$name : declared uncertainty before cooldown completed"
                $enabled = if ($scenario -eq 'hopper-locked') { 'enabled=false' } else { 'enabled=true' }
                Check ($hopper.state.Contains($enabled)) "$name : hopper fixture state incorrect"
            }
            if ($scenario -eq 'hopper-cooldown') {
                Check ($result.firstTransferTick -eq 8 -and $result.cooldownWithoutQueueTicks -ge 7 -and $result.tick -ge 32) "$name : deferred hopper transfers not exercised"
                Check (($transferTicks -join ',') -eq '8,16,24') "$name : incorrect transfer ticks in trace"
                $chest = BlockAt $result.endpoint 4 80 2
                $items = @($chest.nbt.value.Items.value)
                Check ($items.Count -eq 1 -and $items[0].value.count.value -eq '3') "$name : three diamonds did not reach chest"
            }
            if ($scenario -eq 'clock') {
                Check ($result.tick -eq 36000 -and $result.stateChanges -gt 100 -and $result.pendingTicks -gt 100) "$name : persistent clock not exercised"
            }
            $results += $result
            $rows.Add([pscustomobject]@{ name = $name; status = $result.status; tick = $result.tick; reason = $result.reason; firstTransferTick = $result.firstTransferTick; quietWithPendingTicks = $result.quietWithPendingTicks })
        } catch { $failures.Add("$name : $($_.Exception.Message)") }
    }
    if ($results.Count -eq 3) {
        Check (@($results.status | Select-Object -Unique).Count -eq 1 -and @($results.tick | Select-Object -Unique).Count -eq 1 -and @($results.reason | Select-Object -Unique).Count -eq 1) "$scenario : inconsistent result or tick across repetitions"
    }
}
$verdict = [pscustomobject]@{ success = $failures.Count -eq 0; runs = $rows.ToArray(); failures = $failures.ToArray() }
$verdict | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $ExperimentDirectory 'verdict.json') -Encoding utf8
$markdown = [System.Collections.Generic.List[string]]::new()
$markdown.Add('# Verdict du prototype de fin de transition')
$markdown.Add('')
$markdown.Add("Succès des critères expérimentaux : **$($verdict.success)**")
$markdown.Add('')
$markdown.Add('| Exécution | Résultat | Tick | Cause |')
$markdown.Add('| --- | --- | ---: | --- |')
foreach ($row in $rows) { $markdown.Add("| $($row.name) | $($row.status) | $($row.tick) | $($row.reason) |") }
$markdown.Add('')
$markdown.Add("Les fins reconnues ont été restaurées dans une copie indépendante, puis observées pendant 200 ticks. Les hoppers restent indéterminés : lastTickTime continue de changer, même verrouillés. Aucun champ interne n'a été normalisé. Ce résultat est limité aux montages et versions du prototype.")
foreach ($failure in $failures) { $markdown.Add("- Échec : $failure") }
$markdown | Set-Content -LiteralPath (Join-Path $ExperimentDirectory 'verdict.md') -Encoding utf8
$verdict
