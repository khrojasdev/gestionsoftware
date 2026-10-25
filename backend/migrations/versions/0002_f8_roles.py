"""Seed the stable F8 role vocabulary."""

from uuid import UUID

from alembic import op
import sqlalchemy as sa

revision = "0002_f8_roles"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_ROLES = (
    (UUID("00000000-0000-0000-0000-000000000001"), "ADMINISTRADOR", "Acceso completo"),
    (UUID("00000000-0000-0000-0000-000000000002"), "JEFE_DE_PROYECTO", "Gestiona proyectos y cambios"),
    (UUID("00000000-0000-0000-0000-000000000003"), "INTEGRANTE", "Actualiza sus avances y consulta"),
)


def upgrade() -> None:
    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    op.bulk_insert(
        roles,
        [{"id": identifier, "name": name, "description": description} for identifier, name, description in _ROLES],
    )


def downgrade() -> None:
    names = [name for _, name, _ in _ROLES]
    op.execute(sa.text("DELETE FROM roles WHERE name IN :names").bindparams(sa.bindparam("names", expanding=True)).params(names=names))
