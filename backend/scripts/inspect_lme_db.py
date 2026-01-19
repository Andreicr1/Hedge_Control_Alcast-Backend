from __future__ import annotations

import sqlite3
from pathlib import Path


def inspect_sqlite(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('alembic_version','lme_prices')"
        )
        tables = [r[0] for r in cur.fetchall()]
        print(f"{db_path.name}: tables={tables}")

        if 'alembic_version' in tables:
            cur.execute('SELECT version_num FROM alembic_version')
            row = cur.fetchone()
            print(f"{db_path.name}: alembic_version={row[0] if row else None}")

        if 'lme_prices' in tables:
            cur.execute('SELECT COUNT(*) FROM lme_prices')
            cnt = cur.fetchone()[0]
            print(f"{db_path.name}: lme_prices count={cnt}")

            cur.execute(
                'SELECT symbol, price_type, COUNT(*) c, MAX(ts_price) FROM lme_prices '
                'GROUP BY symbol, price_type ORDER BY symbol, price_type'
            )
            rows = cur.fetchall()
            print(f"{db_path.name}: groups={len(rows)}")
            for r in rows[:50]:
                print(' ', r)
    finally:
        con.close()


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    dbs = [here / 'dev.db', here / 'dev-local.db', here / 'dev-smoke.db']

    found = False
    for db in dbs:
        if db.exists():
            found = True
            inspect_sqlite(db)

    if not found:
        print('No local dev DB files found.')


if __name__ == '__main__':
    main()
