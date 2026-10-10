[CmdletBinding()]
param(
    [switch]$AcceptEula,
    [switch]$SkipBuild,
    [string]$Java = 'java',
    [string]$Python = 'python',
    [string]$CacheSource,
    [string]$ServerCacheSource,
    [ValidateRange(1, 65534)][int]$BaseMcpPort = 18765,
    [ValidateRange(1, 65534)][int]$BaseGamePort = 25581
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required.' }
if (!$AcceptEula) { throw 'Pass -AcceptEula to accept the Minecraft EULA for these disposable test servers.' }

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$controllerRoot = Join-Path $repoRoot 'app\controller'
$runtime = Join-Path $controllerRoot '.runtime'
$artifact = Join-Path $controllerRoot 'build\libs\stonebench-controller-0.1.0.jar'
$integration = Join-Path $repoRoot 'tests\integration.py'
$buildScript = Join-Path $PSScriptRoot 'build.ps1'

if (!$SkipBuild) {
    $buildArgs = @{ Java = $Java }
    if ($CacheSource) { $buildArgs.CacheSource = $CacheSource }
    & $buildScript @buildArgs

}
if (!(Test-Path -LiteralPath $artifact)) { throw "Controller jar not found: $artifact" }
if (!(Test-Path -LiteralPath $integration)) { throw "Integration suite not found: $integration" }

$javaCommand = Get-Command $Java -ErrorAction Stop
$javaExe = $javaCommand.Source
$javaVersion = (& $javaExe -version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $javaVersion -notmatch 'version "21(?:\.|")') {
    throw "Java 21 is required; '$javaExe' reported: $javaVersion"
}
$pythonCommand = Get-Command $Python -ErrorAction Stop
$pythonExe = $pythonCommand.Source
$pythonArgs = @()
if ([IO.Path]::GetFileNameWithoutExtension($pythonCommand.Name) -eq 'py') { $pythonArgs = @('-3.12') }
$pythonVersion = (& $pythonExe @pythonArgs --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python 3\.12\.') {
    throw "Python 3.12 is required; '$pythonExe' reported: $pythonVersion"
}

$serverCacheRoot = $null
if ($ServerCacheSource) {
    $serverCacheRoot = [IO.Path]::GetFullPath($ServerCacheSource)
    foreach ($directory in @('libraries', 'versions')) {
        if (!(Test-Path -LiteralPath (Join-Path $serverCacheRoot $directory))) {
            throw "Server cache is missing $directory/: $serverCacheRoot"
        }
    }
}
$launcher = Join-Path $runtime 'fabric-server-mc.1.21.11-loader.0.19.5-launcher.1.1.2.jar'
$launcherHash = '2B63D293BE54C8F5484A242859CAB841DCEE38511E11B2F82E92211F19872D08'
if ($CacheSource -and !(Test-Path -LiteralPath $launcher)) {
    $sourceLauncher = Join-Path ([IO.Path]::GetFullPath($CacheSource)) (Split-Path -Leaf $launcher)
    if (Test-Path -LiteralPath $sourceLauncher) {
        if ((Get-FileHash -LiteralPath $sourceLauncher -Algorithm SHA256).Hash.ToUpperInvariant() -ne $launcherHash) {
            throw 'CacheSource Fabric launcher SHA-256 mismatch.'
        }
        Copy-Item -LiteralPath $sourceLauncher -Destination $launcher
    }
}
if (!(Test-Path -LiteralPath $launcher)) {
    $partial = "$launcher.partial"
    try {
        Invoke-WebRequest 'https://meta.fabricmc.net/v2/versions/loader/1.21.11/0.19.5/1.1.2/server/jar' -OutFile $partial
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToUpperInvariant() -ne $launcherHash) {
            throw 'Fabric launcher SHA-256 mismatch.'
        }
        Move-Item -LiteralPath $partial -Destination $launcher
    } catch {
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        throw
    }
} elseif ((Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash.ToUpperInvariant() -ne $launcherHash) {
    throw 'Fabric launcher SHA-256 mismatch.'
}

$loomCache = Join-Path $runtime 'gradle-home\caches\fabric-loom\1.21.11'
$bundledServer = Join-Path $loomCache 'minecraft-server.jar'
$minecraftInfoPath = Join-Path $loomCache 'mojang_minecraft_info.json'
if (!(Test-Path -LiteralPath $bundledServer) -or !(Test-Path -LiteralPath $minecraftInfoPath)) {
    throw 'The Loom-cached Minecraft server and Mojang metadata are required; build the controller first.'
}
$minecraftInfo = Get-Content -LiteralPath $minecraftInfoPath -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $bundledServer -Algorithm SHA1).Hash.ToLowerInvariant() -ne $minecraftInfo.downloads.server.sha1.ToLowerInvariant()) {
    throw 'Loom-cached Minecraft server SHA-1 mismatch.'
}

