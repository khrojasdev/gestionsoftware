# Guion de la demostración

Duración sugerida: 10–12 minutos. Antes de empezar ejecuta `reiniciar-demo.bat`
(o `python -m app.demo --reset` en `backend/`) para partir del estado inicial.

## 0. Ingreso y roles (1 min)

1. Abrir `http://localhost:8000`. Mostrar las tres cuentas de demostración.
2. Ingresar como **Jefe de Proyecto** (`kevin.henriquez@trazo.cl` / `Trazo2026!`).
3. En **Usuarios y roles**, mostrar la matriz de permisos de Administrador, Jefe de
   Proyecto e Integrante.

## 1. Planificación importada (2 min)

1. **Proyectos**: Horizonte Conecta, avance 29,6 % vs 31,9 % planificado, SPI 0,93,
   término proyectado 19‑07‑2027 frente al compromiso 04‑08‑2027.
2. **Importar Carta Gantt**: arrastrar `insumos/Caso3_Horizonte_Planificacion_Gantt.xlsx`.
   Mostrar que se reconoce el libro del curso, las hojas convertidas, los conteos
   (10/25/42/10) y la advertencia de sobreasignación de BE1. No confirmar.
3. **Carta Gantt**: jerarquía plegable («Solo etapas» / «Expandir todo»), barras plan
   vs línea base, desplazamiento proyectado, hitos, fecha de corte, compromiso y
   flechas FS/SS/FF/SF. Activar «Solo ruta crítica».
4. **Caso de prueba**: checklist 12/12.

## 2. Escenario 1 · Cambiar una duración (2 min)

1. **Actividades y precedencias** → buscar **A17** (integración con compras, crítica).
2. Duración **22 → 27** → «Guardar y recalcular».
3. El modal muestra el antes/después: A17 termina el 16‑02‑2027, se mueven sus
   sucesoras y resúmenes, y el término planificado del proyecto pasa de
   12‑07‑2027 a **20‑07‑2027**.
4. Ver el efecto en **Carta Gantt**, en la reserva de plazo y en el **Tablero del proyecto**.

## 3. Escenario 2 · Modificar recursos (2 min)

1. **Recursos y costos** → «Por tarea» → fila **A18** → clic en la asignación **IN1**.
2. Horas por día **8 → 16** y marcar «Duración guiada por esfuerzo». El modal estima
   la nueva duración (17 → 9 días).
3. Guardar: A18 se acorta, el término proyectado mejora y aparece la alerta de
   **sobreasignación del Desarrollador de Integraciones (200 %)**.
4. Mostrar la pestaña «Carga semanal» (celdas rojas con detalle de tareas) y
   «Costos y calendario».

## 4. Escenario 3 · Aprobar una solicitud de cambio (3 min)

1. **Solicitudes de cambio** → **SC‑04** «Tablero ejecutivo exportable a PDF».
   Está en la etapa 5 (Revisión del comité) con propuesta: A26 de 16 a 20 días y
   +32 h de BI1; impacto simulado +4 días hábiles y +$736.000, 3 evidencias.
2. «Avanzar a «Decisión»» → escribir el acuerdo → **Aprobar**.
3. **Aplicar cambio al plan y generar nueva línea base**: se congela la línea base
   siguiente (v3), se recalculan Gantt, costos y 20 KPI.
4. Avanzar Verificación y Cierre → la solicitud queda **Cerrada** con su trazabilidad.
5. **Tablero del cambio**: embudo, tiempos vs SLA, matriz impacto × probabilidad,
   C01–C12 y consumo de contingencia.

## 5. Control (1–2 min)

1. **Administrador de KPI**: abrir P01 (SPI) — fórmula `EV / PV`, valores sustituidos,
   variables y tendencia. Cambiar el umbral amarillo y «Probar fórmula».
2. **Hitos**: abrir H05, mostrar tareas y criterios de aceptación; adjuntar una
   evidencia y marcar un criterio como cumplido.
3. Cerrar sesión e ingresar como **Integrante** (`diego.lopez@trazo.cl`): solo ve
   «Mis tareas», puede registrar avance de A19 y crear solicitudes, pero no editar
   duraciones ni aprobar cambios.
