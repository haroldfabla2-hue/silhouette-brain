#!/usr/bin/env python3
"""
migrate_owner_id.py — One-time migration to enable multi-tenant on existing DB.

Run BEFORE deploying the multi-tenant code changes to:
1. Add owner_id column (if not exists) to memory_nodes + conversations tables
2. Backfill NULL owner_id values to 'default' (system tenant)
3. Create index on (owner_id, timestamp) for performance

Safe to run multiple times (idempotent).

Usage:
    python3 migrate_owner_id.py [--dry-run]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = "/root/silhouette-brain/src/core/data/memory.db"


def get_tables(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def column_exists(conn, table, column):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols


def index_exists(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,))
    return cur.fetchone() is not None


def migrate(db_path, dry_run=False):
    print(f"[MIGRATE] DB: {db_path}")
    print(f"[MIGRATE] Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    
    if not Path(db_path).exists():
        print(f"[ERROR] DB not found: {db_path}")
        sys.exit(1)
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    tables = get_tables(conn)
    print(f"[MIGRATE] Tables found: {tables}")
    
    # Tables that should have owner_id
    TARGET_TABLES = ["memory_nodes", "conversations"]
    
    for table in TARGET_TABLES:
        if table not in tables:
            print(f"[SKIP] Table '{table}' not in DB (skipping)")
            continue
        
        print(f"\n[PROCESSING] Table: {table}")
        
        # 1. Add column if missing
        if not column_exists(conn, table, "owner_id"):
            print(f"  [ADD] Column owner_id")
            if not dry_run:
                # SQLite doesn't support ALTER TABLE ... ADD COLUMN with NOT NULL DEFAULT directly
                # but we can add with DEFAULT 'default' (effectively NOT NULL for new rows)
                cur.execute(f"ALTER TABLE {table} ADD COLUMN owner_id TEXT DEFAULT 'default'")
                conn.commit()
        else:
            print(f"  [OK] Column owner_id already exists")
        
        # 2. Backfill NULL values
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE owner_id IS NULL OR owner_id = ''")
        null_count = cur.fetchone()[0]
        print(f"  [BACKFILL] Rows with NULL/empty owner_id: {null_count}")
        
        if null_count > 0:
            if not dry_run:
                cur.execute(f"UPDATE {table} SET owner_id = 'default' WHERE owner_id IS NULL OR owner_id = ''")
                conn.commit()
                print(f"  [DONE] Updated {null_count} rows to 'default'")
            else:
                print(f"  [DRY-RUN] Would update {null_count} rows")
        
        # 3. Create index if missing
        index_name = f"idx_{table}_owner_ts"
        if not index_exists(conn, index_name):
            print(f"  [INDEX] Creating {index_name}")
            if not dry_run:
                cur.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}(owner_id, timestamp)")
                conn.commit()
                print(f"  [DONE] Index created")
        else:
            print(f"  [OK] Index {index_name} already exists")
    
    # 4. Show distribution after migration
    print(f"\n[REPORT] Final state:")
    for table in TARGET_TABLES:
        if table not in tables:
            continue
        cur.execute(f"SELECT owner_id, COUNT(*) FROM {table} GROUP BY owner_id ORDER BY COUNT(*) DESC")
        print(f"  {table}:")
        for owner, count in cur.fetchall():
            print(f"    {owner!r}: {count} rows")
    
    conn.close()
    
    if dry_run:
        print(f"\n[DRY-RUN] No changes made. Re-run without --dry-run to apply.")
    else:
        print(f"\n[SUCCESS] Migration complete. Brain is now multi-tenant ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Silhouette Brain DB to multi-tenant")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to memory.db")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without changing anything")
    args = parser.parse_args()
    
    migrate(args.db, dry_run=args.dry_run)
