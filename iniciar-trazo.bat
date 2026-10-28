@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Trazo - iniciando con Docker Desktop...
echo.
docker info >nul 2>&1
if errorlevel 1 (
  echo  [ERROR] Docker Desktop no esta iniciado. Abrelo, espera a que diga "Engine running" y vuelve a ejecutar este archivo.
  pause
  exit /b 1
)
docker compose up --build -d
if errorlevel 1 (
  echo  [ERROR] No fue posible construir o iniciar los contenedores. Revisa el mensaje anterior.
  pause
  exit /b 1
)
echo.
echo  Esperando a que la aplicacion responda (la primera vez carga los datos de demostracion)...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 90;$i++){ try { Invoke-WebRequest -UseBasicParsing http://localhost:8000/health -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 2 } }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
  echo  [AVISO] La aplicacion aun no responde. Revisa los registros con: docker compose logs -f app
  pause
  exit /b 1
)
echo.
echo  Trazo esta listo en http://localhost:8000
echo  Usuarios (contrasena Trazo2026!): admin@trazo.cl, kevin.henriquez@trazo.cl, diego.lopez@trazo.cl
start "" http://localhost:8000
endlocal
