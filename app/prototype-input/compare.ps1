param([Parameter(Mandatory)][string]$ExperimentDirectory, [ValidateSet('torch', 'repeater-1', 'repeater-4', 'piston')][string[]]$Fixtures = @('torch', 'repeater-1', 'repeater-4', 'piston'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()
$runs = [System.Collections.Generic.List[object]]::new()
$pairs = [System.Collections.Generic.List[object]]::new()
$repeatability = [System.Collections.Generic.List[object]]::new()
function Check([bool]$Condition, [string]$Message) { if (!$Condition) { $failures.Add($Message) } }
function Canonical($Value) { ConvertTo-Json -InputObject $Value -Depth 100 -Compress }
function Common($State) {
    $copy = [ordered]@{ blocks = $State.blocks }
    foreach ($field in @('blockTicks', 'fluidTicks', 'blockEvents')) {
        $copy[$field] = @($State[$field] | Where-Object { $_.pos[0] -ge 4 })
    }
    $copy
}
function Read-Lines([string]$Path) {
    if (Test-Path -LiteralPath $Path) { return [IO.File]::ReadAllLines($Path) }
    $stream = [IO.File]::OpenRead("$Path.gz")
    $gzip = [IO.Compression.GZipStream]::new($stream, [IO.Compression.CompressionMode]::Decompress)
    $reader = [IO.StreamReader]::new($gzip)
    try { $reader.ReadToEnd() -split "\r?\n" | Where-Object { $_.Length -gt 0 } } finally { $reader.Dispose(); $stream.Dispose() }
}

foreach ($fixture in $Fixtures) {
    foreach ($device in @('lever', 'stone-button', 'wood-button')) {
        $byMode = @{}
        foreach ($mode in @('direct', 'repeater')) {
            $repetitions = @()
            foreach ($attempt in 1..3) {
                $name = "$fixture-$device-$mode-$attempt"
                $root = Join-Path $ExperimentDirectory "$name/traces"
                try {
                    Check (!(Test-Path -LiteralPath (Join-Path $root 'error.txt'))) "$name : server error"
                    $result = Get-Content -LiteralPath (Join-Path $root "$name.result.json") -Raw | ConvertFrom-Json -AsHashtable
                    $checkpoint = Get-Content -LiteralPath (Join-Path $root "$fixture.checkpoint.json") -Raw | ConvertFrom-Json -AsHashtable
                    $original = Get-Content -LiteralPath (Join-Path $ExperimentDirectory "checkpoint-$fixture/traces/$fixture.checkpoint.json") -Raw | ConvertFrom-Json -AsHashtable
                    Check ((Canonical $checkpoint) -ceq (Canonical $original)) "$name : run does not use the original checkpoint"
                    Check ((Canonical (Common $checkpoint)) -ceq (Canonical $result.initial)) "$name : reported state 0 differs from checkpoint"
                    $trace = @(Read-Lines (Join-Path $root "$name.jsonl") | ForEach-Object { $_ | ConvertFrom-Json -AsHashtable })
                    Check ($result.name -eq $name -and $result.fixture -eq $fixture -and $result.device -eq $device -and $result.mode -eq $mode) "$name : incorrect identity"
                    Check ($result.status -eq 'terminated' -and $result.returnedToState0) "$name : incomplete cycle"
                    Check ($trace[0].event -eq 'initial' -and $trace[0].tick -eq -1 -and $trace[-1].event -eq 'closed-endpoint') "$name : missing trace endpoints"
                    Check ((Canonical (Common $trace[0].state)) -ceq (Canonical $result.initial)) "$name : initial trace differs from checkpoint"
                    Check ((Canonical (Common $trace[-1].state)) -ceq (Canonical $result.closed)) "$name : final trace differs from result"
                    Check ((Canonical $result.initial) -ceq (Canonical $result.closed)) "$name : final construction differs from state 0"
                    $open = @($trace | Where-Object { $_.event -eq 'open-endpoint' })
                    Check ($open.Count -eq 1 -and (Canonical (Common $open[0].state)) -ceq (Canonical $result.opened)) "$name : missing or inconsistent open endpoint"
                    $tickRows = @($trace | Where-Object { $_.event -eq 'tick' })
                    Check ($tickRows.Count -eq $result.lastTick + 1) "$name : incomplete tick trace"
                    for ($index = 0; $index -lt $tickRows.Count; $index++) {
                        Check ($tickRows[$index].tick -eq $index -and $tickRows[$index].state.worldTime -eq $trace[0].state.worldTime + $index + 1) "$name : invalid simulation/world tick $index"
                    }
                    foreach ($endpoint in @($open[0], $trace[-1])) {
                        $common = Common $endpoint.state
                        Check ($common.blockTicks.Count -eq 0 -and $common.fluidTicks.Count -eq 0 -and $common.blockEvents.Count -eq 0) "$name : endpoint has pending construction events"
                        Check (@($common.blocks | Where-Object { $_.state.Contains('minecraft:moving_piston') }).Count -eq 0) "$name : endpoint contains moving piston"
                        Check ($endpoint.tick -gt 0 -and (Canonical $common) -ceq (Canonical (Common $tickRows[$endpoint.tick - 1].state))) "$name : endpoint changed during its preceding tick"
                    }
                    Check ($trace[-1].state.blockTicks.Count -eq 0 -and $trace[-1].state.fluidTicks.Count -eq 0 -and $trace[-1].state.blockEvents.Count -eq 0) "$name : final adapter still has pending events"
                    $actions = @($trace | Where-Object { $_.event -eq 'after-input-before-time-increment' })
                    Check ($actions.Count -eq $(if ($device -eq 'lever') { 2 } else { 1 })) "$name : wrong number of vanilla source actions"
                    foreach ($action in $actions) {
                        Check ($action.phase -eq 'before-time-increment' -and $action.state.worldTime -eq $trace[0].state.worldTime + $action.tick) "$name : source action occurred after world time increment"
                        $targetX = if ($mode -eq 'direct') { 5 } else { 3 }
                        $scheduled = @($action.state.blockTicks | Where-Object { $_.pos[0] -eq $targetX -and $_.pos[1] -eq 80 -and $_.pos[2] -eq 2 })
                        $delay = if ($mode -eq 'direct' -and $fixture -eq 'repeater-4') { 8 } else { 2 }
                        Check ($scheduled.Count -eq 1 -and $scheduled[0].triggerTick -eq $action.state.worldTime + $delay) "$name : expected vanilla scheduled deadline missing"
                    }
                    foreach ($event in $result.events) {
                        $offset = if ($event.phase -eq 'before-time-increment') { 0 } else { 1 }
                        Check ($event.worldTime -eq $trace[0].state.worldTime + $event.tick + $offset) "$name : event phase and world clock disagree"
                    }
                    foreach ($kind in @('source', 'input', 'component')) {
                        $events = @($result.events | Where-Object { $_.kind -eq $kind })
                        Check ($events.Count -eq 2) "$name : expected two $kind changes"
                        $previous = if ($kind -eq 'component') { ($trace[0].state.blocks | Where-Object { $_.pos[0] -eq 5 -and $_.pos[1] -eq 80 -and $_.pos[2] -eq 2 }).state } else { $false }
                        $observed = @()
                        foreach ($row in $trace) {
                            $value = if ($kind -eq 'component') { ($row.state.blocks | Where-Object { $_.pos[0] -eq 5 -and $_.pos[1] -eq 80 -and $_.pos[2] -eq 2 }).state } else { $row["${kind}Powered"] }
                            if ($value -cne $previous) { $observed += [pscustomobject]@{ tick = $row.tick; value = $value }; $previous = $value }
                        }
                        Check ($observed.Count -eq 2) "$name : trace does not exercise two $kind edges"
                        for ($i = 0; $i -lt [Math]::Min($observed.Count, $events.Count); $i++) {
                            $value = if ($kind -eq 'component') { $events[$i].state } else { $events[$i].powered }
                            Check ($observed[$i].tick -eq $events[$i].tick -and $observed[$i].value -ceq $value) "$name : $kind event inconsistent with trace"
                        }
                    }
                    $source = @($result.events | Where-Object { $_.kind -eq 'source' })
                    $input = @($result.events | Where-Object { $_.kind -eq 'input' })
                    $component = @($result.events | Where-Object { $_.kind -eq 'component' })
                    $nominal = if ($fixture -eq 'repeater-4') { 8 } else { 2 }
                    $on = $component[0].tick - $input[0].tick
                    $off = $component[1].tick - $input[1].tick
                    $expectedOn = if ($mode -eq 'direct') { $nominal - 1 } else { $nominal }
                    $expectedOff = if ($mode -eq 'direct' -and $device -eq 'lever') { $nominal - 1 } else { $nominal }
                    Check ($on -eq $expectedOn -and $off -eq $expectedOff) "$name : component delays $on/$off, expected $expectedOn/$expectedOff"
                    $adapter = if ($mode -eq 'direct') { 0 } else { 1 }
                    Check ($input[0].tick - $source[0].tick -eq $adapter) "$name : wrong adapter activation delay"
                    $adapterOff = if ($mode -eq 'direct') { 0 } elseif ($device -eq 'lever') { 1 } else { 2 }
                    Check ($input[1].tick - $source[1].tick -eq $adapterOff) "$name : wrong adapter deactivation delay"
                    Check ($source[0].phase -eq 'before-time-increment' -and $source[0].worldTime -eq $trace[0].state.worldTime) "$name : action in incorrect world phase"
                    Check ($input[0].phase -eq $(if ($mode -eq 'direct') { 'before-time-increment' } else { 'world-tick' })) "$name : input in incorrect world phase"
                    if ($device -ne 'lever') {
                        $width = if ($device -eq 'stone-button') { 19 } else { 29 }
                        Check ($source[1].tick - $source[0].tick -eq $width -and $input[1].tick - $input[0].tick -eq $width + $adapterOff - $adapter) "$name : vanilla pulse duration changed"
                        Check ($source[1].phase -eq 'world-tick' -and $input[1].phase -eq 'world-tick') "$name : button did not release during world tick"
                    }
                    if ($fixture -eq 'piston') {
                        $piston = @($result.opened.blocks | Where-Object { $_.pos[0] -eq 7 -and $_.pos[1] -eq 80 -and $_.pos[2] -eq 2 })[0]
                        Check ($piston.state.Contains('extended=false')) "$name : piston did not retract when open"
                        Check (@($tickRows | Where-Object { @($_.state.blocks | Where-Object { $_.state.Contains('minecraft:moving_piston') }).Count -gt 0 }).Count -gt 0) "$name : no piston movement observed"
                    }
                    $row = [pscustomobject]@{ name = $name; fixture = $fixture; device = $device; mode = $mode; onDelay = $on; offDelay = $off; expectedOnDelay = $expectedOn; expectedOffDelay = $expectedOff; adapterOnDelay = $adapter; adapterOffDelay = $adapterOff; sourcePulseTicks = $source[1].tick - $source[0].tick; inputPulseTicks = $input[1].tick - $input[0].tick; lastTick = $result.lastTick }
                    $signature = @($trace | ForEach-Object {
                        $state = $_.state.Clone(); $state.Remove('worldTime'); $state.Remove('timeOfDay')
                        # Compare deadlines relative to input time; retain every priority and order field.
                        foreach ($field in @('blockTicks', 'fluidTicks')) {
                            $state[$field] = @($state[$field] | ForEach-Object { $tick = $_.Clone(); $tick.triggerTick -= $trace[0].state.worldTime; $tick })
                        }
                        [ordered]@{ tick = $_.tick; event = $_.event; phase = $_.phase; sourcePowered = $_.sourcePowered; inputPowered = $_.inputPowered; state = $state }
                    })
                    $hasher = [Security.Cryptography.SHA256]::Create()
                    try { $result['traceSignature'] = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes((Canonical $signature)))).Replace('-', '') }
                    finally { $hasher.Dispose() }
                    $runs.Add($row); $repetitions += $result
                } catch { $failures.Add("$name : $($_.Exception.Message)") }
            }
            Check ($repetitions.Count -eq 3) "$fixture/$device/$mode : missing repetitions"
            if ($repetitions.Count -eq 3) {
                $identical = $true
                foreach ($repeat in $repetitions[1..2]) {
                    $same = $repeat.traceSignature -ceq $repetitions[0].traceSignature -and $repeat.lastTick -eq $repetitions[0].lastTick -and (Canonical $repeat.opened) -ceq (Canonical $repetitions[0].opened)
                    Check $same "$fixture/$device/$mode : nonrepeatable trace or state"
                    $identical = $identical -and $same
                }
                $repeatability.Add([pscustomobject]@{ fixture = $fixture; device = $device; mode = $mode; tracesIdentical = $identical; traceSignature = $repetitions[0].traceSignature })
                $byMode[$mode] = $repetitions[0]
            }
        }
        if ($byMode.Count -eq 2) {
            $identical = (Canonical $byMode.direct.opened) -ceq (Canonical $byMode.repeater.opened) -and (Canonical $byMode.direct.closed) -ceq (Canonical $byMode.repeater.closed)
            Check ($identical) "$fixture/$device : direct and repeater endpoints differ"
            $pairs.Add([pscustomobject]@{ fixture = $fixture; device = $device; endpointsIdentical = $identical })
        }
    }
}
$verdict = [pscustomobject]@{
    success = $failures.Count -eq 0 -and $runs.Count -eq 18 * $Fixtures.Count
    timingReproduced = $runs.Count -eq 18 * $Fixtures.Count -and @($runs | Where-Object { $_.onDelay -ne $_.expectedOnDelay -or $_.offDelay -ne $_.expectedOffDelay }).Count -eq 0
    repeatable = $repeatability.Count -eq 6 * $Fixtures.Count -and @($repeatability | Where-Object { !$_.tracesIdentical }).Count -eq 0
    endpointsIdentical = $pairs.Count -eq 3 * $Fixtures.Count -and @($pairs | Where-Object { !$_.endpointsIdentical }).Count -eq 0
    runs = $runs.ToArray(); repeatability = $repeatability.ToArray(); pairs = $pairs.ToArray(); failures = $failures.ToArray()
}
$verdict | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $ExperimentDirectory 'verdict.json') -Encoding utf8
$markdown = @('# Verdict du prototype des entrées', '', "Succès : **$($verdict.success)** ; $($runs.Count) exécutions, $($pairs.Count) comparaisons de modes.", '', "Décalage reproduit : $($verdict.timingReproduced). Répétabilité : $($verdict.repeatable). États entre modes identiques : $($verdict.endpointsIdentical).", '', '| Exécution | Délai activation | Délai désactivation | Adaptateur activation | Fin du cycle |', '| --- | ---: | ---: | ---: | ---: |')
foreach ($row in $runs) { $markdown += "| $($row.name) | $($row.onDelay) | $($row.offDelay) | $($row.adapterOnDelay) | $($row.lastTick) |" }
$markdown += ''
foreach ($failure in $failures) { $markdown += "- Échec : $failure" }
$markdown | Set-Content -LiteralPath (Join-Path $ExperimentDirectory 'verdict.md') -Encoding utf8
$verdict
