"""Demo data loader: users per role, both seed projects and change history.

Usage (inside backend/):
    python -m app.demo            # load if the database has no projects
    python -m app.demo --reset    # delete every project and load again

All demo users share the password ``Trazo2026!``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db import SessionLocal
from app.models import (
    AcceptanceCriterion,
    ChangePriority,
    ChangeRequest,
    ChangeRequestStage,
    ChangeStageStatus,
    ChangeTransition,
    ChangeType,
    CriterionStatus,
    Evidence,
    GanttElement,
    KpiValue,
    ManualMetric,
    Milestone,
    Project,
    Resource,
    Role,
    User,
)
from app.services.change_flow import ChangeFlow, ensure_stages
from app.services.kpi_engine import recalculate_kpis
from app.services.persistence import import_workbook

ROOT = Path(__file__).resolve().parents[2]
SEEDS = Path(__import__("os").environ.get("SEEDS_DIR", ROOT / "seeds"))
PASSWORD = "Trazo2026!"

USERS = (
    ("admin@trazo.cl", "Administración Trazo", "ADMINISTRADOR"),
    ("kevin.henriquez@trazo.cl", "Kevin Henríquez", "JEFE_DE_PROYECTO"),
    ("diego.lopez@trazo.cl", "Diego López", "INTEGRANTE"),
    ("christian.perez@trazo.cl", "Christian Pérez", "INTEGRANTE"),
)


def _at(day: str, hour: int = 10, minute: int = 0) -> datetime:
    """Chile (UTC-3) wall time expressed in UTC."""

    return datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=UTC) + timedelta(hours=3)


def ensure_users(session: Session) -> dict[str, User]:
    roles = {role.name: role for role in session.scalars(sa.select(Role)).all()}
    users: dict[str, User] = {}
    for email, name, role in USERS:
        user = session.scalar(sa.select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name, password_hash=hash_password(PASSWORD), roles=[roles[role]])
            session.add(user)
        users[email] = user
    session.flush()
    return users


def _import(session: Session, path: Path) -> Project:
    result = import_workbook(session, path)
    if not result.report.valid:
        raise RuntimeError(f"Seed inválido {path.name}: {result.report.as_dict()['errors'][:3]}")
    project = session.scalar(sa.select(Project).where(Project.code == result.preview.project_code))
    if project is None:
        raise RuntimeError(f"No se creó el proyecto de {path.name}")
    return project


def _link_resources(session: Session, project: Project, users: dict[str, User], mapping: dict[str, str]) -> None:
    for external_id, email in mapping.items():
        resource = session.scalar(sa.select(Resource).where(Resource.project_id == project.id, Resource.external_id == external_id))
        if resource is not None:
            resource.user_id = users[email].id


def _verify_done_milestones(session: Session, project: Project, verifier: User) -> None:
    for element in session.scalars(
        sa.select(GanttElement).where(GanttElement.project_id == project.id, GanttElement.element_type == "HITO")
    ).all():
        if element.progress_pct < 100:
            continue
        verified_at = datetime.combine(element.actual_finish or element.planned_finish or date.today(), datetime.min.time(), tzinfo=UTC) + timedelta(hours=20)
        for index, criterion in enumerate(
            session.scalars(sa.select(AcceptanceCriterion).where(AcceptanceCriterion.milestone_id == element.id).order_by(AcceptanceCriterion.external_id)).all()
        ):
            criterion.status = CriterionStatus.MET
            criterion.verified_by = verifier.id
            criterion.verified_at = verified_at
            if index == 0:
                session.add(
                    Evidence(
                        criterion_id=criterion.id,
                        file_name=f"Acta_{element.external_id}_{element.name[:28].replace(' ', '_')}.pdf",
                        storage_key=f"seed-{criterion.external_id}.pdf",
                        content_type="application/pdf",
                        size_bytes=184_320,
                        uploaded_by=verifier.id,
                        uploaded_at=verified_at,
                    )
                )
        milestone = session.get(Milestone, element.id)
        if milestone is not None:
            milestone.acceptance_status = CriterionStatus.MET


def _new_request(
    session: Session,
    project: Project,
    code: str,
    title: str,
    description: str,
    justification: str,
    change_type: ChangeType,
    priority: ChangePriority,
    area: str,
    requester: User,
    responsible: User,
    created: datetime,
) -> ChangeRequest:
    stages = ensure_stages(session, project.id)
    request = ChangeRequest(
        project_id=project.id,
        code=code,
        title=title,
        description=description,
        justification=justification,
        change_type=change_type,
        priority=priority,
        requester_area=area,
        requester_id=requester.id,
        responsible_id=responsible.id,
        current_stage_id=stages[0].id,
        proposal=[],
        created_at=created,
        updated_at=created,
    )
    session.add(request)
    session.flush()
    session.add_all(
        [
            ChangeRequestStage(
                request_id=request.id,
                stage_id=stage.id,
                status=ChangeStageStatus.ACTIVE if index == 0 else ChangeStageStatus.PENDING,
                entered_at=created if index == 0 else None,
            )
            for index, stage in enumerate(stages)
        ]
    )
    session.add(
        ChangeTransition(request_id=request.id, to_stage_id=stages[0].id, to_status=request.status, performed_by=requester.id, comment="Solicitud registrada", occurred_at=created)
    )
    session.flush()
    return request


def _advance(flow: ChangeFlow, steps: list[tuple[datetime, str]]) -> None:
    for moment, comment in steps:
        flow.advance(comment, now=moment)


def _evidence(session: Session, request: ChangeRequest, name: str, user: User, when: datetime, size: int = 95_000) -> None:
    session.add(
        Evidence(
            change_request_id=request.id,
            file_name=name,
            storage_key=f"seed-{request.code}-{name}",
            content_type="application/pdf" if name.endswith(".pdf") else "application/octet-stream",
            size_bytes=size,
            uploaded_by=user.id,
            uploaded_at=when,
        )
    )


def horizonte_changes(session: Session, project: Project, users: dict[str, User]) -> None:
    kevin = users["kevin.henriquez@trazo.cl"]
    diego = users["diego.lopez@trazo.cl"]
    christian = users["christian.perez@trazo.cl"]

    # SC-01 · rejected scope request (Prevención de Riesgos), decided at the H02 committee.
    sc01 = _new_request(
        session, project, "SC-01", "Incorporar módulo de Prevención de Riesgos",
        "Agregar a la plataforma el registro de charlas, inspecciones y no conformidades de Prevención de Riesgos.",
        "Prevención de Riesgos pidió participar del piloto para no duplicar registros en obra.",
        ChangeType.SCOPE, ChangePriority.MEDIUM, "Prevención de Riesgos", kevin, kevin, _at("2026-11-02", 9),
    )
    flow = ChangeFlow(session, sc01, kevin.id)
    _evidence(session, sc01, "Carta_Prevencion_Riesgos.pdf", kevin, _at("2026-11-02", 9, 30))
    _advance(flow, [(_at("2026-11-02", 16), "Solicitud completa"), (_at("2026-11-03", 11), "Clasificada: alcance, prioridad media")])
    flow.save_proposal([
        {"task_id": "A07", "duration_days": 26, "resources": [{"resource": "AF1", "hours": 120}], "note": "Historias del nuevo módulo"},
        {"task_id": "A19", "duration_days": 37, "resources": [{"resource": "BE1", "hours": 80}], "note": "Desarrollo del módulo"},
    ])
    flow.simulate(now=_at("2026-11-05", 17))
    _advance(flow, [(_at("2026-11-06", 10), "Impacto evaluado: +15 días hábiles")])
    flow.decide(False, "Comité H02: queda fuera del piloto; se evaluará como fase 2", now=_at("2026-11-11", 12))

    # SC-02 · approved, applied and closed (extra vendor support for A17).
    sc02 = _new_request(
        session, project, "SC-02", "Soporte adicional del proveedor de compras para A17",
        "Contratar 40 horas extra de soporte del proveedor del sistema de compras para destrabar la integración de la API.",
        "La API devuelve respuestas inconsistentes (riesgo R-01); sin soporte A17 se atrasa más.",
        ChangeType.RESOURCE, ChangePriority.HIGH, "Equipo de integraciones", diego, kevin, _at("2027-01-11", 9),
    )
    flow = ChangeFlow(session, sc02, kevin.id)
    _evidence(session, sc02, "Cotizacion_soporte_proveedor.pdf", diego, _at("2027-01-11", 9, 20))
    _evidence(session, sc02, "Registro_errores_API.xlsx", diego, _at("2027-01-11", 9, 25), 41_000)
    _advance(flow, [
        (_at("2027-01-11", 12), "Revisión inicial OK"),
        (_at("2027-01-11", 15), "Prioridad alta: afecta la ruta crítica"),
    ])
    flow.save_proposal([{"task_id": "A17", "resources": [{"resource": "NL-06", "quantity": 40}], "note": "40 h de soporte del proveedor"}])
    flow.simulate(now=_at("2027-01-12", 10))
    _advance(flow, [
        (_at("2027-01-12", 11), "Impacto: +$1.400.000, sin efecto en plazo"),
        (_at("2027-01-12", 16), "Revisado en comité extraordinario"),
        (_at("2027-01-12", 18), "Comité recomienda aprobar"),
    ])
    flow.decide(True, "Aprobado con cargo a contingencia", now=_at("2027-01-13", 9))
    _advance(flow, [(_at("2027-01-13", 12), "Orden de compra emitida")])
    flow.apply(now=_at("2027-01-13", 17))
    _advance(flow, [(_at("2027-01-14", 12), "Proveedor asignado, horas disponibles"), (_at("2027-01-14", 18), "Cierre y comunicación al equipo")])

    # SC-03 · cost change waiting for impact analysis, no evidence yet.
    sc03 = _new_request(
        session, project, "SC-03", "Agregar 2 tablets para la obra industrial",
        "Comprar dos tablets rugerizadas adicionales para la obra industrial de Rancagua.",
        "La obra tiene dos frentes de trabajo simultáneos y un solo equipo comparte las tablets.",
        ChangeType.COST, ChangePriority.LOW, "Jefe de obra Rancagua", christian, kevin, _at("2027-01-11", 11),
    )
    flow = ChangeFlow(session, sc03, kevin.id)
    _advance(flow, [
        (_at("2027-01-12", 9), "Revisión inicial OK"),
        (_at("2027-01-13", 10), "Clasificada: costo, prioridad baja"),
        (_at("2027-01-13", 12), "Pasa a análisis de impacto"),
    ])
    flow.save_proposal([{"task_id": "A34", "resources": [{"resource": "NL-04", "quantity": 2}], "note": "2 tablets adicionales"}])

    # SC-04 · in committee; the live demo approves and applies it (scenario 3).
    sc04 = _new_request(
        session, project, "SC-04", "Tablero ejecutivo exportable a PDF para el Directorio",
        "Agregar al tablero ejecutivo (A26) la exportación del informe mensual en PDF con las 6 preguntas de la gerencia.",
        "El informe al Directorio hoy demora 8 días; la exportación directa elimina el armado manual.",
        ChangeType.SCOPE, ChangePriority.MEDIUM, "Gerencia de Operaciones", kevin, kevin, _at("2027-01-08", 9, 12),
    )
    flow = ChangeFlow(session, sc04, kevin.id)
    _evidence(session, sc04, "Correo_Gerencia_Operaciones.pdf", kevin, _at("2027-01-08", 9, 15))
    _evidence(session, sc04, "Estimacion_A26_exportacion.xlsx", kevin, _at("2027-01-11", 16), 38_000)
    _evidence(session, sc04, "Minuta_comite_14-01.docx", kevin, _at("2027-01-14", 11, 30), 52_000)
    _advance(flow, [(_at("2027-01-08", 15, 40), "Revisión inicial completa"), (_at("2027-01-11", 10, 5), "Clasificada: alcance, prioridad media")])
    flow.save_proposal([{"task_id": "A26", "duration_days": 20, "resources": [{"resource": "BI1", "hours": 32}], "note": "Exportación PDF del informe"}])
    flow.simulate(now=_at("2027-01-12", 17, 20))
    _advance(flow, [
        (_at("2027-01-12", 17, 30), "Pasa a análisis de impacto"),
        (_at("2027-01-14", 11), "Impacto evaluado; enviado a comité directivo"),
    ])

    # SC-05 · registered, stuck in initial review (SLA breach alert).
    sc05 = _new_request(
        session, project, "SC-05", "Notificaciones push de observaciones abiertas",
        "Enviar una notificación al responsable cuando una observación técnica lleve más de 48 h abierta.",
        "Las observaciones se olvidan y vuelven a aparecer en las visitas de inspección.",
        ChangeType.SCOPE, ChangePriority.MEDIUM, "Oficina técnica", christian, kevin, _at("2027-01-05", 10),
    )
    flow = ChangeFlow(session, sc05, kevin.id)
    _evidence(session, sc05, "Ejemplos_observaciones_vencidas.pdf", christian, _at("2027-01-05", 10, 10))
    _advance(flow, [(_at("2027-01-06", 9), "Registro completo")])


def seed_b_changes(session: Session, project: Project, users: dict[str, User]) -> None:
    kevin = users["kevin.henriquez@trazo.cl"]
    proposals = {
        "CB-02": [{"task_id": "A13", "duration_days": 9, "note": "3 días más de pruebas"}],
        "CB-03": [{"task_id": "A18", "resources": [{"resource": "R-EQ1", "quantity": 2}]}],
        "CB-04": [{"task_id": "A15", "resources": [{"resource": "P5", "hours": 16}]}],
    }
    for request in session.scalars(sa.select(ChangeRequest).where(ChangeRequest.project_id == project.id)).all():
        request.responsible_id = kevin.id
        request.requester_id = kevin.id
        request.description = request.description or request.title
        if request.code in proposals:
            request.proposal = proposals[request.code]
    session.flush()
    for request in session.scalars(sa.select(ChangeRequest).where(ChangeRequest.project_id == project.id, ChangeRequest.code.in_(["CB-02", "CB-03"]))).all():
        ChangeFlow(session, request, kevin.id).simulate()
    for request in session.scalars(sa.select(ChangeRequest).where(ChangeRequest.project_id == project.id, ChangeRequest.code.in_(["CB-01", "CB-03", "CB-04"]))).all():
        _evidence(session, request, f"Respaldo_{request.code}.pdf", kevin, request.created_at)


def kpi_history(session: Session, project: Project, start: date, cutoff: date) -> None:
    from app.services.analytics import ProjectAnalytics

    analytics = ProjectAnalytics(session, project)
    point = start
    while point < cutoff:
        recalculate_kpis(session, project, at=point, analytics=analytics)
        point += timedelta(days=7)
    recalculate_kpis(session, project, at=cutoff, analytics=analytics)


def _manual(session: Session, project: Project, code: str, value: str, user: User) -> None:
    session.add(ManualMetric(project_id=project.id, code=code, value=Decimal(value), updated_by=user.id))


def load(session: Session) -> dict[str, Project]:
    users = ensure_users(session)
    horizonte_source = ROOT / "insumos" / "Caso3_Horizonte_Planificacion_Gantt.xlsx"
    if not horizonte_source.exists():
        horizonte_source = SEEDS / "Horizonte_Conecta_Carta_Gantt.xlsx"
    horizonte = _import(session, horizonte_source)
    horizonte.responsible_id = users["kevin.henriquez@trazo.cl"].id
    _link_resources(session, horizonte, users, {"JP1": "kevin.henriquez@trazo.cl", "BE1": "diego.lopez@trazo.cl", "FE1": "christian.perez@trazo.cl"})
    _verify_done_milestones(session, horizonte, users["kevin.henriquez@trazo.cl"])
    _manual(session, horizonte, "CHANGE_TRAINING_COVERAGE", "12", users["kevin.henriquez@trazo.cl"])
    _manual(session, horizonte, "CHANGE_ADOPTION_INDEX", "0", users["kevin.henriquez@trazo.cl"])
    session.flush()
    horizonte_changes(session, horizonte, users)
    session.flush()
    kpi_history(session, horizonte, date(2026, 10, 30), horizonte.cutoff_date or date(2027, 1, 15))

    seed_b = _import(session, SEEDS / "Seed_B_Caso_Prueba_Minimo.xlsx")
    seed_b.responsible_id = users["kevin.henriquez@trazo.cl"].id
    _link_resources(session, seed_b, users, {"P1": "kevin.henriquez@trazo.cl", "P3": "diego.lopez@trazo.cl", "P4": "christian.perez@trazo.cl"})
    _verify_done_milestones(session, seed_b, users["kevin.henriquez@trazo.cl"])
    _manual(session, seed_b, "CHANGE_TRAINING_COVERAGE", "0", users["kevin.henriquez@trazo.cl"])
    _manual(session, seed_b, "CHANGE_ADOPTION_INDEX", "0", users["kevin.henriquez@trazo.cl"])
    session.flush()
    seed_b_changes(session, seed_b, users)
    session.flush()
    kpi_history(session, seed_b, date(2026, 9, 18), seed_b.cutoff_date or date(2026, 10, 30))
    return {"horizonte": horizonte, "seed_b": seed_b}


def reset(session: Session) -> None:
    from app.api.views import _purge_project

    session.execute(sa.text("ALTER TABLE baseline_elements DISABLE TRIGGER trg_baseline_elements_immutable"))
    for project in session.scalars(sa.select(Project)).all():
        _purge_project(session, project)
    session.flush()
    session.execute(sa.text("ALTER TABLE baseline_elements ENABLE TRIGGER trg_baseline_elements_immutable"))
    session.execute(sa.delete(KpiValue))


def seed_if_empty() -> bool:
    with SessionLocal() as session:
        if session.scalar(sa.select(sa.func.count(Project.id))):
            ensure_users(session)
            session.commit()
            return False
        load(session)
        session.commit()
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga los datos de demostración de Trazo")
    parser.add_argument("--reset", action="store_true", help="Elimina todos los proyectos y vuelve a cargar")
    args = parser.parse_args(argv)
    with SessionLocal() as session:
        if args.reset:
            reset(session)
            session.commit()
        if session.scalar(sa.select(sa.func.count(Project.id))):
            ensure_users(session)
            session.commit()
            print("La base ya tiene proyectos; use --reset para recargar la demo.")
            return 0
        projects = load(session)
        session.commit()
        print("Demo cargada:", ", ".join(project.name for project in projects.values()))
        print("Usuarios (contraseña Trazo2026!):")
        for email, name, role in USERS:
            print(f"  {email:<28} {role:<17} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
