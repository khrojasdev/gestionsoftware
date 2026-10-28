@echo off
cd /d "%~dp0"
docker compose down
echo Trazo detenido. Los datos se conservan en el volumen trazo_postgres_data.
pause
