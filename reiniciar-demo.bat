@echo off
cd /d "%~dp0"
echo Se borraran los proyectos y se volvera a cargar la demostracion (Horizonte Conecta y Caso de prueba).
choice /M "Continuar"
if errorlevel 2 exit /b 0
docker compose exec app python -m app.demo --reset
pause
