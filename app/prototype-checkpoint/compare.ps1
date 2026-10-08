param([Parameter(Mandatory)][string]$TraceDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# All fields participate, including world clocks and NBT numeric types.
function Find-Differences($Expected, $Actual, [string]$Path = '$') {
    if ($null -eq $Expected -or $null -eq $Actual) {
        if ($null -ne $Expected -or $null -ne $Actual) {
            [pscustomobject]@{ path = $Path; expected = $Expected; actual = $Actual }
        }
        return
    }
    if ($Expected -is [System.Collections.IDictionary] -and $Actual -is [System.Collections.IDictionary]) {
        $keys = @(@($Expected.Keys) + @($Actual.Keys) | Sort-Object -Unique -CaseSensitive)
        foreach ($key in $keys) {
            if (!$Expected.Contains($key) -or !$Actual.Contains($key)) {
                [pscustomobject]@{ path = "$Path.$key"; expected = $Expected[$key]; actual = $Actual[$key] }
            } else { Find-Differences $Expected[$key] $Actual[$key] "$Path.$key" }
        }
    } elseif ($Expected -is [array] -and $Actual -is [array]) {
        if ($Expected.Count -ne $Actual.Count) {
            [pscustomobject]@{ path = "$Path.length"; expected = $Expected.Count; actual = $Actual.Count }
        }
        for ($index = 0; $index -lt [Math]::Min($Expected.Count, $Actual.Count); $index++) {
            Find-Differences $Expected[$index] $Actual[$index] "$Path[$index]"
        }
    } elseif ($Expected.GetType() -ne $Actual.GetType() -or $Expected -cne $Actual) {
        [pscustomobject]@{ path = $Path; expected = $Expected; actual = $Actual }
    }
}

function Read-Trace([string]$Name) {
    $rows = @(Get-Content -LiteralPath (Join-Path $TraceDirectory "$Name.jsonl") |
        ForEach-Object { ConvertFrom-Json -InputObject $_ -AsHashtable })
    if ($rows.Count -ne 83 -or $rows[0].event -ne 'initial' -or $rows[-1].tick -ne 80) {
        throw "Incomplete trace: $Name (expected initial, two inputs and 80 ticks)"
    }
    $tickRows = @($rows | Where-Object { $_.event -eq 'tick' })
    if ($tickRows.Count -ne 80) { throw "Invalid tick count: $Name" }
    for ($index = 0; $index -lt 80; $index++) {
        if ($tickRows[$index].tick -ne $index + 1 -or
            $tickRows[$index].state.worldTime -ne $rows[0].state.worldTime + $index + 1) {
            throw "Non-consecutive ticks: $Name"
        }
    }
    return ,$rows
}

$reference = Read-Trace 'reference'
$results = @(foreach ($attempt in 1..3) {
    $name = "replay-$attempt"
    $actual = Read-Trace $name
    $initialDiff = @(Find-Differences $reference[0] $actual[0])
    $first = $null
    for ($index = 0; $index -lt $reference.Count; $index++) {
        $diff = @(Find-Differences $reference[$index] $actual[$index])
        if ($diff.Count -gt 0) {
            $first = [pscustomobject]@{
                row = $index; tick = $reference[$index].tick; event = $reference[$index].event; fields = $diff
            }
            break
        }
    }
    [pscustomobject]@{
        run = $name; initialStateIdentical = ($initialDiff.Count -eq 0)
        executionIdentical = ($null -eq $first); initialDifferences = $initialDiff; firstDivergence = $first
    }
})
$verdict = [pscustomobject]@{
    success = (@($results | Where-Object { !$_.executionIdentical }).Count -eq 0)
    observationsPerRun = 83; replayCount = 3; results = $results
    limitation = 'Fixed static fixture only; no guarantee for other builds or checkpoints during transitions.'
}
$verdict | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $TraceDirectory 'verdict.json') -Encoding utf8
$lines = @('# Checkpoint prototype verdict', '', "Success: $($verdict.success)", '')
foreach ($result in $results) {
    $lines += "- $($result.run): initial state identical=$($result.initialStateIdentical); execution identical=$($result.executionIdentical)."
    if ($null -ne $result.firstDivergence) {
        $lines += "  First divergence: tick $($result.firstDivergence.tick), event $($result.firstDivergence.event)."
        foreach ($field in $result.firstDivergence.fields) {
            $lines += "  $($field.path): expected $($field.expected), actual $($field.actual)."
        }
    }
}
$lines += @('', $verdict.limitation)
$lines | Set-Content -LiteralPath (Join-Path $TraceDirectory 'verdict.md') -Encoding utf8
$verdict
