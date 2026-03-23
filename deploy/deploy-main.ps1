param(
    [string[]]$Services = @("postgres", "runner", "monitor"),
    [string[]]$RequiredEnv = @()
)

$ErrorActionPreference = "Stop"

function Normalize-ArgList {
    param([string[]]$Values)

    $normalized = @()
    foreach ($value in $Values) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }

        foreach ($part in ($value -split ",")) {
            $trimmed = $part.Trim()
            if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                $normalized += $trimmed
            }
        }
    }

    return $normalized | Select-Object -Unique
}

$Services = Normalize-ArgList $Services
$RequiredEnv = Normalize-ArgList $RequiredEnv

$repoRoot = Split-Path -Parent $PSScriptRoot
$deployRoot = Join-Path $repoRoot ".worktrees\deploy-main"
$composeFile = Join-Path $deployRoot "deploy\docker-compose.yml"
$envFile = Join-Path $deployRoot ".env"
$projectDir = Join-Path $deployRoot "deploy"

$requiredPaths = @(
    @{ Label = "deploy worktree"; Path = $deployRoot }
    @{ Label = "compose file"; Path = $composeFile }
    @{ Label = "env file"; Path = $envFile }
    @{ Label = "compose project directory"; Path = $projectDir }
)

foreach ($item in $requiredPaths) {
    if (-not (Test-Path $item.Path)) {
        throw "Missing required $($item.Label): $($item.Path)"
    }
}

function Invoke-DockerCompose {
    param(
        [string[]]$ComposeArgs,
        [switch]$Capture
    )

    $dockerArgs = @(
        "compose",
        "--project-directory", $projectDir,
        "--env-file", $envFile,
        "-f", $composeFile
    ) + $ComposeArgs

    if ($Capture) {
        $output = & docker @dockerArgs 2>&1
        if ($LASTEXITCODE -ne 0) {
            $output | Write-Host
            throw "docker compose failed: $($ComposeArgs -join ' ')"
        }
        return $output
    }

    & docker @dockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed: $($ComposeArgs -join ' ')"
    }
}

function Get-ServiceRequirements {
    param(
        [string]$ServiceName,
        [string[]]$ExtraEnv
    )

    $defaults = @{
        "runner" = @("VNPY_DATABASE_HOST", "VNPY_LOG_DIR")
        "monitor" = @("VNPY_DATABASE_HOST", "MONITOR_LOG_DIR")
        "postgres" = @("POSTGRES_USER", "POSTGRES_DB")
    }

    $required = @()
    if ($defaults.ContainsKey($ServiceName)) {
        $required += $defaults[$ServiceName]
    }
    $required += $ExtraEnv
    return $required | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
}

function Test-ServiceEnv {
    param(
        [string]$ServiceName,
        [string[]]$EnvNames
    )

    foreach ($envName in $EnvNames) {
        $value = Invoke-DockerCompose -ComposeArgs @("exec", "-T", $ServiceName, "sh", "-lc", "printenv $envName") -Capture
        $joined = ($value | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($joined)) {
            throw "Required environment variable '$envName' is empty in service '$ServiceName'."
        }
    }
}

Write-Host "[1/3] Validating docker compose config..."
Invoke-DockerCompose -ComposeArgs @("config")

Write-Host "[2/3] Building and starting services..."
Invoke-DockerCompose -ComposeArgs (@("up", "-d", "--build") + $Services)

$runningServices = Invoke-DockerCompose -ComposeArgs @("ps", "--status", "running", "--services") -Capture
$runningSet = @{}
foreach ($serviceName in $runningServices) {
    $trimmed = ($serviceName | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
        $runningSet[$trimmed] = $true
    }
}

foreach ($serviceName in $Services) {
    if (-not $runningSet.ContainsKey($serviceName)) {
        throw "Service '$serviceName' is not running after docker compose up."
    }
}

Write-Host "[3/3] Checking required container environment variables..."
foreach ($serviceName in $Services) {
    $envNames = Get-ServiceRequirements -ServiceName $serviceName -ExtraEnv $RequiredEnv
    if ($envNames.Count -eq 0) {
        continue
    }
    Test-ServiceEnv -ServiceName $serviceName -EnvNames $envNames
}

Write-Host "Deployment verification passed."
