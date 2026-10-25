# Scripts de desarrollo

Los comandos de desarrollo se ejecutan desde la raíz, que puede tener espacios en su ruta. Para Windows se prefieren PowerShell y Python:

```powershell
docker compose up --build
docker compose down
python -m pytest "backend\tests"
```

También puedes iniciar y detener desde cualquier ubicación:

```powershell
& ".\scripts\start-local.ps1" -Build
& ".\scripts\stop-local.ps1"
```

La carga final se realiza desde la UI con un archivo XLSX/CSV multipart. Los
scripts de seeds reconstruyen y verifican datos, pero no cargan rutas del host en
la API ni modifican `insumos/`.
