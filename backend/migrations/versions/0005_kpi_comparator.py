"""KPI explicit comparator and range thresholds.

Revision ID: 0005_kpi_comparator
Revises: 0004_ui_support
"""

from __future__ import annotations

from alembic import op

revision = "0005_kpi_comparator"
down_revision = "0004_ui_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE kpis ADD COLUMN IF NOT EXISTS comparator VARCHAR(10) NOT NULL DEFAULT 'GE'")
    for column in ("green_min", "green_max", "yellow_min", "yellow_max"):
        op.execute(f"ALTER TABLE kpis ADD COLUMN IF NOT EXISTS {column} NUMERIC(18, 6)")
    # Back-fill the comparator from the legacy green/yellow ordering so existing
    # KPIs keep the exact same traffic-light behaviour.
    op.execute(
        """
        UPDATE kpis SET comparator = CASE
            WHEN green_threshold IS NULL OR yellow_threshold IS NULL THEN 'INFO'
            WHEN green_threshold >= yellow_threshold THEN 'GE'
            ELSE 'LE'
        END
        """
    )


def downgrade() -> None:
    for column in ("comparator", "green_min", "green_max", "yellow_min", "yellow_max"):
        op.execute(f"ALTER TABLE kpis DROP COLUMN IF EXISTS {column}")
