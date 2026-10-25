"""Create the F1 planning, KPI, baseline and change-control schema.

This first migration intentionally uses the declarative metadata as the
single source of truth.  Subsequent migrations must be explicit and must not
call ``create_all``.  The database trigger protects approved baseline data;
changing the current/superseded status is the only allowed lifecycle update.
"""

from alembic import op

from app.models import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_baseline_plan_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_TABLE_NAME = 'baseline_elements' THEN
                IF TG_OP = 'INSERT' THEN
                    IF EXISTS (
                        SELECT 1
                        FROM baselines
                        WHERE id = NEW.baseline_id AND approved_at IS NOT NULL
                    ) THEN
                        RAISE EXCEPTION 'approved baseline_elements are immutable';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'UPDATE'
                   AND OLD.element_id IS NOT NULL
                   AND NEW.element_id IS NULL
                   AND NEW.baseline_id = OLD.baseline_id
                   AND NEW.external_id = OLD.external_id THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'baseline_elements are immutable';
            END IF;
            IF NEW.project_id IS DISTINCT FROM OLD.project_id
               OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.created_by IS DISTINCT FROM OLD.created_by
               OR (
                   OLD.approved_at IS NOT NULL
                   AND NEW.approved_at IS DISTINCT FROM OLD.approved_at
               ) THEN
                RAISE EXCEPTION 'baseline plan data is immutable';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_baselines_immutable_plan
        BEFORE UPDATE ON baselines
        FOR EACH ROW EXECUTE FUNCTION prevent_baseline_plan_mutation();
        CREATE TRIGGER trg_baseline_elements_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON baseline_elements
        FOR EACH ROW EXECUTE FUNCTION prevent_baseline_plan_mutation();
        """
    )


def downgrade() -> None:
    """Drop the initial schema when explicitly downgrading a development DB."""

    op.execute("DROP TRIGGER IF EXISTS trg_baseline_elements_immutable ON baseline_elements")
    op.execute("DROP TRIGGER IF EXISTS trg_baselines_immutable_plan ON baselines")
    op.execute("DROP FUNCTION IF EXISTS prevent_baseline_plan_mutation()")
    Base.metadata.drop_all(bind=op.get_bind())
