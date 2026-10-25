# Manual de usuario

## 1. Preparar la demostración

1. En Windows 11, copiar `.env.example` a `.env`, definir `AUTH_SECRET` con al
   menos 32 caracteres y ejecutar `docker compose up --build` desde la raíz, o iniciar
   backend y frontend según el [README](../README.md).
2. Generar y verificar el caso mínimo:
   `python seeds/build_seed_b.py` y `python seeds/verificar_f9.py`.
3. Abrir la aplicación, iniciar sesión, importar `seeds/Seed_B_Caso_Prueba_Minimo.xlsx` y
   confirmar solo después de que la vista previa no muestre errores.

## 2. Importar y planificar

El asistente sigue **subir → mapear → validar → vista previa → confirmar** y
envía los bytes mediante `multipart/form-data`; nunca envía una ruta local.
Después de confirmar, la Carta Gantt muestra la jerarquía plegable y la línea
base. Para editar una duración, seleccionar una fila, cambiar el valor y guardar;
usar **Recalcular** para propagar a sucesoras. Un ciclo o una referencia inválida
debe rechazarse sin guardar parcialmente.

La aplicación no tiene un módulo EDT separado. La jerarquía se consulta en la
Carta Gantt: etapa, actividad, subactividad e hito se identifican por su fila y
`padre_id`.

## 3. Recursos, KPI y permisos

- En recursos, seleccionar una tarea y asignar un recurso; comprobar horas,
  tarifa, costo y carga.
- En KPI, revisar fórmula, meta, snapshots y valor persistido. Las fórmulas se validan en
  backend; la interfaz no sustituye el cálculo determinista.
- El rol Administrador puede editar planificación y aprobar cambios. El rol de
  consulta/integrante puede consultar y, según la operación, registrar avance o
  solicitudes, pero no debe saltarse las reglas del backend.

## 4. Gestión del cambio y tableros

Abrir una solicitud en el panel F7, revisar el impacto simulado, comparar contra
la línea base vigente y aplicar solo una solicitud autorizada. Comprobar la nueva
línea base y los efectos en Gantt, costo, KPI y dashboard.

## 5. Límites conocidos

- El repositorio tiene pruebas unitarias, de integración de API y de checklist,
  pero **no** una suite E2E de navegador.
- Docker está documentado como ejecución local reproducible; levantarlo requiere
  Docker Desktop y no equivale a una prueba E2E automatizada.
- La validación final de los tres escenarios, las barras visuales y la
  actualización de tableros se registra con el guion manual.
