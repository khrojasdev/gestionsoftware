# Manual de usuario

## Roles

| Rol | Alcance |
|---|---|
| **Administrador** | Todos los permisos. Crea usuarios, asigna roles y elimina proyectos. |
| **Jefe de Proyecto** | Crea, importa y edita proyectos; duraciones, precedencias, recursos y tarifas; verifica criterios de hitos; configura KPI; avanza, aprueba, rechaza y aplica solicitudes de cambio. |
| **Integrante** | Consulta todo; registra avance real solo en tareas asignadas a su recurso; adjunta evidencias; crea solicitudes de cambio. |

La interfaz oculta lo que el rol no permite y la API lo rechaza (403) aunque se intente
por otro medio. El vínculo usuario ↔ profesional se define en **Recursos** (editar recurso → «Usuario vinculado»).

## Proyectos

La barra superior muestra el proyecto activo (selector), su fecha de corte y la línea
base vigente. En **Proyectos** se ve cada proyecto con avance real vs planificado, SPI,
CPI, término proyectado y cambios abiertos. Se puede crear un proyecto vacío, editar
datos (cambiar la fecha de corte recalcula avance planificado, EVM y KPI), cerrarlo
(exige hitos cumplidos y cambios cerrados) o eliminarlo (solo Administrador).

## Importar la Carta Gantt

1. **Descargar plantilla .xlsx** para ver el formato: una hoja por entidad (Proyecto,
   Gantt, Recursos, Asignaciones, Calendario, Criterios, Hitos_Tareas, KPI y etapas de cambio).
   También se acepta directamente el libro del curso (Cronograma / Planificación / Calendario).
2. Arrastrar el archivo. Se muestra el formato detectado, las hojas y columnas encontradas,
   los conteos, los errores (bloquean) y advertencias (no bloquean) y una vista previa.
3. **Importar y calcular** crea el proyecto; si el código ya existe se ofrece
   **Reemplazar planificación**. En ambos casos se calcula el cronograma, costos y KPI y se
   congela una línea base.

## Actividades y precedencias

- Filtros: mis tareas, subactividades e hitos, ruta crítica, atrasadas/desplazadas,
  jerarquía completa; búsqueda y etapa.
- Al seleccionar una fila, el panel derecho muestra plan, línea base, proyección,
  avance, costo y holgura.
- **Planificación**: cambiar nombre o duración (días hábiles) y «Guardar y recalcular».
- **Precedencias**: cambiar tipo (FS, SS, FF, SF) y desfase, quitar o agregar. Un ciclo se
  rechaza con el detalle del ciclo.
- **Avance real**: porcentaje, fechas reales, costo real y comentario. Un hito solo llega a
  100 % si todos sus criterios están cumplidos.
- Cada cambio abre un resumen **antes / después** con los elementos recalculados y el
  efecto en el término del proyecto.

## Carta Gantt

Jerarquía etapa → actividad → subactividad/hito (sin módulo EDT aparte). Barra verde
clara = plan vigente, relleno = avance real, rojo = ruta crítica, ámbar = atrasada,
rayado = desplazamiento proyectado, línea gris inferior = línea base, rombo = hito,
línea naranja = fecha de corte, línea discontinua = término comprometido. Zoom en
días/semanas/meses, plegar por nivel, solo ruta crítica, mostrar/ocultar flechas y
línea base. Al hacer clic en una fila se abre un panel con detalle y edición rápida de duración.

## Recursos y costos

- **Por recurso**: tarifa, capacidad, tareas, horas o cantidad, costo, carga máxima y usuario
  vinculado; al expandir se ven sus asignaciones.
- **Por tarea**: cada asignación (horas · h/día · costo). Clic para editar; «+» para asignar.
  La opción «Duración guiada por esfuerzo» recalcula la duración = horas totales ÷ horas diarias.
- **Carga semanal**: mapa de calor por profesional y semana; clic en una celda para ver las tareas.
- **Costos y calendario**: costo por tipo de recurso y por etapa; jornada y feriados.
- Las sobreasignaciones (más horas diarias que la capacidad) se alertan arriba.

## Hitos

Indicadores (cumplidos, a tiempo, desplazados, desviación del cierre), línea de tiempo y
un acordeón por hito con sus tareas y criterios de aceptación. El Jefe de Proyecto marca
cada criterio como Cumplido / No cumplido con una observación; cualquiera puede adjuntar
evidencias. Al cumplirse todos, el hito queda al 100 %.

## Administrador de KPI

Pestañas Proyecto e hitos (P01–P08) y Gestión del cambio (C01–C12; los adicionales se
marcan). Para cada KPI: valor, estado, fórmula con los valores sustituidos, detalle de
cada variable, tendencia y versiones. El Jefe de Proyecto puede editar la fórmula (con
chips de variables), umbrales y meta, probar la fórmula antes de guardar, crear KPI y
registrar las mediciones manuales de adopción y capacitación. Regla de umbrales: si el
verde es mayor que el amarillo, más alto es mejor; si es menor, más bajo es mejor.

## Solicitudes de cambio

Flujo de 10 etapas con SLA: Registro → Revisión inicial → Clasificación y prioridad →
Análisis de impacto → Revisión del comité → Decisión → Planificación del cambio →
Implementación → Verificación → Cierre y línea base.

1. Cualquier usuario registra una solicitud (título, descripción, justificación, tipo,
   prioridad, área).
2. El Jefe de Proyecto define la **propuesta** (tareas, nuevas duraciones, horas o
   cantidades adicionales) y usa **Simular impacto**: término propuesto, costo, consumo de
   contingencia, reserva de plazo, efecto en recursos y tareas afectadas.
3. Avanza etapas con comentario; en Decisión aprueba o rechaza.
4. **Aplicar cambio al plan** recalcula todo y congela una nueva línea base.
5. Verificación y Cierre dejan la solicitud cerrada. El historial muestra transiciones
   y auditoría.

## Tableros

- **Tablero del proyecto**: avance, SPI/CPI, EAC/VAC, término proyectado y reserva, hitos,
  curva S (PV/EV/AC), avance por etapa, KPI, alertas, tareas atrasadas, hitos y carga.
- **Tablero del cambio**: solicitudes, aprobación, ciclo, impacto, contingencia, SLA,
  embudo por etapa, tiempos vs SLA, matriz impacto × probabilidad, KPI y alertas.

## Reiniciar la demostración

`reiniciar-demo.bat` (Docker) o `python -m app.demo --reset` en `backend/`.
