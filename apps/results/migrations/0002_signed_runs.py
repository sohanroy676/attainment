from django.db import migrations, models

# A signed run, and its values, are frozen (design 8.7, v0.8.0 A4). Only the sealing itself is
# allowed: signed false -> true with a content hash. After that no DELETE and no UPDATE, except
# the is_latest flag, which moves on when a newer run is stored.
FREEZE = """
    CREATE FUNCTION results_protect_signed_run() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.signed THEN
            IF TG_OP = 'DELETE' OR (
                NEW.signed IS DISTINCT FROM OLD.signed
                OR NEW.kept IS DISTINCT FROM OLD.kept
                OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
                OR NEW.input_hash IS DISTINCT FROM OLD.input_hash
                OR NEW.engine_version IS DISTINCT FROM OLD.engine_version
                OR NEW.status IS DISTINCT FROM OLD.status
                OR NEW.outputs IS DISTINCT FROM OLD.outputs
                OR NEW.trace IS DISTINCT FROM OLD.trace
                OR NEW.checklist IS DISTINCT FROM OLD.checklist
                OR NEW.at IS DISTINCT FROM OLD.at
                OR NEW.offering_id IS DISTINCT FROM OLD.offering_id
                OR NEW.programme_id IS DISTINCT FROM OLD.programme_id
                OR NEW.method_version_id IS DISTINCT FROM OLD.method_version_id
            ) THEN
                RAISE EXCEPTION 'a signed run is frozen';
            END IF;
            RETURN NEW;
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        IF NEW.signed AND (NEW.content_hash = '' OR NOT NEW.kept) THEN
            RAISE EXCEPTION 'only a kept run with a content hash can be signed';
        END IF;
        RETURN NEW;
    END
    $$;
    CREATE TRIGGER results_run_frozen BEFORE UPDATE OR DELETE
        ON results_calculationrun FOR EACH ROW EXECUTE FUNCTION results_protect_signed_run();

    CREATE FUNCTION results_protect_signed_value() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE locked boolean;
    BEGIN
        IF TG_OP = 'INSERT' THEN
            SELECT signed INTO locked FROM results_calculationrun WHERE id = NEW.run_id;
        ELSE
            SELECT signed INTO locked FROM results_calculationrun WHERE id = OLD.run_id;
        END IF;
        IF COALESCE(locked, false) THEN
            RAISE EXCEPTION 'the values of a signed run are frozen';
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END
    $$;
    CREATE TRIGGER results_value_frozen BEFORE INSERT OR UPDATE OR DELETE
        ON results_resultvalue FOR EACH ROW EXECUTE FUNCTION results_protect_signed_value();
"""
FREEZE_REVERSE = """
    DROP TRIGGER results_value_frozen ON results_resultvalue;
    DROP FUNCTION results_protect_signed_value();
    DROP TRIGGER results_run_frozen ON results_calculationrun;
    DROP FUNCTION results_protect_signed_run();
"""


class Migration(migrations.Migration):
    dependencies = [("results", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="calculationrun",
            name="signed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="calculationrun",
            name="content_hash",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.RunSQL(FREEZE, FREEZE_REVERSE),
    ]
