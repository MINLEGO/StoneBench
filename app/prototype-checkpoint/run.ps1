# PROTOTYPE: creates a disposable server; never operates on an existing world.
param([string]$Java = 'java')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required.' }
$runtime = Join-Path $PSScriptRoot '.runtime'
$gradleVersion = '9.2.1'
$gradle = Join-Path $runtime "gradle-$gradleVersion/bin/gradle.bat"
New-Item -ItemType Directory -Force $runtime | Out-Null

function Download([string]$Url, [string]$Destination) {
    if (!(Test-Path -LiteralPath $Destination)) {
        Write-Host "Downloading $Url"
        $temporary = "$Destination.partial"
        Invoke-WebRequest $Url -OutFile $temporary
        Move-Item -LiteralPath $temporary -Destination $Destination
    }
}

$oldGradleHome = $env:GRADLE_USER_HOME
$oldJavaHome = $env:JAVA_HOME
try {
    $javaCommand = (Get-Command $Java -ErrorAction Stop).Source
    $env:JAVA_HOME = Split-Path (Split-Path $javaCommand)
    $env:GRADLE_USER_HOME = Join-Path $runtime 'gradle-home'
    if (!(Test-Path -LiteralPath $gradle)) {
        $archive = Join-Path $runtime 'gradle.zip'
        Download "https://services.gradle.org/distributions/gradle-$gradleVersion-bin.zip" $archive
        $expected = '72f44c9f8ebcb1af43838f45ee5c4aa9c5444898b3468ab3f4af7b6076c5bc3f'
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw 'Gradle archive checksum mismatch'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
    }
    Push-Location $PSScriptRoot
    try {
        & $gradle build --console=plain
        if ($LASTEXITCODE -ne 0) { throw 'Mod build failed' }
    } finally { Pop-Location }
} finally {
    $env:GRADLE_USER_HOME = $oldGradleHome
    $env:JAVA_HOME = $oldJavaHome
}

$launcher = Join-Path $runtime 'fabric-server-mc.1.21.11-loader.0.19.5-launcher.1.1.2.jar'
Download 'https://meta.fabricmc.net/v2/versions/loader/1.21.11/0.19.5/1.1.2/server/jar' $launcher
if ((Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash -ne '2B63D293BE54C8F5484A242859CAB841DCEE38511E11B2F82E92211F19872D08') {
    throw 'Fabric launcher checksum mismatch'
}
$experimentRoot = Join-Path $runtime ('experiment-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$serverRoot = Join-Path $experimentRoot 'server'
$checkpoint = Join-Path $experimentRoot 'checkpoint'
New-Item -ItemType Directory -Force (Join-Path $serverRoot 'mods') | Out-Null
Copy-Item -LiteralPath $launcher -Destination (Join-Path $serverRoot 'fabric-server.jar')
# Loom already downloaded the official bundled server; avoid downloading it twice.
$loomCache = Join-Path $runtime 'gradle-home/caches/fabric-loom/1.21.11'
$minecraftInfo = Get-Content -LiteralPath (Join-Path $loomCache 'mojang_minecraft_info.json') -Raw | ConvertFrom-Json
$bundledServer = Join-Path $loomCache 'minecraft-server.jar'
if ((Get-FileHash -LiteralPath $bundledServer -Algorithm SHA1).Hash -ne $minecraftInfo.downloads.server.sha1) {
    throw 'Minecraft server checksum mismatch'
}
New-Item -ItemType Directory -Force (Join-Path $serverRoot '.fabric/server') | Out-Null
Copy-Item -LiteralPath $bundledServer -Destination (Join-Path $serverRoot '.fabric/server/1.21.11-server.jar')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build/libs/prototype-checkpoint-0.1.0.jar') -Destination (Join-Path $serverRoot 'mods/prototype.jar')
'eula=true' | Set-Content -LiteralPath (Join-Path $serverRoot 'eula.txt') -Encoding utf8
@'
server-ip=127.0.0.1
server-port=25579
online-mode=true
white-list=true
enforce-whitelist=true
enable-rcon=false
enable-query=false
level-name=world
level-seed=731928
level-type=minecraft:flat
generator-settings={"layers":[{"block":"minecraft:bedrock","height":1}],"biome":"minecraft:plains"}
generate-structures=false
spawn-protection=0
view-distance=2
simulation-distance=2
max-tick-time=60000
pause-when-empty-seconds=-1
'@ | Set-Content -LiteralPath (Join-Path $serverRoot 'server.properties') -Encoding utf8
$process = $null
$stdout = $null
$stderr = $null
$boot = 0
$traceRoot = Join-Path $serverRoot 'traces'

function Wait-Condition([scriptblock]$Condition, [int]$TimeoutSeconds = 180) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while (!( & $Condition )) {
        if ($null -ne $process -and $process.HasExited) { throw 'Server exited unexpectedly (see console logs)' }
        $errorFile = Join-Path $traceRoot 'error.txt'
        if (Test-Path -LiteralPath $errorFile) { throw (Get-Content -LiteralPath $errorFile -Raw) }
        if ([DateTime]::UtcNow -gt $deadline) { throw 'Server operation timed out' }
        Start-Sleep -Milliseconds 100
    }
}

function Start-Server {
    $script:boot++
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $javaCommand
    $info.WorkingDirectory = $serverRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in @('-Xms512M', '-Xmx2G', "-Dstonebench.boot=$boot", '-jar', 'fabric-server.jar', 'nogui')) { $info.ArgumentList.Add($argument) }
    $script:process = [System.Diagnostics.Process]::Start($info)
    $script:stdout = $process.StandardOutput.ReadToEndAsync()
    $script:stderr = $process.StandardError.ReadToEndAsync()
    Wait-Condition { Test-Path -LiteralPath (Join-Path $traceRoot "boot-$boot.ready") } -TimeoutSeconds 600
}

