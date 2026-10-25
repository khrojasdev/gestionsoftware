"""Enforce project ownership on cross-aggregate planning references.

The first migration uses the declarative metadata for a clean database.  This
migration is deliberately idempotent as well, so databases created by the
earlier F1 schema can be upgraded without losing their planning data.
"""

from alembic import op


revision = "0003_f14_domain_integrity"
down_revision = "0002_f8_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_baseline_plan_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME = 'baseline_elements' THEN
                IF TG_OP = 'INSERT' THEN
                    IF EXISTS (SELECT 1 FROM baselines WHERE id = NEW.baseline_id AND approved_at IS NOT NULL) THEN
                        RAISE EXCEPTION 'approved baseline_elements are immutable';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.element_id IS NOT NULL AND NEW.element_id IS NULL
                   AND NEW.baseline_id = OLD.baseline_id AND NEW.external_id = OLD.external_id THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'baseline_elements are immutable';
            END IF;
            IF NEW.project_id IS DISTINCT FROM OLD.project_id
               OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.created_by IS DISTINCT FROM OLD.created_by
               OR (OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at) THEN
                RAISE EXCEPTION 'baseline plan data is immutable';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    # Existing installations need the ownership columns before the composite
    # foreign keys can be installed.  Fresh installations already have them
    # because 0001 creates the current metadata.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboards (
            id uuid PRIMARY KEY,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            external_id varchar(80) NOT NULL,
            name varchar(200) NOT NULL,
            dashboard_type varchar(40) NOT NULL,
            kpi_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_dashboards_project_external UNIQUE (project_id, external_id)
        );
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='dependencies' AND column_name='project_id') THEN
                ALTER TABLE dependencies ADD COLUMN project_id uuid;
                UPDATE dependencies d SET project_id = g.project_id FROM gantt_elements g WHERE g.id = d.successor_id;
                ALTER TABLE dependencies ALTER COLUMN project_id SET NOT NULL;
                ALTER TABLE dependencies ADD CONSTRAINT fk_dependencies_project_id_projects FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='assignments' AND column_name='project_id') THEN
                ALTER TABLE assignments ADD COLUMN project_id uuid;
                UPDATE assignments a SET project_id = g.project_id FROM gantt_elements g WHERE g.id = a.element_id;
                ALTER TABLE assignments ALTER COLUMN project_id SET NOT NULL;
                ALTER TABLE assignments ADD CONSTRAINT fk_assignments_project_id_projects FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='baseline_elements' AND column_name='project_id') THEN
                ALTER TABLE baseline_elements ADD COLUMN project_id uuid;
                UPDATE baseline_elements b SET project_id = bl.project_id FROM baselines bl WHERE bl.id = b.baseline_id;
                ALTER TABLE baseline_elements ALTER COLUMN project_id SET NOT NULL;
                ALTER TABLE baseline_elements ADD CONSTRAINT fk_baseline_elements_project_id_projects FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_resources_project_id') THEN
                ALTER TABLE resources ADD CONSTRAINT uq_resources_project_id UNIQUE (project_id, id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_gantt_elements_project_id') THEN
                ALTER TABLE gantt_elements ADD CONSTRAINT uq_gantt_elements_project_id UNIQUE (project_id, id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_gantt_elements_project_parent') THEN
                ALTER TABLE gantt_elements ADD CONSTRAINT fk_gantt_elements_project_parent
                    FOREIGN KEY (project_id, parent_id) REFERENCES gantt_elements(project_id, id) ON DELETE RESTRICT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_calendar_entries_project_resource') THEN
                ALTER TABLE calendar_entries ADD CONSTRAINT fk_calendar_entries_project_resource
                    FOREIGN KEY (project_id, resource_id) REFERENCES resources(project_id, id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_dependencies_project_predecessor') THEN
                ALTER TABLE dependencies ADD CONSTRAINT fk_dependencies_project_predecessor
                    FOREIGN KEY (project_id, predecessor_id) REFERENCES gantt_elements(project_id, id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_dependencies_project_successor') THEN
                ALTER TABLE dependencies ADD CONSTRAINT fk_dependencies_project_successor
                    FOREIGN KEY (project_id, successor_id) REFERENCES gantt_elements(project_id, id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_assignments_project_element') THEN
                ALTER TABLE assignments ADD CONSTRAINT fk_assignments_project_element
                    FOREIGN KEY (project_id, element_id) REFERENCES gantt_elements(project_id, id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_assignments_project_resource') THEN
                ALTER TABLE assignments ADD CONSTRAINT fk_assignments_project_resource
                    FOREIGN KEY (project_id, resource_id) REFERENCES resources(project_id, id) ON DELETE RESTRICT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_kpis_project_element') THEN
                ALTER TABLE kpis ADD CONSTRAINT fk_kpis_project_element
                    FOREIGN KEY (project_id, element_id) REFERENCES gantt_elements(project_id, id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_baseline_elements_project_element') THEN
                ALTER TABLE baseline_elements ADD CONSTRAINT fk_baseline_elements_project_element
                    FOREIGN KEY (project_id, element_id) REFERENCES gantt_elements(project_id, id) ON DELETE RESTRICT;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # The ownership columns are part of the current model; keeping them on a
    # downgrade avoids silently reintroducing cross-project references.
    pass
