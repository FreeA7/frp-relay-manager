[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$HostAlias = "kchat",
    [string]$RemoteRoot = "/src/frp_relay",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$serverPath = Join-Path $repoRoot "server"
$deployPath = Join-Path $repoRoot "deploy"
$tempBase = [System.IO.Path]::GetTempPath()
$stageRoot = Join-Path $tempBase ("frp-relay-deploy-" + [guid]::NewGuid().ToString("N"))
$excludedNames = @(
    ".env",
    ".env.local",
    ".env.production",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".vite",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "data",
    "tmp",
    "temp"
)
$excludedExtensions = @(
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".pid",
    ".tmp",
    ".pem",
    ".key",
    ".crt",
    ".p12",
    ".pfx"
)

if (-not (Test-Path -LiteralPath $serverPath -PathType Container)) {
    throw "Missing server directory: $serverPath"
}

if (-not (Test-Path -LiteralPath $deployPath -PathType Container)) {
    throw "Missing deploy directory: $deployPath"
}

Write-Host "Deploy target: $HostAlias`:$RemoteRoot"
Write-Host "Will copy only: server/ and deploy/"
Write-Host "Will not copy: client/, docs/, .git/, .env, local caches, or secrets"

if ($DryRun) {
    Write-Host "Dry run only. No files copied."
    exit 0
}

function Copy-CleanTree {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        if ($excludedNames -contains $_.Name) {
            return
        }

        if (-not $_.PSIsContainer -and ($excludedExtensions -contains $_.Extension)) {
            return
        }

        $target = Join-Path $Destination $_.Name

        if ($_.PSIsContainer) {
            Copy-CleanTree -Source $_.FullName -Destination $target
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

if ($PSCmdlet.ShouldProcess("$HostAlias`:$RemoteRoot", "Create remote directories and copy server/deploy")) {
    try {
        $stageServer = Join-Path $stageRoot "server"
        $stageDeploy = Join-Path $stageRoot "deploy"

        Copy-CleanTree -Source $serverPath -Destination $stageServer
        Copy-CleanTree -Source $deployPath -Destination $stageDeploy
        Get-ChildItem -LiteralPath $stageRoot -Recurse -Force | ForEach-Object {
            if ($_.PSIsContainer) {
                $_.Attributes = $_.Attributes -band (-bnot [System.IO.FileAttributes]::Hidden)
            }
        }

        ssh $HostAlias "mkdir -p '$RemoteRoot'"

        scp -r $stageServer "$HostAlias`:$RemoteRoot/"
        scp -r $stageDeploy "$HostAlias`:$RemoteRoot/"

        ssh $HostAlias "find '$RemoteRoot/server' '$RemoteRoot/deploy' \( -path '*/.venv' -o -path '*/.venv/*' -o -path '*/node_modules' -o -path '*/node_modules/*' -o -path '*/dist' -o -path '*/dist/*' \) -prune -o -type d -exec chmod 755 {} +; find '$RemoteRoot/server' '$RemoteRoot/deploy' \( -path '*/.venv' -o -path '*/.venv/*' -o -path '*/node_modules' -o -path '*/node_modules/*' -o -path '*/dist' -o -path '*/dist/*' \) -prune -o -type f -exec chmod 644 {} +"

        Write-Host "Copied sanitized server/ and deploy/ to $HostAlias`:$RemoteRoot"
        Write-Host "Next: ssh $HostAlias and verify /src/frp_relay before restarting services."
    } finally {
        $resolvedStage = Resolve-Path -LiteralPath $stageRoot -ErrorAction SilentlyContinue

        if ($resolvedStage) {
            $resolvedTemp = (Resolve-Path -LiteralPath $tempBase).Path
            $stagePath = $resolvedStage.Path

            if ($stagePath.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
                Remove-Item -LiteralPath $stagePath -Recurse -Force
            } else {
                Write-Warning "Skipped cleanup because staging path is outside temp: $stagePath"
            }
        }
    }
}
