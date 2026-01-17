from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a SQLite dev database.")
    parser.add_argument(
        "--db",
        default="dev.db",
        help="Path to the sqlite db file (default: dev.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("select name from sqlite_master where type='table' order by name")
        tables = [r[0] for r in cur.fetchall()]

        print(f"DB: {db_path}")
        print(f"Tables ({len(tables)}):")
        for name in tables:
            print(f"- {name}")

        if "alembic_version" in tables:
            cur.execute("select version_num from alembic_version")
            versions = [r[0] for r in cur.fetchall()]
            print(f"alembic_version: {versions}")
        else:
            print("alembic_version: (missing)")

        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
