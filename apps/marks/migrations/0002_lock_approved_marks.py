from django.db import migrations

# After approval the marks are locked in the service layer; this trigger is the second line:
# no cell of an approved or locked assessment can be inserted, changed or removed (v0.8.0 A2).
LOCK = """
    CREATE FUNCTION marks_protect_locked_cell() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE row_id uuid; state text;
    BEGIN
        IF TG_OP = 'DELETE' THEN row_id := OLD.row_id; ELSE row_id := NEW.row_id; END IF;
        SELECT a.status INTO state
          FROM marks_marksheetrow r JOIN assessments_assessment a ON a.id = r.assessment_id
         WHERE r.id = row_id;
        IF state IN ('approved', 'locked') THEN
            RAISE EXCEPTION 'these marks are locked: reopen the result first';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END
    $$;
    CREATE TRIGGER marks_cell_locked BEFORE INSERT OR UPDATE OR DELETE
        ON marks_markcell FOR EACH ROW EXECUTE FUNCTION marks_protect_locked_cell();
"""
LOCK_REVERSE = """
    DROP TRIGGER marks_cell_locked ON marks_markcell;
    DROP FUNCTION marks_protect_locked_cell();
"""


class Migration(migrations.Migration):
    dependencies = [("marks", "0001_initial")]

    operations = [migrations.RunSQL(LOCK, LOCK_REVERSE)]
