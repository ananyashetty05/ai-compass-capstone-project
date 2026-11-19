"""Apply the model-catalogue migration to the configured database and prove PgStore works end to end.

Run from backend/ on a machine that can reach the database:

    python scripts/catalog_db_check.py                # migrate + verify (additive only)
    python scripts/catalog_db_check.py --refresh      # also run ONE real refresh into the catalogue tables

Touches ONLY the new catalog_* tables (CREATE TABLE IF NOT EXISTS). Existing tables are never altered or read.
Never prints DATABASE_URL, passwords or tokens. Safe to re-run.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services.catalog import engine, registry, sources as S  # noqa: E402
from app.services.catalog.store import PgStore  # noqa: E402

MIGRATION = ROOT / "migrations" / "20261121_model_catalog.sql"


def step(ok: bool, msg: str) -> None:
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    if not ok:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="run one real refresh (live OpenRouter + Hugging Face) into the catalogue tables")
    args = ap.parse_args()

    step(bool(settings.DATABASE_URL), "DATABASE_URL is configured (value not shown)")
    import psycopg

    sql = MIGRATION.read_text()
    forbidden = [w for w in ("DROP ", "DELETE ", "TRUNCATE ", "ALTER TABLE") if w in sql.upper()]
    step(not forbidden, "migration is additive only (no DROP / DELETE / TRUNCATE / ALTER)")

    with psycopg.connect(settings.DATABASE_URL, connect_timeout=8, prepare_threshold=None) as conn:
        with conn.transaction():
            conn.execute(sql)
        names = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_name LIKE 'catalog\\_%' ORDER BY 1").fetchall()]
    step(len(names) >= 8, f"catalogue tables present: {', '.join(names)}")

    store = PgStore()
    step(store.version() >= 0, f"PgStore connects; catalogue version = {store.version()}")

    if args.refresh:
        before = store.version()
        srcs = S.default_sources()
        rep = engine.refresh(store, srcs, trigger="manual-db-check", force=True)
        print(f"  refresh: status={rep.status} published={rep.published} version={rep.version} counts={rep.counts}")
        for s in rep.sources:
            print("   source:", s)
        step(rep.status in ("ok", "partial"), "refresh completed")
        loaded = PgStore().load()
        step(loaded.version >= before, f"reload round-trip: version {loaded.version}")
        pub = [m for m in loaded.models.values() if m.publication == "published"]
        sup = [m for m in loaded.models.values() if m.retention == "superseded"]
        step(len(loaded.models) > 0, f"models={len(loaded.models)} published={len(pub)} superseded={len(sup)} offerings={len(loaded.offerings)}")
        # Idempotency is a property of unchanged input. Hugging Face deliberately reads a rotating window of organisations per run, so it is
        # excluded here; the stable sources must produce zero changes when run again.
        stable = {"curated_snapshot", "openrouter", "announcements"}
        rep2 = engine.refresh(store, srcs, trigger="manual-db-check", force=True, only=stable)
        step(not rep2.counts.get("catalog_changed"), f"second refresh of stable sources is a no-op (events={rep2.counts.get('events')})")
        pub_before = len([m for m in PgStore().load().models.values() if m.publication == "published"])
        rep3 = engine.refresh(store, srcs, trigger="manual-db-check", force=True)           # next Hugging Face window
        pub_after = len([m for m in PgStore().load().models.values() if m.publication == "published"])
        print(f"  info: rotating Hugging Face window -> status={rep3.status} published {pub_before} -> {pub_after}")
        step(rep3.status in ("ok", "partial") and pub_after >= pub_before, "rotating window never reduces the published catalogue")
        registry.invalidate()

    print("\nDone. To serve from the database set CATALOG_PERSISTENCE_ENABLED=true in backend/.env and restart.")


if __name__ == "__main__":
    main()