function Assert-PortAvailable([int]$Port) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
    } catch {
        throw "Required localhost port $Port is already in use."
    } finally {
        $listener.Stop()
    }
}

function Start-Server($Server) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $javaExe
    $info.WorkingDirectory = $Server.Root
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in @(
        '-Xms256M',
        '-Xmx1G',
        "-Dstonebench.port=$($Server.McpPort)",
        '-Dstonebench.test=true',
        '-jar',
        'fabric-server.jar',
        'nogui'
    )) {
        $info.ArgumentList.Add($argument)
    }
    $Server.Process = [Diagnostics.Process]::Start($info)
    $Server.ProcessId = $Server.Process.Id
    $Server.StdoutTask = $Server.Process.StandardOutput.ReadToEndAsync()
    $Server.StderrTask = $Server.Process.StandardError.ReadToEndAsync()
    [IO.File]::WriteAllText((Join-Path $Server.Root 'server.pid'), "$($Server.ProcessId)" + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Wait-Ready($Server, [int]$TimeoutSeconds = 180) {
    $marker = Join-Path $Server.Root 'stonebench\ready'
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while (!(Test-Path -LiteralPath $marker)) {
        if ($Server.Process.HasExited) { throw "Server $($Server.Index) exited before ready; see its saved logs." }
        if ([DateTime]::UtcNow -ge $deadline) { throw "Server $($Server.Index) did not become ready within $TimeoutSeconds seconds." }
        Start-Sleep -Milliseconds 250
    }
}

function Stop-Server($Server) {
    if ($null -eq $Server.Process) { return }
    $process = $Server.Process
    if (!$process.HasExited) {
        $process.StandardInput.WriteLine('stop')
        $process.StandardInput.Flush()
        if (!$process.WaitForExit(30000)) {
            $Server.Killed = $true
            $process.Kill($true)
            if (!$process.WaitForExit(30000)) { throw "Owned server PID $($Server.ProcessId) could not be stopped." }
        }
    }
    $process.WaitForExit()
    $stdout = $Server.StdoutTask.GetAwaiter().GetResult()
    $stderr = $Server.StderrTask.GetAwaiter().GetResult()
    [IO.File]::WriteAllText((Join-Path $Server.Root 'logs\stdout.log'), $stdout, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $Server.Root 'logs\stderr.log'), $stderr, [Text.UTF8Encoding]::new($false))
    $process.Dispose()
    $Server.Process = $null
}

if ($BaseMcpPort -le ($BaseGamePort + 1) -and $BaseGamePort -le ($BaseMcpPort + 1)) { throw 'MCP and Minecraft port ranges must be distinct.' }

$testRoot = Join-Path $runtime ('tests-' + [Guid]::NewGuid().ToString('N'))
$servers = @(
    [pscustomobject]@{ Index = 1; McpPort = $BaseMcpPort; GamePort = $BaseGamePort; Root = Join-Path $testRoot 'server-1'; Process = $null; ProcessId = $null; StdoutTask = $null; StderrTask = $null; Killed = $false },
    [pscustomobject]@{ Index = 2; McpPort = ($BaseMcpPort + 1); GamePort = ($BaseGamePort + 1); Root = Join-Path $testRoot 'server-2'; Process = $null; ProcessId = $null; StdoutTask = $null; StderrTask = $null; Killed = $false }
)
foreach ($server in $servers) {
    Assert-PortAvailable $server.McpPort
    Assert-PortAvailable $server.GamePort
}
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$propertyLines = @(
    'server-ip=127.0.0.1',
    'online-mode=true',
    'white-list=true',
    'enforce-whitelist=true',
    'enable-rcon=false',
    'enable-query=false',
    'level-name=world',
    'level-seed=731928',
    'level-type=minecraft:flat',
    'generator-settings={"layers":[],"biome":"minecraft:plains"}',
    'generate-structures=false',
    'spawn-protection=0',
    'view-distance=2',
    'simulation-distance=2',
    'max-tick-time=60000',
    'pause-when-empty-seconds=-1'
)

