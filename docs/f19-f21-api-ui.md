# Referencia F19–F21: contratos persistentes

## Alcance

La entrega final conecta la UI React con FastAPI y PostgreSQL. La UI no calcula
ni simula localmente: consulta datos persistidos y envía cambios al backend.

## Contratos principales

| Operación | Método y ruta | Resultado |
|---|---|---|
| Cargar Gantt | `GET /api/v1/projects/{project_id}/gantt` | Filas jerárquicas, baseline, proyección y dependencias |
| Dashboard | `GET /api/v1/projects/{project_id}/dashboard` | Métricas de proyecto, costos, cambios, KPI, dashboards y snapshots |
| Snapshots KPI | `GET /api/v1/projects/{project_id}/kpis/snapshots` | Valores por KPI y fecha de corte |
| Líneas base | `GET /api/v1/projects/{project_id}/baselines` | Versiones inmutables y estado vigente |
| What-if | `POST /api/v1/change-requests/{request_id}/impact` | Delta de plazo, costo, contingencia y recursos |
| Comparar | `POST /api/v1/projects/{project_id}/baselines/{baseline_id}/compare` | Cambios de campos contra baseline |
| Aplicar | `POST /api/v1/change-requests/{request_id}/apply` | Nueva baseline y propagación transaccional |

Las propuestas F7 aceptan actualizaciones de tarea (por ejemplo `task_id` y
`duration_days`); el actor se obtiene de autenticación y no se acepta como campo
controlado por el cliente. Las respuestas pueden venir envueltas en `{data: ...}`.

## Importación real

`POST /api/v1/projects/import/preview` y
`POST /api/v1/projects/{project_id}/imports` reciben `file` como multipart. Se
aceptan XLSX/CSV dentro de los límites del importador; la validación precede a
la persistencia y la operación es todo-o-nada. El endpoint no acepta
`source_path`, y la API rechaza fuentes dentro de `insumos/`.

## Ejecución Windows/Docker

```powershell
Copy-Item ".env.example" ".env"
# Editar .env y establecer AUTH_SECRET con al menos 32 caracteres
docker compose up --build
```

Frontend: `http://localhost:5173`; API/OpenAPI: `http://localhost:8000/docs`;
PostgreSQL: puerto host `5433`. `docker compose down` conserva datos y
`docker compose down -v` elimina el volumen `trazo_postgres_data`.

## Límites de prueba

Los contratos se verifican con pytest (`test_api_contracts.py` y
`test_f21_contracts.py`) y las reglas con las suites de motor, importador,
integridad, RBAC, KPI y seeds. No existe E2E de navegador ni prueba que levante
Docker completo; la inspección visual se ejecuta con los guiones F9/F18.
