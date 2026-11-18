from django.db import migrations, models

# A signed batch run is frozen (design 8.7, v0.9.0 A9). Only the sealing itself is allowed:
# signed false -> true with a content hash, on a kept run. After that no DELETE and no UPDATE,
# except the is_latest flag, which moves on when a newer run is stored.
FREEZE = """
    CREATE FUNCTION results_protect_signed_batch() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.signed THEN
            IF TG_OP = 'DELETE' OR (
                NEW.signed IS DISTINCT FROM OLD.signed
                OR NEW.kept IS DISTINCT FROM OLD.kept
                OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
                OR NEW.input_hash IS DISTINCT FROM OLD.input_hash
                OR NEW.engine_version IS DISTINCT FROM OLD.engine_version
                OR NEW.status IS DISTINCT FROM OLD.status
                OR NEW.include_unsigned IS DISTINCT FROM OLD.include_unsigned
                OR NEW.outputs IS DISTINCT FROM OLD.outputs
                OR NEW.trace IS DISTINCT FROM OLD.trace
                OR NEW.courses IS DISTINCT FROM OLD.courses
                OR NEW.excluded IS DISTINCT FROM OLD.excluded
                OR NEW.checklist IS DISTINCT FROM OLD.checklist
                OR NEW.at IS DISTINCT FROM OLD.at
                OR NEW.batch_id IS DISTINCT FROM OLD.batch_id
                OR NEW.method_version_id IS DISTINCT FROM OLD.method_version_id
            ) THEN
                RAISE EXCEPTION 'a signed batch run is frozen';
            END IF;
            RETURN NEW;
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        IF NEW.signed AND (NEW.content_hash = '' OR NOT NEW.kept) THEN
            RAISE EXCEPTION 'only a kept batch run with a content hash can be signed';
        END IF;
        RETURN NEW;
    END
    $$;
    CREATE TRIGGER results_batch_frozen BEFORE UPDATE OR DELETE
        ON results_batchrun FOR EACH ROW EXECUTE FUNCTION results_protect_signed_batch();
"""
FREEZE_REVERSE = """
    DROP TRIGGER results_batch_frozen ON results_batchrun;
    DROP FUNCTION results_protect_signed_batch();
"""


class Migration(migrations.Migration):
    dependencies = [("results", "0003_batch_runs")]

    operations = [
        migrations.AddField(
            model_name="batchrun",
            name="signed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="batchrun",
            name="content_hash",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.RunSQL(FREEZE, FREEZE_REVERSE),
    ]
