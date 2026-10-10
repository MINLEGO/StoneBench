[CmdletBinding()]
param(
    [string]$Java = 'java',
    [string]$CacheSource,
    [switch]$Offline
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required.' }

$gradleVersion = '9.2.1'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\app\controller'))
$runtime = Join-Path $projectRoot '.runtime'
$gradleHome = Join-Path $runtime 'gradle-home'
$gradleDirectory = Join-Path $runtime "gradle-$gradleVersion"
$gradle = Join-Path $gradleDirectory 'bin\gradle.bat'
$archive = Join-Path $runtime "gradle-$gradleVersion-bin.zip"
$archiveHash = '72f44c9f8ebcb1af43838f45ee5c4aa9c5444898b3468ab3f4af7b6076c5bc3f'
$artifact = Join-Path $projectRoot 'build\libs\stonebench-controller-0.1.0.jar'
$launcherName = 'fabric-server-mc.1.21.11-loader.0.19.5-launcher.1.1.2.jar'
$launcherHash = '2B63D293BE54C8F5484A242859CAB841DCEE38511E11B2F82E92211F19872D08'

New-Item -ItemType Directory -Force -Path $runtime, $gradleHome | Out-Null

if ($CacheSource) {
    $sourceRuntime = [IO.Path]::GetFullPath($CacheSource)
    $sourceGradleHome = Join-Path $sourceRuntime 'gradle-home'
    $sourceLauncher = Join-Path $sourceRuntime $launcherName
    if (Test-Path -LiteralPath $sourceLauncher) {
        if ((Get-FileHash -LiteralPath $sourceLauncher -Algorithm SHA256).Hash.ToUpperInvariant() -ne $launcherHash) {
            throw 'CacheSource Fabric launcher SHA-256 mismatch.'
        }
        $targetLauncher = Join-Path $runtime $launcherName
        if (!(Test-Path -LiteralPath $targetLauncher)) { Copy-Item -LiteralPath $sourceLauncher -Destination $targetLauncher }
    }
    $sourceDistribution = Join-Path $sourceRuntime "gradle-$gradleVersion"
    if (!(Test-Path -LiteralPath $gradle) -and (Test-Path -LiteralPath (Join-Path $sourceDistribution 'bin\gradle.bat'))) {
        New-Item -ItemType Directory -Force -Path $gradleDirectory | Out-Null
        Get-ChildItem -LiteralPath $sourceDistribution -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $gradleDirectory -Recurse -Force
        }
    }

    $sourceModules = Join-Path $sourceGradleHome 'caches\modules-2'
    $targetModules = Join-Path $gradleHome 'caches\modules-2'
    if (Test-Path -LiteralPath $sourceModules) {
        foreach ($file in Get-ChildItem -LiteralPath $sourceModules -File -Recurse -Force) {
            if ($file.Name -match '\.(lock|lck|part|tmp)$') { continue }
            $relative = $file.FullName.Substring($sourceModules.TrimEnd('\').Length + 1)
            $destination = Join-Path $targetModules $relative
            if (!(Test-Path -LiteralPath $destination)) {
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
                Copy-Item -LiteralPath $file.FullName -Destination $destination
            }
        }
    }

    $sourceLoom = Join-Path $sourceGradleHome 'caches\fabric-loom\1.21.11'
    $sourceServer = Join-Path $sourceLoom 'minecraft-server.jar'
    $sourceInfoPath = Join-Path $sourceLoom 'mojang_minecraft_info.json'
    if ((Test-Path -LiteralPath $sourceServer) -and (Test-Path -LiteralPath $sourceInfoPath)) {
        $sourceInfo = Get-Content -LiteralPath $sourceInfoPath -Raw | ConvertFrom-Json
        $sourceHash = (Get-FileHash -LiteralPath $sourceServer -Algorithm SHA1).Hash
        if ($sourceHash -ne $sourceInfo.downloads.server.sha1) { throw 'CacheSource Minecraft server SHA-1 mismatch.' }

        $targetLoom = Join-Path $gradleHome 'caches\fabric-loom\1.21.11'
        foreach ($file in Get-ChildItem -LiteralPath $sourceLoom -File -Recurse -Force) {
            if ($file.Name -match '\.(lock|lck|part|tmp)$') { continue }
            $relative = $file.FullName.Substring($sourceLoom.TrimEnd('\').Length + 1)
            $destination = Join-Path $targetLoom $relative
            if (!(Test-Path -LiteralPath $destination)) {
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
                Copy-Item -LiteralPath $file.FullName -Destination $destination
            }
        }
    }
}

$javaCommand = Get-Command $Java -ErrorAction Stop
$javaExe = $javaCommand.Source
$javaVersion = (& $javaExe -version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $javaVersion -notmatch 'version "21(?:\.|")') {
    throw "Java 21 is required; '$javaExe' reported: $javaVersion"
}
$javaHome = Split-Path -Parent (Split-Path -Parent $javaExe)
$oldJavaHome = $env:JAVA_HOME
$oldPath = $env:PATH
$oldGradleHome = $env:GRADLE_USER_HOME

try {
    $env:JAVA_HOME = $javaHome
    $env:PATH = (Join-Path $javaHome 'bin') + [IO.Path]::PathSeparator + $oldPath
    $env:GRADLE_USER_HOME = $gradleHome

    if (!(Test-Path -LiteralPath $gradle)) {
        if (!(Test-Path -LiteralPath $archive)) {
            $partial = "$archive.partial"
            try {
                Invoke-WebRequest "https://services.gradle.org/distributions/gradle-$gradleVersion-bin.zip" -OutFile $partial
                if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archiveHash) {
                    throw 'Gradle archive SHA-256 mismatch.'
                }
                Move-Item -LiteralPath $partial -Destination $archive
            } catch {
                Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
                throw
            }
        } elseif ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archiveHash) {
            throw 'Gradle archive SHA-256 mismatch.'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
    }

    $gradleVersionOutput = (& $gradle --version --no-daemon 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $gradleVersionOutput -notmatch "Gradle $gradleVersion") {
        throw "Expected Gradle $gradleVersion; output was: $gradleVersionOutput"
    }

    $buildFile = Get-Content -LiteralPath (Join-Path $projectRoot 'build.gradle') -Raw
    foreach ($required in @(
        "id 'fabric-loom' version '1.14.10'",
        "minecraft 'com.mojang:minecraft:1.21.11'",
        "mappings 'net.fabricmc:yarn:1.21.11+build.3:v2'",
        "modImplementation 'net.fabricmc:fabric-loader:0.19.5'"
    )) {
        if (!$buildFile.Contains($required)) { throw "Pinned build dependency is missing: $required" }
    }

    Push-Location $projectRoot
    try {
        $gradleArguments = @('build','--no-daemon','--console=plain')
        if ($Offline) { $gradleArguments += '--offline' }
        & $gradle @gradleArguments
        if ($LASTEXITCODE -ne 0) { throw 'Controller build failed.' }
    } finally {
        Pop-Location
    }
} finally {
    $env:JAVA_HOME = $oldJavaHome
    $env:PATH = $oldPath
    $env:GRADLE_USER_HOME = $oldGradleHome
}

if (!(Test-Path -LiteralPath $artifact)) { throw "Build artifact not found: $artifact" }
Write-Output $artifact