function Send-Command([string]$Command) {
    $process.StandardInput.WriteLine($Command)
    $process.StandardInput.Flush()
}

function Stop-Server {
    if ($null -eq $process) { return }
    if (!$process.HasExited) {
        Send-Command 'stop'
        if (!$process.WaitForExit(30000)) { $process.Kill($true); $process.WaitForExit(); throw 'Server did not stop cleanly' }
    }
    [System.IO.File]::WriteAllText((Join-Path $experimentRoot "console-$boot.log"), $stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult())
    $process.Dispose()
    $script:process = $null
}

function Run-Sequence([string]$Name) {
    Send-Command "sb record $Name"
    Wait-Condition { Test-Path -LiteralPath (Join-Path $traceRoot "$Name.done") }
}

Write-Host "Experiment: $experimentRoot"
try {
    Start-Server
    Send-Command 'sb prepare'
    Wait-Condition { Test-Path -LiteralPath (Join-Path $traceRoot 'prepared') }
    # Wait for the flush acknowledgement, not just the command being sent.
    Send-Command 'save-all flush'
    Wait-Condition { Select-String -LiteralPath (Join-Path $serverRoot 'logs/latest.log') -SimpleMatch 'Saved the game' -Quiet }
    New-Item -ItemType Directory $checkpoint | Out-Null
    # session.lock belongs to the running process, not to persisted world state.
    Get-ChildItem -LiteralPath (Join-Path $serverRoot 'world') -Force |
        Where-Object { $_.Name -ne 'session.lock' } |
        Copy-Item -Destination $checkpoint -Recurse
    Run-Sequence 'reference'
    Stop-Server
    foreach ($attempt in 1..3) {
        $worldPath = [System.IO.Path]::GetFullPath((Join-Path $serverRoot 'world'))
        $allowed = [System.IO.Path]::GetFullPath($experimentRoot) + [System.IO.Path]::DirectorySeparatorChar
        if (!$worldPath.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'World path outside experiment directory' }
        Remove-Item -LiteralPath $worldPath -Recurse -Force
        Copy-Item -LiteralPath $checkpoint -Destination $worldPath -Recurse
        Start-Server
        Run-Sequence "replay-$attempt"
        Stop-Server
    }
    $verdict = & (Join-Path $PSScriptRoot 'compare.ps1') -TraceDirectory $traceRoot
    $verdict | ConvertTo-Json -Depth 20 | Write-Host
    Write-Host "Traces and verdict: $traceRoot"
    if (!$verdict.success) { throw "Experiment completed with divergence; see $traceRoot/verdict.md" }
} finally { Stop-Server }
