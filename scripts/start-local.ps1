param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeArgs = @("--project-directory", $projectRoot, "up")

if ($Build) {
    $composeArgs += "--build"
}

& docker compose @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw "No fue posible iniciar Trazo con Docker Compose. Verifica que Docker Desktop esté iniciado."
}