foreach ($server in $servers) {
    New-Item -ItemType Directory -Force -Path (Join-Path $server.Root 'mods'), (Join-Path $server.Root '.fabric\server'), (Join-Path $server.Root 'stonebench'), (Join-Path $server.Root 'logs') | Out-Null
    Copy-Item -LiteralPath $launcher -Destination (Join-Path $server.Root 'fabric-server.jar')
    Copy-Item -LiteralPath $artifact -Destination (Join-Path $server.Root 'mods\stonebench-controller.jar')
    Copy-Item -LiteralPath $bundledServer -Destination (Join-Path $server.Root '.fabric\server\1.21.11-server.jar')
    $copiedServer = Join-Path $server.Root '.fabric\server\1.21.11-server.jar'
    if ((Get-FileHash -LiteralPath $copiedServer -Algorithm SHA1).Hash.ToLowerInvariant() -ne $minecraftInfo.downloads.server.sha1.ToLowerInvariant()) { throw 'Copied Minecraft server SHA-1 mismatch.' }
    if ($serverCacheRoot) {
        foreach ($directory in @('libraries', 'versions')) {
            Copy-Item -LiteralPath (Join-Path $serverCacheRoot $directory) -Destination (Join-Path $server.Root $directory) -Recurse
        }
    }
    [IO.File]::WriteAllText((Join-Path $server.Root 'eula.txt'), 'eula=true' + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    $properties = (($propertyLines + "server-port=$($server.GamePort)") -join [Environment]::NewLine) + [Environment]::NewLine
    [IO.File]::WriteAllText((Join-Path $server.Root 'server.properties'), $properties, [Text.UTF8Encoding]::new($false))
}

$oldPorts = $env:STONEBENCH_MCP_PORTS
try {
    Write-Host "Disposable server data and logs: $testRoot"
    foreach ($server in $servers) {
        Write-Host "Starting server $($server.Index): MCP 127.0.0.1:$($server.McpPort), Minecraft 127.0.0.1:$($server.GamePort)"
        Start-Server $server
    }
    foreach ($server in $servers) { Wait-Ready $server }

    $env:STONEBENCH_MCP_PORTS = ($servers.McpPort -join ',')
    $pythonInvocationArgs = @($pythonArgs + $integration)
    Push-Location $repoRoot
    try {
        & $pythonExe @pythonInvocationArgs
        if ($LASTEXITCODE -ne 0) { throw "Integration suite failed with exit code $LASTEXITCODE." }
    $journalArguments = @($pythonArgs + (Join-Path $repoRoot 'tests\verify_journals.py'))
    foreach ($server in $servers) { $journalArguments += Join-Path $server.Root 'stonebench\operations.jsonl' }
    & $pythonExe @journalArguments
    if ($LASTEXITCODE -ne 0) { throw 'Journal clock verification failed.' }
    } finally {
        Pop-Location
    }
} finally {
    $env:STONEBENCH_MCP_PORTS = $oldPorts
    $stopErrors = @()
    foreach ($server in $servers) {
        try {
            Stop-Server $server
        } catch {
            $stopErrors += $_.Exception.Message
        }
    }
    if ($stopErrors.Count -gt 0) { throw ($stopErrors -join [Environment]::NewLine) }
}
if ($servers.Killed -contains $true) { throw 'A test server required PID-scoped termination after its 30 second stop timeout.' }
Write-Host "Integration suite finished; server logs and worlds remain under $testRoot"
