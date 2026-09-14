"""Append-only audit table, enforced below the application.
A trigger rather than REVOKE so it holds with a single database role."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION claims_claimevent_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'claims_claimevent is append-only (% refused)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER claims_claimevent_immutable
    BEFORE UPDATE OR DELETE ON claims_claimevent
    FOR EACH ROW EXECUTE FUNCTION claims_claimevent_immutable();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS claims_claimevent_immutable ON claims_claimevent;
DROP FUNCTION IF EXISTS claims_claimevent_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [("claims", "0002_claim_claimevent")]
    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
