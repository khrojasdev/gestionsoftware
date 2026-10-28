"""Columns and tables required by the full web application.

Idempotent on purpose: 0001 builds the schema from the current metadata, so
fresh databases already contain these objects; older databases get them here.
"""

from alembic import op

revision = "0004_ui_support"
down_revision = "0003_f14_domain_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE resources ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL;
        ALTER TABLE kpis ADD COLUMN IF NOT EXISTS category varchar(20) NOT NULL DEFAULT 'PROYECTO';
        ALTER TABLE kpis ADD COLUMN IF NOT EXISTS is_additional boolean NOT NULL DEFAULT false;
        ALTER TABLE kpis ADD COLUMN IF NOT EXISTS unit varchar(20);
        ALTER TABLE kpis ADD COLUMN IF NOT EXISTS description varchar(500);
        ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS justification varchar(4000);
        ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS requester_area varchar(160);
        ALTER TABLE acceptance_criteria ADD COLUMN IF NOT EXISTS responsible_label varchar(200);
        ALTER TABLE acceptance_criteria ADD COLUMN IF NOT EXISTS notes varchar(1000);
        ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS proposal jsonb NOT NULL DEFAULT '[]'::jsonb;
        CREATE TABLE IF NOT EXISTS manual_metrics (
            id uuid PRIMARY KEY,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            code varchar(80) NOT NULL,
            value numeric(18, 4) NOT NULL DEFAULT 0,
            updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_manual_metrics_project_code UNIQUE (project_id, code)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS manual_metrics")
