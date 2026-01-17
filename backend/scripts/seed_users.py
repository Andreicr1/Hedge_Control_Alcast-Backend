from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Ensure "app" is importable when running as a script (python scripts/seed_users.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models
from app.database import SessionLocal
from app.services.auth import hash_password


def ensure_role(db: Session, role_name: models.RoleName) -> models.Role:
    role = db.query(models.Role).filter(models.Role.name == role_name).first()
    if role:
        return role
    role = models.Role(name=role_name, description=role_name.value)
    db.add(role)
    db.flush()
    return role


def ensure_user(
    db: Session,
    *,
    email: str,
    name: str,
    role: models.Role,
    password: str,
) -> tuple[models.User, bool]:
    user = db.query(models.User).filter(models.User.email == email).first()
    created = False
    if not user:
        user = models.User(
            email=email,
            name=name,
            hashed_password=hash_password(password),
            role_id=role.id,
            active=True,
        )
        db.add(user)
        created = True
    else:
        # Update to ensure dev logins work even if user existed before.
        user.name = name
        user.role_id = role.id
        user.active = True
        user.hashed_password = hash_password(password)
        db.add(user)
    db.flush()
    return user, created


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed initial users for dev.")
    parser.add_argument("--password", default="123", help="Password for all seeded users (default: 123)")
    parser.add_argument("--domain", default="alcast.local", help="Email domain (default: alcast.local)")
    args = parser.parse_args()

    pwd = str(args.password)
    domain = str(args.domain).strip().lstrip("@") or "alcast.local"

    targets = [
        ("admin", models.RoleName.admin, "Administrador"),
        ("financeiro", models.RoleName.financeiro, "Financeiro"),
        ("compras", models.RoleName.compras, "Compras"),
        ("vendas", models.RoleName.vendas, "Vendas"),
        ("auditoria", models.RoleName.auditoria, "Auditoria"),
    ]

    db = SessionLocal()
    try:
        roles: dict[models.RoleName, models.Role] = {}
        for _, rn, _ in targets:
            roles[rn] = ensure_role(db, rn)

        results = []
        for username, rn, display in targets:
            email = f"{username}@{domain}"
            user, created = ensure_user(
                db,
                email=email,
                name=display,
                role=roles[rn],
                password=pwd,
            )
            results.append((user.email, rn.value, "created" if created else "updated"))

        db.commit()

        print("Seed users OK:")
        for email, role, status in results:
            print(f"- {email} ({role}) [{status}]")
        print("Password:", pwd)
    finally:
        db.close()


if __name__ == "__main__":
    main()
