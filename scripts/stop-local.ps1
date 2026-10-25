$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& docker compose --project-directory $projectRoot down
if ($LASTEXITCODE -ne 0) {
    throw "No fue posible detener Trazo con Docker Compose."
}
