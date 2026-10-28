param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop no está iniciado."
}

& docker compose --project-directory $projectRoot up --build -d
if ($LASTEXITCODE -ne 0) {
    throw "No fue posible iniciar Trazo con Docker Compose."
}

Write-Host "Esperando a http://localhost:8000/health ..."
for ($i = 0; $i -lt 90; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing "http://localhost:8000/health" -TimeoutSec 2 | Out-Null
        Write-Host "Trazo listo en http://localhost:8000"
        if (-not $NoBrowser) { Start-Process "http://localhost:8000" }
        exit 0
    } catch {
        Start-Sleep -Seconds 2
    }
}
throw "La aplicación no respondió. Revisa: docker compose logs -f app"
