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

Los scripts de carga y conversión de datos se incorporarán en las fases F2 y posteriores. No deben modificar `insumos/`.
