"""scheduler_sync jadvalini kafolatlaydi.

Bot ham (CREATE_SQL) bu jadvalni IF NOT EXISTS bilan yaratadi; lekin adminka
botdan oldin ishga tushsa, Mini App yozishga uringanda jadval bo'lmasligi mumkin.
Shu migratsiya uni oldindan yaratib qo'yadi (ikkala tomon ham idempotent)."""
from django.db import migrations

_SQL = """
CREATE TABLE IF NOT EXISTS scheduler_sync (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    ref_id INTEGER NOT NULL,
    processed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sched_sync_pending ON scheduler_sync (processed);
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.RunSQL(sql=_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
